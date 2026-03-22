import logging
import unicodedata
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.project")


class CreateProjectHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        # Find or create customer — prefer org number search
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
            result = await self.client.get("/customer", params={
                "name": e["customerName"],
                "fields": "id,name", "count": 5,
            })
            customers = result.get("values", [])
            if customers:
                customer_id = customers[0]["id"]
        if not customer_id and e.get("customerName"):
            cust_body = {"name": e["customerName"], "isCustomer": True}
            if e.get("customerOrganizationNumber"):
                cust_body["organizationNumber"] = e["customerOrganizationNumber"]
            cust_result = await self.client.post("/customer", cust_body)
            customer_id = cust_result["value"]["id"]

        # Find or CREATE project manager employee
        project_manager_id = None
        if e.get("projectManagerName"):
            name = e["projectManagerName"]
            parts = name.split()
            # Search by email first (most precise)
            if e.get("projectManagerEmail"):
                try:
                    result = await self.client.get("/employee", params={
                        "email": e["projectManagerEmail"],
                        "fields": "id,firstName,lastName,email", "count": 5,
                    })
                    if result.get("values"):
                        project_manager_id = result["values"][0]["id"]
                except Exception:
                    pass
            # Search by name
            if not project_manager_id:
                result = await self.client.get("/employee", params={
                    "firstName": parts[0],
                    "fields": "id,firstName,lastName", "count": 5,
                })
                for emp in result.get("values", []):
                    fn = (emp.get("firstName") or "").lower()
                    ln = (emp.get("lastName") or "").lower()
                    if parts[0].lower() == fn and (len(parts) < 2 or parts[-1].lower() == ln):
                        project_manager_id = emp["id"]
                        break
            # CREATE if not found
            if not project_manager_id:
                dept_r = await self.client.get("/department", params={"fields": "id", "count": 1})
                dept_id = dept_r.get("values", [{}])[0].get("id")
                pm_email = e.get("projectManagerEmail") or ""
                if not pm_email:
                    fn = unicodedata.normalize("NFKD", parts[0]).encode("ascii", "ignore").decode().lower()
                    ln = unicodedata.normalize("NFKD", parts[-1]).encode("ascii", "ignore").decode().lower() if len(parts) > 1 else "pm"
                    pm_email = f"{fn}.{ln}@example.org"
                try:
                    emp_result = await self.client.post("/employee", {
                        "firstName": parts[0],
                        "lastName": parts[-1] if len(parts) > 1 else "Manager",
                        "email": pm_email,
                        "userType": "EXTENDED",
                        "department": {"id": dept_id},
                    })
                    project_manager_id = emp_result["value"]["id"]
                    logger.info(f"Created PM {name} id={project_manager_id}")
                except Exception as ex:
                    logger.warning(f"Could not create PM: {ex}")

        # Fallback to first employee
        if not project_manager_id:
            result = await self.client.get("/employee", params={"fields": "id", "count": 1})
            if result.get("values"):
                project_manager_id = result["values"][0]["id"]

        body: dict = {
            "name": e["name"],
            "startDate": e.get("startDate") or today,
        }

        if e.get("number"):
            body["number"] = str(e["number"])
        if customer_id:
            body["customer"] = {"id": customer_id}
        if project_manager_id:
            body["projectManager"] = {"id": project_manager_id}
        if e.get("endDate"):
            body["endDate"] = e["endDate"]
        if e.get("description"):
            body["description"] = e["description"]

        result = await self.post_with_retry("/project", body, fixups={
            "startDate": today,
        })
        project_id = result["value"]["id"]
        logger.info(f"Created project id={project_id}")
        self.verify(result, {"name": e["name"]})
