"""Handler for cost analysis tasks — analyze ledger, create projects for top expenses."""
import logging
from collections import defaultdict
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.cost_analysis")


class CostAnalysisHandler(BaseHandler):
    """Analyze ledger expenses and create projects for top accounts."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()
        num_accounts = e.get("numberOfAccounts", 3)

        # Step 1: Get all ledger postings for Jan and Feb (GETs are free)
        jan_totals = defaultdict(float)
        feb_totals = defaultdict(float)
        account_names = {}

        for month, start, end, totals in [
            ("jan", "2026-01-01", "2026-01-31", jan_totals),
            ("feb", "2026-02-01", "2026-02-28", feb_totals),
        ]:
            try:
                r = await self.client.get("/ledger/posting", params={
                    "dateFrom": start, "dateTo": end,
                    "fields": "id,date,amount,account",
                    "count": 1000,
                })
                for p in r.get("values", []):
                    acc = p.get("account", {})
                    num = acc.get("number", 0)
                    name = acc.get("name", "")
                    amt = p.get("amount", 0)
                    # Only expense accounts (4000-7999)
                    if 4000 <= num <= 7999 and amt > 0:
                        totals[num] += amt
                        account_names[num] = name
            except Exception as ex:
                logger.warning(f"Failed to get {month} postings: {ex}")

        # Step 2: Calculate increases
        all_accounts = set(jan_totals.keys()) | set(feb_totals.keys())
        increases = {}
        for acc_num in all_accounts:
            jan = jan_totals.get(acc_num, 0)
            feb = feb_totals.get(acc_num, 0)
            increase = feb - jan
            if increase > 0:
                increases[acc_num] = increase

        # Log ALL expense data for debugging
        logger.info(f"Jan totals: {dict(jan_totals)}")
        logger.info(f"Feb totals: {dict(feb_totals)}")
        logger.info(f"All increases: {sorted(increases.items(), key=lambda x: -x[1])}")

        # Sort by largest increase
        top_accounts = sorted(increases.items(), key=lambda x: -x[1])[:num_accounts]
        logger.info(f"Top {num_accounts} expense increases: {top_accounts}")

        if not top_accounts:
            logger.warning("No expense increases found between periods")
            return

        # Step 3: Get default employee for project manager
        r = await self.client.get("/employee", params={"fields": "id", "count": 1})
        employees = r.get("values", [])
        pm_id = employees[0]["id"] if employees else None

        # Step 4: Create a project for each top account
        for acc_num, increase in top_accounts:
            acc_name = account_names.get(acc_num, f"Konto {acc_num}")

            # Create activity first, then project with activity linked (saves writes)
            activity_id = None
            try:
                act_result = await self.client.post("/activity", {
                    "name": acc_name,
                    "activityType": "PROJECT_GENERAL_ACTIVITY",
                })
                activity_id = act_result["value"]["id"]
                logger.info(f"Created activity id={activity_id}")
            except Exception as ex:
                logger.warning(f"Activity creation failed: {ex}")

            project_body = {
                "name": acc_name,
                "startDate": today,
            }
            if pm_id:
                project_body["projectManager"] = {"id": pm_id}
            # Include activity in project creation — links it automatically
            if activity_id:
                project_body["projectActivities"] = [{"activity": {"id": activity_id}}]

            try:
                result = await self.client.post("/project", project_body)
                project_id = result["value"]["id"]
                logger.info(f"Created project '{acc_name}' (account {acc_num}, increase {increase}) id={project_id} with activity {activity_id}")

            except Exception as ex:
                logger.warning(f"Project creation failed for {acc_name}: {ex}")

        logger.info(f"Cost analysis completed — created {len(top_accounts)} projects")
