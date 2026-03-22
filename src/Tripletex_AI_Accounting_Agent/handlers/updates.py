"""Generic update handlers for product, department, project, order."""
import logging

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.updates")


class UpdateProductHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        search = e.get("searchName") or e.get("name") or ""

        result = await self.client.get("/product", params={
            "name": search, "fields": "id,version,name,number,priceExcludingVatCurrency,description,vatType,productUnit,isInactive", "count": 5,
        })
        products = result.get("values", [])
        if not products:
            logger.error(f"No product found: {search}")
            return

        prod = products[0]
        pid = prod["id"]

        if e.get("name"):
            prod["name"] = e["name"]
        if e.get("number"):
            prod["number"] = e["number"]
        if e.get("priceExcludingVatCurrency") is not None:
            prod["priceExcludingVatCurrency"] = e["priceExcludingVatCurrency"]
        if e.get("unitPrice") is not None:
            prod["priceExcludingVatCurrency"] = e["unitPrice"]
        if e.get("description"):
            prod["description"] = e["description"]

        await self.client.put(f"/product/{pid}", prod)
        logger.info(f"Updated product id={pid}")


class UpdateDepartmentHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        search = e.get("searchName") or e.get("name") or ""

        result = await self.client.get("/department", params={
            "fields": "id,version,name,departmentNumber", "count": 20,
        })
        depts = result.get("values", [])
        target = None
        for d in depts:
            if search.lower() in (d.get("name") or "").lower():
                target = d
                break
        if not target and depts:
            target = depts[0]
        if not target:
            logger.error(f"No department found: {search}")
            return

        did = target["id"]
        if e.get("name"):
            target["name"] = e["name"]
        if e.get("departmentNumber"):
            target["departmentNumber"] = str(e["departmentNumber"])

        await self.client.put(f"/department/{did}", target)
        logger.info(f"Updated department id={did}")


class UpdateProjectHandler(BaseHandler):
    # Limited fields to avoid returning non-updatable nested objects
    PROJECT_FIELDS = "id,version,name,number,description,startDate,endDate,customer,projectManager,department,isClosed,isReadyForInvoicing,mainProject,isInternal,isFixedPrice,isOffer"

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        search = e.get("searchName") or e.get("name") or ""

        result = await self.client.get("/project", params={
            "name": search, "fields": self.PROJECT_FIELDS, "count": 5,
        })
        projects = result.get("values", [])
        if not projects:
            logger.error(f"No project found: {search}")
            return

        proj = projects[0]
        pid = proj["id"]

        if e.get("name"):
            proj["name"] = e["name"]
        if e.get("description"):
            proj["description"] = e["description"]
        if e.get("startDate"):
            proj["startDate"] = e["startDate"]
        if e.get("endDate"):
            proj["endDate"] = e["endDate"]
        if e.get("isClosed") is not None:
            proj["isClosed"] = e["isClosed"]

        try:
            await self.client.put(f"/project/{pid}", proj)
            logger.info(f"Updated project id={pid}")
        except Exception as ex:
            logger.warning(f"PUT /project BETA failed: {ex}")
