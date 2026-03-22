import logging
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.correction")


class DeleteVoucherHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        # Find vouchers
        params: dict = {
            "dateFrom": e.get("dateFrom", "2026-01-01"),
            "dateTo": e.get("dateTo", "2026-12-31"),
            "fields": "id,number,date,description",
            "count": 100,
        }

        result = await self.client.get("/ledger/voucher", params=params)
        vouchers = result.get("values", [])

        if not vouchers:
            logger.error("No vouchers found")
            return

        # Match by number or description
        target = None
        for v in vouchers:
            if e.get("voucherNumber") and str(v.get("number")) == str(e["voucherNumber"]):
                target = v
                break
        if not target and e.get("description"):
            desc = e["description"].lower()
            for v in vouchers:
                if desc in (v.get("description") or "").lower():
                    target = v
                    break
        if not target:
            target = vouchers[0]

        voucher_id = target["id"]

        # Prefer reverse over delete (creates a counter-voucher)
        try:
            result = await self.client.put(
                f"/ledger/voucher/{voucher_id}/:reverse", {},
                params={"date": e.get("date") or today},
            )
            logger.info(f"Reversed voucher id={voucher_id}")
            return
        except Exception:
            logger.debug(f"Reverse failed, trying delete")

        # Fallback to delete
        try:
            await self.client.delete(f"/ledger/voucher/{voucher_id}")
            logger.info(f"Deleted voucher id={voucher_id}")
        except Exception as ex:
            logger.error(f"Could not delete/reverse voucher {voucher_id}: {ex}")
