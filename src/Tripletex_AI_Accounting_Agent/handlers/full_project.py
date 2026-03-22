"""Handler for full project cycle tasks (Tier 3).
Creates project, registers timesheets, posts supplier costs, creates invoice."""
import logging
from datetime import date, timedelta

from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.full_project")


class FullProjectCycleHandler(BaseHandler):
    """Execute complete project lifecycle deterministically."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()
        account_ctx = e.get("_account", {})

        # Step 0: Bank account setup (needed for invoicing later)
        await ensure_bank_account(self.client, account_ctx)

        # Step 1: Find or create customer (competition may pre-create customers)
        customer_name = e.get("customerName", "Customer")
        customer_id = None
        try:
            params = {"fields": "id,name", "count": 5}
            if e.get("customerOrganizationNumber"):
                params["organizationNumber"] = e["customerOrganizationNumber"]
            else:
                params["name"] = customer_name
            r = await self.client.get("/customer", params=params)
            if r.get("values"):
                customer_id = r["values"][0]["id"]
        except Exception:
            pass

        if not customer_id:
            cust_body = {"name": customer_name, "isCustomer": True}
            if e.get("customerOrganizationNumber"):
                cust_body["organizationNumber"] = e["customerOrganizationNumber"]
            cust_result = await self.client.post("/customer", cust_body)
            customer_id = cust_result["value"]["id"]
        logger.info(f"Using customer id={customer_id}")

        # Step 2: Find default department
        dept_id = account_ctx.get("default_dept_id")
        if not dept_id:
            r = await self.client.get("/department", params={"fields": "id", "count": 1})
            depts = r.get("values", [])
            if depts:
                dept_id = depts[0]["id"]

        # Step 3: Create/find project manager employee
        pm_name = e.get("projectManagerName", "")
        pm_email = e.get("projectManagerEmail", "")
        pm_id = await self._find_or_create_employee(pm_name, pm_email, dept_id)

        # Step 4: Find or create a PROJECT-compatible activity
        entries = e.get("timesheetEntries", [])
        activity_id = None

        # Search for existing PROJECT_GENERAL_ACTIVITY (must be project-compatible for projectActivities array)
        r = await self.client.get("/activity", params={"fields": "id,name,isProjectActivity,activityType", "count": 20})
        for act in r.get("values", []):
            act_type = act.get("activityType", "")
            if act_type in ("PROJECT_GENERAL_ACTIVITY", "PROJECT_SPECIFIC_ACTIVITY"):
                activity_id = act["id"]
                break

        # Always create if no project-compatible activity found
        if not activity_id:
            try:
                act_result = await self.client.post("/activity", {
                    "name": "Prosjektarbeid",
                    "activityType": "PROJECT_GENERAL_ACTIVITY",
                })
                activity_id = act_result["value"]["id"]
            except Exception:
                pass

        # Step 5: Create project WITH activity linked (saves a write)
        project_body = {
            "name": e.get("projectName", "Project"),
            "startDate": today,
            "customer": {"id": customer_id},
            "projectManager": {"id": pm_id},
        }
        if e.get("budget"):
            project_body["isFixedPrice"] = True
            project_body["fixedprice"] = e["budget"]
        if activity_id:
            project_body["projectActivities"] = [{"activity": {"id": activity_id}}]
        project_result = await self.client.post("/project", project_body)
        project_id = project_result["value"]["id"]
        logger.info(f"Created project id={project_id} with activity {activity_id}")

        # Step 6: Register timesheet entries
        for entry in entries:
            emp_name = entry.get("employeeName", "")
            emp_email = entry.get("employeeEmail", "")
            emp_id = await self._find_or_create_employee(emp_name, emp_email, dept_id)

            hours = entry.get("hours", 0)
            if hours > 0 and activity_id:
                ts_body = {
                    "employee": {"id": emp_id},
                    "project": {"id": project_id},
                    "activity": {"id": activity_id},
                    "date": today,
                    "hours": hours,
                }
                try:
                    result = await self.client.post("/timesheet/entry", ts_body)
                    logger.info(f"Registered {hours}h for {emp_name}")
                except Exception:
                    # Activity not compatible with project — retry without project
                    try:
                        ts_body.pop("project", None)
                        result = await self.client.post("/timesheet/entry", ts_body)
                        logger.info(f"Registered {hours}h for {emp_name} (no project link)")
                    except Exception as ex2:
                        logger.warning(f"Timesheet failed for {emp_name}: {ex2}")

        # Step 7: Register supplier costs as voucher
        for cost in e.get("supplierCosts", []):
            supplier_name = cost.get("supplierName", "Supplier")
            amount = cost.get("amount", 0)
            if amount <= 0:
                continue

            # Create supplier as customer with isSupplier=true
            supplier_body = {"name": supplier_name, "isCustomer": True, "isSupplier": True}
            sup_org = cost.get("organizationNumber") or cost.get("supplierOrganizationNumber")
            # accountNumber field might have been misextracted as org number
            acc_num = cost.get("accountNumber", "")
            if acc_num and len(str(acc_num)) >= 9:
                sup_org = sup_org or str(acc_num)
                acc_num = ""
            if sup_org:
                supplier_body["organizationNumber"] = str(sup_org)
            supplier_id = None
            try:
                sup_result = await self.client.post("/customer", supplier_body)
                supplier_id = sup_result["value"]["id"]
                logger.info(f"Created supplier {supplier_name} id={supplier_id}")
            except Exception:
                pass

            # Post supplier cost voucher: debit expense (4300 default), credit 2400
            expense_account = acc_num if acc_num and len(str(acc_num)) <= 4 else "4300"
            debit_id = await self._get_account_id(str(expense_account))
            credit_id = await self._get_account_id("2400")

            if debit_id and credit_id:
                credit_posting = {
                    "row": 2,
                    "account": {"id": credit_id},
                    "amountGross": -amount,
                    "amountGrossCurrency": -amount,
                    "description": f"Leverandørgjeld {supplier_name}",
                }
                if supplier_id:
                    credit_posting["supplier"] = {"id": supplier_id}
                voucher_body = {
                    "date": today,
                    "description": cost.get("description") or f"Leverandørkostnad {supplier_name}",
                    "postings": [
                        {
                            "row": 1,
                            "account": {"id": debit_id},
                            "amountGross": amount,
                            "amountGrossCurrency": amount,
                            "description": f"Kostnad {supplier_name}",
                        },
                        credit_posting,
                    ],
                }
                try:
                    await self.client.post("/ledger/voucher", voucher_body)
                    logger.info(f"Posted supplier cost voucher: {amount} for {supplier_name}")
                except Exception as ex:
                    logger.warning(f"Supplier voucher failed: {ex}")

        # Step 8: Create invoice to customer for the project
        invoice_amount = e.get("invoiceAmount") or e.get("budget", 0)
        if invoice_amount:
            order_body = {
                "customer": {"id": customer_id},
                "orderDate": today,
                "deliveryDate": today,
                "orderLines": [{
                    "description": e.get("projectName", "Prosjektfaktura"),
                    "count": 1,
                    "unitPriceExcludingVatCurrency": invoice_amount,
                    "vatType": {"id": 3},  # 25% MVA
                }],
            }
            order_result = await self.client.post("/order", order_body)
            order_id = order_result["value"]["id"]

            due_date = (date.today() + timedelta(days=14)).isoformat()
            inv_body = {
                "invoiceDate": today,
                "invoiceDueDate": due_date,
                "customer": {"id": customer_id},
                "orders": [{"id": order_id}],
            }
            inv_result = await self.client.post("/invoice", inv_body)
            invoice_id = inv_result["value"]["id"]
            logger.info(f"Created project invoice id={invoice_id}")

            # Send invoice
            try:
                await self.client.put(
                    f"/invoice/{invoice_id}/:send", {},
                    params={"sendType": "EMAIL", "overrideEmailAddress": ""},
                )
            except Exception:
                pass

        logger.info("Full project cycle completed")

    async def _find_or_create_employee(self, name: str, email: str, dept_id: int) -> int:
        """Find employee by name or create if not found."""
        if not hasattr(self, "_employee_cache"):
            self._employee_cache = {}

        cache_key = name.lower()
        if cache_key in self._employee_cache:
            return self._employee_cache[cache_key]

        # Search by name
        if name:
            parts = name.split()
            params = {"fields": "id,firstName,lastName,email", "count": 5}
            params["firstName"] = parts[0]
            if len(parts) > 1:
                params["lastName"] = parts[-1]
            r = await self.client.get("/employee", params=params)
            for emp in r.get("values", []):
                fn = (emp.get("firstName") or "").lower()
                ln = (emp.get("lastName") or "").lower()
                if parts[0].lower() in fn or (len(parts) > 1 and parts[-1].lower() in ln):
                    self._employee_cache[cache_key] = emp["id"]
                    return emp["id"]

        # Create employee
        parts = name.split() if name else ["Employee", "Unknown"]
        first_name = parts[0]
        last_name = parts[-1] if len(parts) > 1 else "Employee"
        if not email:
            email = f"{first_name.lower()}.{last_name.lower()}@example.org"

        body = {
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "userType": "EXTENDED",
            "department": {"id": dept_id},
        }
        result = await self.client.post("/employee", body)
        emp_id = result["value"]["id"]
        self._employee_cache[cache_key] = emp_id
        logger.info(f"Created employee {name} id={emp_id}")
        return emp_id

    async def _get_account_id(self, number: str):
        """Get ledger account ID by number."""
        if not hasattr(self, "_account_cache"):
            self._account_cache = {}
        if number in self._account_cache:
            return self._account_cache[number]
        r = await self.client.get("/ledger/account", params={
            "number": number, "fields": "id,number", "count": 1,
        })
        vals = r.get("values", [])
        if vals:
            self._account_cache[number] = vals[0]["id"]
            return vals[0]["id"]
        return None
