"""Deterministic handler for ledger correction tasks.
Finds actual vouchers/postings, reads counterpart accounts, makes precise corrections."""
import logging
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.ledger_correction")


class LedgerCorrectionHandler(BaseHandler):
    """Find erroneous vouchers and correct them using actual posting data."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()
        errors = e.get("errors", [])

        if not errors:
            logger.warning("No errors extracted from prompt")
            return

        # Step 1: GET all vouchers with postings (free)
        vouchers = []
        try:
            r = await self.client.get("/ledger/voucher", params={
                "dateFrom": "2026-01-01", "dateTo": "2026-12-31",
                "fields": "id,number,date,description,postings(id,account,amountGross,description)",
                "count": 100,
            })
            vouchers = r.get("values", [])
            logger.info(f"Found {len(vouchers)} vouchers to analyze")
        except Exception as ex:
            logger.warning(f"Could not fetch vouchers: {ex}")

        # Build a lookup: account_number → account_id
        account_cache = {}
        for v in vouchers:
            for p in v.get("postings", []):
                acc = p.get("account", {})
                num = acc.get("number")
                acc_id = acc.get("id")
                if num and acc_id:
                    account_cache[num] = acc_id

        # Step 2: Process each error
        for error in errors:
            error_type = error.get("type", "unknown")
            acc_num = str(error.get("accountNumber", ""))
            amount = error.get("amount", 0)
            correct_acc = error.get("correctAccount")
            description = error.get("description") or error.get("voucherDescription") or "Korreksjon"

            logger.info(f"Processing error: type={error_type} acc={acc_num} amt={amount} correct={correct_acc}")

            # Find the matching voucher/posting
            matching_voucher = None
            matching_posting = None
            counterpart_acc_id = None

            for v in vouchers:
                postings = v.get("postings", [])
                for p in postings:
                    p_acc = p.get("account", {}).get("number")
                    p_amt = abs(p.get("amountGross", 0))
                    if str(p_acc) == acc_num and abs(p_amt - amount) < 1:
                        matching_voucher = v
                        matching_posting = p
                        # Find the counterpart (other posting in same voucher)
                        for other in postings:
                            if other["id"] != p["id"]:
                                counterpart_acc_id = other.get("account", {}).get("id")
                                break
                        break
                if matching_voucher:
                    break

            if matching_voucher:
                logger.info(f"Found matching voucher id={matching_voucher['id']} number={matching_voucher.get('number')}")
            else:
                logger.warning(f"No matching voucher found for {error_type} acc={acc_num} amt={amount}")

            if error_type == "duplicate":
                # Reverse the duplicate voucher
                if matching_voucher:
                    try:
                        await self.client.put(
                            f"/ledger/voucher/{matching_voucher['id']}/:reverse",
                            {}, params={"date": today},
                        )
                        logger.info(f"Reversed duplicate voucher {matching_voucher['id']}")
                    except Exception as ex:
                        logger.warning(f"Reverse failed: {ex}")

            elif error_type == "wrong_account":
                # Credit wrong account, debit correct account
                wrong_acc_id = account_cache.get(int(acc_num)) if acc_num.isdigit() else None
                correct_acc_id = await self._get_or_create_account(str(correct_acc)) if correct_acc else None
                voucher_date = matching_voucher.get("date", today) if matching_voucher else today

                if wrong_acc_id and correct_acc_id:
                    try:
                        await self.client.post("/ledger/voucher", {
                            "date": voucher_date,
                            "description": f"Korreksjon: {acc_num} → {correct_acc} ({amount} kr)",
                            "postings": [
                                {"row": 1, "account": {"id": correct_acc_id},
                                 "amountGross": amount, "amountGrossCurrency": amount,
                                 "description": f"Korreksjon til konto {correct_acc}"},
                                {"row": 2, "account": {"id": wrong_acc_id},
                                 "amountGross": -amount, "amountGrossCurrency": -amount,
                                 "description": f"Korreksjon fra konto {acc_num}"},
                            ],
                        })
                        logger.info(f"Posted wrong_account correction: {acc_num} → {correct_acc}")
                    except Exception as ex:
                        logger.warning(f"Wrong account correction failed: {ex}")

            elif error_type == "missing":
                # Missing VAT line — debit VAT account, credit expense account
                # If counterpart is 2400 (needs supplier.id), use expense account instead
                vat_acc_id = await self._get_or_create_account(str(correct_acc)) if correct_acc else None

                # Try counterpart first; if it's a supplier account (2400), use expense instead
                credit_acc_id = counterpart_acc_id
                counterpart_num = None
                if matching_voucher:
                    for p in matching_voucher.get("postings", []):
                        if p.get("id") != (matching_posting or {}).get("id"):
                            counterpart_num = p.get("account", {}).get("number")
                if counterpart_num and 2400 <= (counterpart_num or 0) <= 2499:
                    # Supplier account — use expense account to avoid supplier.id requirement
                    credit_acc_id = account_cache.get(int(acc_num)) if acc_num.isdigit() else None
                elif not credit_acc_id:
                    credit_acc_id = account_cache.get(int(acc_num)) if acc_num.isdigit() else None

                if vat_acc_id and credit_acc_id:
                    vat_amount = round(amount * 0.25, 2)  # 25% MVA
                    voucher_date = matching_voucher.get("date", today) if matching_voucher else today
                    try:
                        await self.client.post("/ledger/voucher", {
                            "date": voucher_date,
                            "description": f"Korreksjon: Manglende MVA ({correct_acc}) for {amount} kr",
                            "postings": [
                                {"row": 1, "account": {"id": vat_acc_id},
                                 "amountGross": vat_amount, "amountGrossCurrency": vat_amount,
                                 "description": f"Inngående MVA 25% av {amount}"},
                                {"row": 2, "account": {"id": credit_acc_id},
                                 "amountGross": -vat_amount, "amountGrossCurrency": -vat_amount,
                                 "description": f"Korreksjon MVA"},
                            ],
                        })
                        logger.info(f"Posted missing VAT correction: {vat_amount} to {correct_acc}")
                    except Exception as ex:
                        logger.warning(f"Missing VAT correction failed: {ex}")

            elif error_type == "wrong_amount":
                # Excess amount needs to be reversed
                correct_amount = error.get("correctAmount", 0)
                if not correct_amount:
                    # Parse correct amount from description — it's the LAST number
                    # e.g., "23300 NOK comptabilisé au lieu de 8700 NOK" → 8700
                    desc = error.get("description") or error.get("voucherDescription") or ""
                    import re
                    all_amounts = re.findall(r'(\d+)\s*(?:NOK|kr|réel)?', desc)
                    if len(all_amounts) >= 2:
                        correct_amount = int(all_amounts[-1])  # Last number = correct
                    elif len(all_amounts) == 1:
                        correct_amount = int(all_amounts[0])

                diff = amount - correct_amount
                voucher_date = matching_voucher.get("date", today) if matching_voucher else today
                if diff > 0 and counterpart_acc_id:
                    wrong_acc_id = account_cache.get(int(acc_num)) if acc_num.isdigit() else None
                    if wrong_acc_id:
                        try:
                            await self.client.post("/ledger/voucher", {
                                "date": voucher_date,
                                "description": f"Korreksjon: {acc_num} beløp {amount} → {correct_amount} kr",
                                "postings": [
                                    {"row": 1, "account": {"id": counterpart_acc_id},
                                     "amountGross": diff, "amountGrossCurrency": diff,
                                     "description": f"Tilbakeføring overskytende {diff} kr"},
                                    {"row": 2, "account": {"id": wrong_acc_id},
                                     "amountGross": -diff, "amountGrossCurrency": -diff,
                                     "description": f"Korreksjon {acc_num} ({amount} → {correct_amount})"},
                                ],
                            })
                            logger.info(f"Posted wrong_amount correction: {amount} → {correct_amount} (diff {diff})")
                        except Exception as ex:
                            logger.warning(f"Wrong amount correction failed: {ex}")

        logger.info("Ledger correction completed")

    async def _get_or_create_account(self, number: str):
        """Get account ID by number, create if missing."""
        try:
            r = await self.client.get("/ledger/account", params={
                "number": number, "fields": "id,number", "count": 1,
            })
            if r.get("values"):
                return r["values"][0]["id"]
        except Exception:
            pass
        # Create if missing
        try:
            r = await self.client.post("/ledger/account", {
                "number": int(number),
                "name": f"Konto {number}",
            })
            return r["value"]["id"]
        except Exception:
            return None
