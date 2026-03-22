import logging
from datetime import date, timedelta

from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from handlers.order_utils import build_order_lines
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.project_invoice")


class ProjectInvoiceHandler(BaseHandler):
    """Create an invoice linked to a project (project billing)."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        await ensure_bank_account(self.client)

        # Step 1: Find or create customer — prefer org number
        customer_id = None
        if e.get("customerOrganizationNumber"):
            try:
                result = await self.client.get("/customer", params={
                    "organizationNumber": e["customerOrganizationNumber"],
                    "fields": "id,name", "count": 5,
                })
                if result.get("values"):
                    customer_id = result["values"][0]["id"]
            except Exception:
                pass
        if not customer_id and e.get("customerName"):
            try:
                result = await self.client.get("/customer", params={
                    "name": e["customerName"],
                    "fields": "id,name", "count": 5,
                })
                if result.get("values"):
                    customer_id = result["values"][0]["id"]
            except Exception:
                pass

        if not customer_id:
            customer_body = {"name": e.get("customerName", "Customer"), "isCustomer": True}
            if e.get("customerOrganizationNumber"):
                customer_body["organizationNumber"] = e["customerOrganizationNumber"]
            cust_result = await self.client.post("/customer", customer_body)
            customer_id = cust_result["value"]["id"]
        logger.info(f"Customer id={customer_id}")

        # Step 2: Find or create project
        project_id = None
        if e.get("projectName"):
            result = await self.client.get("/project", params={
                "name": e["projectName"],
                "fields": "id,name",
                "count": 5,
            })
            projects = result.get("values", [])
            if projects:
                project_id = projects[0]["id"]

        if not project_id:
            project_body = {
                "name": e.get("projectName") or e.get("description") or "Project",
                "startDate": today,
                "customer": {"id": customer_id},
            }
            # Set fixed price during creation (PUT /project is BETA — avoid it)
            fixed = e.get("totalFixedPrice") or e.get("fixedPrice")
            if fixed:
                project_body["isFixedPrice"] = True
                project_body["fixedprice"] = fixed

            emp_result = await self.client.get("/employee", params={
                "fields": "id", "count": 1,
            })
            employees = emp_result.get("values", [])
            if employees:
                project_body["projectManager"] = {"id": employees[0]["id"]}

            proj_result = await self.client.post("/project", project_body)
            project_id = proj_result["value"]["id"]
        logger.info(f"Project id={project_id}")

        # Step 2a: Set fixed price — try during creation (above), fallback to PUT [BETA]
        fixed = e.get("totalFixedPrice") or e.get("fixedPrice")
        if fixed:
            # Check if it was set during creation by reading back (GETs are free)
            try:
                proj_check = await self.client.get(f"/project/{project_id}", params={
                    "fields": "id,isFixedPrice,fixedprice", "count": 1,
                })
                proj_val = proj_check.get("value", proj_check)
                if not proj_val.get("isFixedPrice"):
                    # Wasn't set during creation — try PUT [BETA, may 403]
                    try:
                        proj_fields = "id,version,name,number,description,startDate,endDate,customer,projectManager,department,isClosed,isFixedPrice,fixedprice"
                        proj_data = (await self.client.get(f"/project/{project_id}", params={"fields": proj_fields}))["value"]
                        proj_data["isFixedPrice"] = True
                        proj_data["fixedprice"] = fixed
                        await self.client.put(f"/project/{project_id}", proj_data)
                        logger.info(f"Set fixed price {fixed} via PUT (BETA)")
                    except Exception as ex:
                        logger.warning(f"PUT /project BETA failed: {ex}")
                else:
                    logger.info(f"Fixed price {fixed} already set during creation")
            except Exception:
                pass

        # Step 2b: Register timesheet hours if specified
        hours = e.get("hours")
        employee_name = e.get("employeeName")

        # Fallback: try to parse hours from orderLines description
        if not hours and e.get("orderLines"):
            import re
            for line in e["orderLines"]:
                desc = line.get("description") or ""
                m = re.search(r"(\d+)\s*(hours|timer|horas|heures|Stunden|timar)", desc, re.IGNORECASE)
                if m:
                    hours = int(m.group(1))
                    # Try to find employee name in description
                    name_m = re.search(r"for\s+([A-ZÆØÅ][a-zæøåéüñã]+\s+[A-ZÆØÅ][a-zæøåéüñã]+)", desc)
                    if name_m and not employee_name:
                        employee_name = name_m.group(1)
                    break

        if hours and employee_name:
            try:
                # Find employee
                emp_name = employee_name
                emp_params = {"fields": "id,firstName,lastName", "count": 5}
                parts = emp_name.split()
                emp_params["firstName"] = parts[0]
                if len(parts) > 1:
                    emp_params["lastName"] = parts[-1]
                emp_result = await self.client.get("/employee", params=emp_params)
                emp_list = emp_result.get("values", [])

                if emp_list:
                    emp_id = emp_list[0]["id"]
                else:
                    # Create employee
                    dept_result = await self.client.get("/department", params={"fields": "id", "count": 1})
                    dept_id = dept_result.get("values", [{}])[0].get("id")
                    emp_email = e.get("employeeEmail") or f"{parts[0].lower()}.{parts[-1].lower() if len(parts) > 1 else 'unknown'}@example.org"
                    emp_body = {
                        "firstName": parts[0],
                        "lastName": parts[-1] if len(parts) > 1 else "Employee",
                        "email": emp_email,
                        "userType": "EXTENDED",
                        "department": {"id": dept_id},
                    }
                    emp_create = await self.client.post("/employee", emp_body)
                    emp_id = emp_create["value"]["id"]
                    logger.info(f"Created employee {emp_name} id={emp_id}")

                if emp_id:
                    # Find activity
                    act_id = None
                    act_result = await self.client.get("/activity", params={
                        "fields": "id,name", "count": 20,
                    })
                    activities = act_result.get("values", [])
                    act_name = (e.get("activityName") or "").lower()
                    for act in activities:
                        if act_name and act_name in (act.get("name") or "").lower():
                            act_id = act["id"]
                            break
                    if not act_id and activities:
                        act_id = activities[-1]["id"]  # default to last (often chargeable)

                    if act_id:
                        await self.client.post("/timesheet/entry", {
                            "employee": {"id": emp_id},
                            "date": today,
                            "hours": hours,
                            "activity": {"id": act_id},
                            "project": {"id": project_id},
                        })
                        logger.info(f"Registered {hours}h timesheet for employee {emp_id}")
            except Exception as ex:
                logger.warning(f"Timesheet registration failed: {ex}")

        # Step 3: Build order lines (creates products if needed)
        order_lines = await build_order_lines(self.client, e)

        # Ensure VAT type is set on all order lines (default 25% for services)
        for ol in order_lines:
            if "vatType" not in ol:
                ol["vatType"] = {"id": 3}  # 25% MVA — standard for consulting/services

        order_result = await self.client.post("/order", {
            "customer": {"id": customer_id},
            "project": {"id": project_id},
            "orderDate": e.get("invoiceDate") or today,
            "deliveryDate": e.get("invoiceDate") or today,
            "orderLines": order_lines,
        })
        order_id = order_result["value"]["id"]
        logger.info(f"Created order id={order_id} linked to project {project_id}")

        # Step 4: Create invoice
        invoice_date = e.get("invoiceDate") or today
        default_due = (date.fromisoformat(invoice_date) + timedelta(days=14)).isoformat()
        inv_result = await self.client.post("/invoice", {
            "invoiceDate": invoice_date,
            "invoiceDueDate": e.get("dueDate") or default_due,
            "customer": {"id": customer_id},
            "orders": [{"id": order_id}],
        })
        invoice_id = inv_result["value"]["id"]
        logger.info(f"Created project invoice id={invoice_id}")

        # Send invoice
        try:
            await self.client.put(
                f"/invoice/{invoice_id}/:send", {},
                params={"sendType": "EMAIL", "overrideEmailAddress": ""},
            )
            logger.info(f"Project invoice {invoice_id} sent")
        except Exception:
            pass

        # Step 5: Register payment if requested
        if e.get("registerPayment"):
            amount = e.get("amount", e.get("totalAmount", 0))
            if not amount:
                for line in e.get("orderLines", []):
                    amount += line.get("unitPrice", 0) * line.get("quantity", 1)

            pt_result = await self.client.get("/invoice/paymentType", params={
                "fields": "id,description", "count": 10,
            })
            payment_types = pt_result.get("values", [])
            payment_type_id = payment_types[0]["id"] if payment_types else 0
            for pt in payment_types:
                if "bank" in (pt.get("description") or "").lower():
                    payment_type_id = pt["id"]
                    break

            await self.client.put(
                f"/invoice/{invoice_id}/:payment",
                {},
                params={
                    "paymentDate": e.get("paymentDate") or today,
                    "paymentTypeId": payment_type_id,
                    "paidAmount": amount,
                },
            )
            logger.info(f"Payment registered on project invoice {invoice_id}")
