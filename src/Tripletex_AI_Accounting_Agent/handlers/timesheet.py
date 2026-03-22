import logging
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.timesheet")


class RegisterTimesheetHandler(BaseHandler):
    """Register timesheet hours for an employee."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        # Find employee
        employee_id = None
        if e.get("employeeName"):
            name = e["employeeName"]
            params = {"fields": "id,firstName,lastName", "count": 5}
            parts = name.split()
            params["firstName"] = parts[0]
            if len(parts) > 1:
                params["lastName"] = parts[-1]
            result = await self.client.get("/employee", params=params)
            employees = result.get("values", [])
            if employees:
                employee_id = employees[0]["id"]

        if not employee_id:
            result = await self.client.get("/employee", params={"fields": "id", "count": 1})
            employees = result.get("values", [])
            if employees:
                employee_id = employees[0]["id"]

        # Find activity
        activity_id = None
        if e.get("activityName"):
            result = await self.client.get("/activity", params={
                "fields": "id,name", "count": 20,
            })
            activities = result.get("values", [])
            search = e["activityName"].lower()
            for act in activities:
                if search in (act.get("name") or "").lower():
                    activity_id = act["id"]
                    break
            if not activity_id and activities:
                activity_id = activities[0]["id"]
        else:
            # Default to first activity
            result = await self.client.get("/activity", params={"fields": "id,name", "count": 5})
            activities = result.get("values", [])
            if activities:
                activity_id = activities[0]["id"]

        # Find project if specified
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

        # Register timesheet entry
        hours = e.get("hours", e.get("count", 0))
        entry_date = e.get("date") or today

        body = {
            "employee": {"id": employee_id},
            "date": entry_date,
            "hours": hours,
            "activity": {"id": activity_id},
        }

        if project_id:
            body["project"] = {"id": project_id}
        if e.get("comment"):
            body["comment"] = e["comment"]

        result = await self.client.post("/timesheet/entry", body)
        entry_id = result["value"]["id"]
        logger.info(f"Registered {hours}h timesheet entry id={entry_id}")
