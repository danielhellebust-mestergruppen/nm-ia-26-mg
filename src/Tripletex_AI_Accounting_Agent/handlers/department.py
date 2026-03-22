import logging

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.department")


async def try_enable_department_module(client) -> None:
    """Try to enable department accounting module via available API mechanisms."""
    # Approach 1: Try POST /company/salesmodules (if a department module exists)
    # Known not to have DEPARTMENT in enum, but try anyway in case competition proxy supports it
    try:
        await client.post("/company/salesmodules", {"name": "DEPARTMENT"})
        logger.info("Enabled department module via salesmodules")
        return
    except Exception:
        logger.debug("salesmodules DEPARTMENT not available")

    # Approach 2: Try PUT /company to set module flags
    try:
        company_data = await client.get("/company/1", params={"fields": "*"})
        company = company_data.get("value", company_data)
        # The Modules schema has moduleDepartmentAccounting and moduledepartment
        # Try setting them if the company object supports it
        if "modules" in company or True:  # Try regardless
            await client.put("/company", {
                **company,
                "moduleDepartmentAccounting": True,
                "moduledepartment": True,
            })
            logger.info("Enabled department module via company update")
            return
    except Exception as e:
        logger.debug(f"Company module update failed: {e}")


class CreateDepartmentHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities

        # Enable department accounting module if requested
        if e.get("enableDepartmentAccounting", False):
            await try_enable_department_module(self.client)

        # Handle multiple departments (e.g. "create 3 departments")
        items = e.get("items", [e])  # list of depts, or wrap single as list

        for i, dept in enumerate(items):
            if isinstance(dept, str):
                dept = {"name": dept}

            body: dict = {
                "name": dept.get("name", e.get("name", f"Department {i+1}")),
            }

            dept_num = dept.get("departmentNumber", e.get("departmentNumber"))
            if dept_num:
                body["departmentNumber"] = str(dept_num)
            if dept.get("departmentManager"):
                name = dept["departmentManager"]
                result = await self.client.get("/employee", params={
                    "firstName": name.split()[0],
                    "fields": "id,firstName,lastName",
                    "count": 5,
                })
                employees = result.get("values", [])
                if employees:
                    body["departmentManager"] = {"id": employees[0]["id"]}

            result = await self.client.post("/department", body)
            dept_id = result["value"]["id"]
            logger.info(f"Created department id={dept_id} name={body['name']}")


class EnableModuleHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        module_name = e.get("moduleName", "")

        if "department" in module_name.lower():
            await try_enable_department_module(self.client)
        else:
            # Generic: try salesmodules
            name = module_name.upper().replace(" ", "_")
            try:
                await self.client.post("/company/salesmodules", {"name": name})
                logger.info(f"Enabled module: {name}")
            except Exception as ex:
                logger.warning(f"Could not enable module {name}: {ex}")
