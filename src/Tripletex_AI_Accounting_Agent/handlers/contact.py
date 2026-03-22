"""Handler for creating contact persons."""
import logging

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.contact")


class CreateContactHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities

        # Find customer to attach contact to
        customer_id = e.get("customerId")
        if not customer_id and e.get("customerName"):
            result = await self.client.get("/customer", params={
                "name": e["customerName"], "fields": "id,name", "count": 5,
            })
            customers = result.get("values", [])
            if customers:
                customer_id = customers[0]["id"]

        body = {
            "firstName": e.get("firstName", ""),
            "lastName": e.get("lastName", ""),
        }
        if e.get("email"):
            body["email"] = e["email"]
        if e.get("phoneNumber"):
            body["phoneNumber"] = e["phoneNumber"]
        if customer_id:
            body["customer"] = {"id": customer_id}

        result = await self.client.post("/contact", body)
        contact_id = result["value"]["id"]
        logger.info(f"Created contact id={contact_id}")
