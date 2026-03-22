"""Handler for bank reconciliation tasks (Tier 3)."""
import logging
from datetime import date

from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.bank")


class BankReconciliationHandler(BaseHandler):
    """Handle bank reconciliation from CSV or statement import."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        await ensure_bank_account(self.client)

        # Find bank account (1920)
        result = await self.client.get("/ledger/account", params={
            "number": "1920", "fields": "id,number,name", "count": 1,
        })
        accounts = result.get("values", [])
        if not accounts:
            logger.error("No bank account 1920 found")
            return
        account_id = accounts[0]["id"]

        # Find accounting period covering today
        period_id = None
        try:
            periods = await self.client.get("/ledger/accountingPeriod", params={
                "fields": "id,start,end", "count": 12,
            })
            for p in periods.get("values", []):
                if p.get("start", "") <= today < p.get("end", "9999"):
                    period_id = p["id"]
                    break
            if not period_id and periods.get("values"):
                period_id = periods["values"][-1]["id"]
        except Exception:
            pass

        if not period_id:
            logger.error("No accounting period found")
            return

        # Create bank reconciliation
        try:
            body = {
                "account": {"id": account_id},
                "accountingPeriod": {"id": period_id},
                "type": "MANUAL",
            }

            result = await self.client.post("/bank/reconciliation", body)
            recon_id = result["value"]["id"]
            logger.info(f"Created bank reconciliation id={recon_id}")

        except Exception as ex:
            logger.warning(f"Bank reconciliation failed: {ex}")
