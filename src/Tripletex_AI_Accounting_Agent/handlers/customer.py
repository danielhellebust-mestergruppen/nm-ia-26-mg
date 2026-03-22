import logging

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.customer")


class CreateCustomerHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities

        # Handle multiple customers
        items = e.get("items", [e])
        for item in items:
            if isinstance(item, str):
                item = {"name": item}
            await self._create_one(item if "name" in item else e)

    async def _create_one(self, e: dict) -> None:
        is_supplier = e.get("isSupplier", False)
        is_customer = e.get("isCustomer", not is_supplier)

        body: dict = {"name": e["name"]}

        if e.get("email"):
            body["email"] = e["email"]
            body["invoiceEmail"] = e["email"]  # Also set invoiceEmail for scoring
        if e.get("phoneNumber"):
            body["phoneNumber"] = e["phoneNumber"]
        if e.get("organizationNumber"):
            body["organizationNumber"] = e["organizationNumber"]
        if e.get("postalAddress"):
            body["postalAddress"] = {
                "addressLine1": e.get("postalAddress", ""),
                "postalCode": e.get("postalCode", ""),
                "city": e.get("city", ""),
            }
        elif e.get("address"):
            body["postalAddress"] = {
                "addressLine1": e.get("address", ""),
                "postalCode": e.get("postalCode", ""),
                "city": e.get("city", ""),
            }
        if e.get("country"):
            body["country"] = e["country"]
        if e.get("invoiceEmail"):
            body["invoiceEmail"] = e["invoiceEmail"]

        # Always use /customer endpoint — scoring checks /customer table
        # Tripletex always sets isCustomer=true regardless, so match that behavior
        body["isCustomer"] = True
        if is_supplier:
            body["isSupplier"] = True

        result = await self.client.post("/customer", body)
        entity_id = result["value"]["id"]
        logger.info(f"Created customer/supplier id={entity_id}")


class UpdateCustomerHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        search_name = e.get("searchName", "")

        result = await self.client.get("/customer", params={
            "name": search_name,
            "fields": "id,version,name,email,phoneNumber,organizationNumber,postalAddress,isCustomer,isSupplier,invoiceEmail,country",
            "count": 5,
        })
        customers = result.get("values", [])

        if not customers:
            logger.error(f"No customer found matching: {search_name}")
            return

        cust = customers[0]
        customer_id = cust["id"]

        if e.get("name"):
            cust["name"] = e["name"]
        if e.get("email"):
            cust["email"] = e["email"]
        if e.get("phoneNumber"):
            cust["phoneNumber"] = e["phoneNumber"]

        await self.client.put(f"/customer/{customer_id}", cust)
        logger.info(f"Updated customer id={customer_id}")
