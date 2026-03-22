import logging

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.product")


class CreateProductHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities

        # Handle multiple products
        items = e.get("items", [e])
        for item in items:
            if isinstance(item, str):
                item = {"name": item}
            await self._create_one(item if "name" in item else e)

    async def _create_one(self, e: dict) -> None:
        body: dict = {
            "name": e["name"],
        }

        if e.get("number"):
            body["number"] = e["number"]
        if e.get("unitPriceExcludingVat") is not None:
            body["priceExcludingVatCurrency"] = e["unitPriceExcludingVat"]
        if e.get("unitPrice") is not None:
            body["priceExcludingVatCurrency"] = e["unitPrice"]
        if e.get("description"):
            body["description"] = e["description"]
        if e.get("vatTypeId"):
            body["vatType"] = {"id": e["vatTypeId"]}

        result = await self.client.post("/product", body)
        product_id = result["value"]["id"]
        logger.info(f"Created product id={product_id}")
