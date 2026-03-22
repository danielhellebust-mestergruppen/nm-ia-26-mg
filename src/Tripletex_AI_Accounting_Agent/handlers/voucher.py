"""Handler for creating manual vouchers/journal entries."""
import logging
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.voucher")


class CreateVoucherHandler(BaseHandler):
    """Create a manual voucher (journal entry) with postings."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        # Use the receipt/voucher date as-is (Tripletex accepts future dates)

        # Find department if specified (GETs are free)
        dept_id = None
        dept_name = e.get("departmentName", "")
        if dept_name:
            account_ctx = e.get("_account", {})
            for d in account_ctx.get("departments", []):
                if dept_name.lower() in (d.get("name") or "").lower():
                    dept_id = d["id"]
                    break
            if not dept_id:
                try:
                    result = await self.client.get("/department", params={
                        "fields": "id,name", "count": 20,
                    })
                    for d in result.get("values", []):
                        if dept_name.lower() in (d.get("name") or "").lower():
                            dept_id = d["id"]
                            break
                except Exception:
                    pass

        # Build postings from extracted data
        postings = []
        row = 1
        for posting in e.get("postings", []):
            p = {
                "date": posting.get("date", e.get("date") or today),
                "amountGross": posting.get("amount", 0),
                "amountGrossCurrency": posting.get("amount", 0),
                "description": posting.get("description") or e.get("description") or "",
                "row": row,
            }
            if dept_id:
                p["department"] = {"id": dept_id}
            row += 1

            # Resolve account by number
            account_id = posting.get("accountId")
            if not account_id and posting.get("accountNumber"):
                result = await self.client.get("/ledger/account", params={
                    "number": str(posting["accountNumber"]),
                    "fields": "id,number",
                    "count": 1,
                })
                accs = result.get("values", [])
                if accs:
                    account_id = accs[0]["id"]

            if account_id:
                p["account"] = {"id": account_id}

            postings.append(p)

        # If no structured postings, create debit/credit from amount
        if not postings and e.get("amount"):
            debit_acc = e.get("debitAccount", "1920")
            credit_acc = e.get("creditAccount", "3000")

            for acc_num in [debit_acc, credit_acc]:
                result = await self.client.get("/ledger/account", params={
                    "number": str(acc_num), "fields": "id,number", "count": 1,
                })
                accs = result.get("values", [])
                if accs:
                    amt = e["amount"] if acc_num == debit_acc else -e["amount"]
                    postings.append({
                        "date": e.get("date") or today,
                        "account": {"id": accs[0]["id"]},
                        "amountGross": amt, "amountGrossCurrency": amt,
                        "description": e.get("description") or "",
                        "row": row,
                    })
                    row += 1

        if not postings:
            logger.error("No postings could be built for voucher")
            return

        try:
            result = await self.client.post("/ledger/voucher", {
                "date": e.get("date") or today,
                "description": e.get("description") or "Manual voucher",
                "postings": postings,
            })
            voucher_id = result["value"]["id"]
            logger.info(f"Created voucher id={voucher_id}")
        except Exception as ex:
            logger.warning(f"Voucher creation failed: {ex}")
