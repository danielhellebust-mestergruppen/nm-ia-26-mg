"""Handler for creating accounting dimensions with values and posting vouchers with them."""
import logging
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.accounting_dimension")


class CreateAccountingDimensionHandler(BaseHandler):
    """Create a custom accounting dimension with values, then post a voucher linked to a dimension value."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        # Step 1: Create the accounting dimension
        dim_name = e.get("dimensionName", "Custom Dimension")
        dim_result = await self.client.post("/ledger/accountingDimensionName", {
            "dimensionName": dim_name,
            "active": True,
        })
        dim_id = dim_result["value"]["id"]
        dim_index = dim_result["value"]["dimensionIndex"]
        logger.info(f"Created dimension '{dim_name}' id={dim_id} index={dim_index}")

        # Step 2: Create dimension values
        value_ids = {}
        for i, val_name in enumerate(e.get("dimensionValues", []), 1):
            try:
                val_result = await self.client.post("/ledger/accountingDimensionValue", {
                    "dimensionIndex": dim_index,
                    "displayName": val_name,
                    "number": str(i),
                    "active": True,
                    "showInVoucherRegistration": True,
                })
                value_ids[val_name.lower()] = val_result["value"]["id"]
                logger.info(f"Created dimension value '{val_name}' id={val_result['value']['id']}")
            except Exception as ex:
                logger.warning(f"Failed to create dimension value '{val_name}': {ex}")

        # Step 3: Post voucher linked to dimension value (if requested)
        voucher_account = e.get("accountNumber")
        voucher_amount = e.get("amount", e.get("voucherAmount", 0))
        linked_value = e.get("linkedDimensionValue", "")

        if voucher_account and voucher_amount:
            # Find the account
            acc_result = await self.client.get("/ledger/account", params={
                "number": str(voucher_account), "fields": "id,number", "count": 1,
            })
            accs = acc_result.get("values", [])
            if not accs:
                logger.error(f"Account {voucher_account} not found")
                return
            account_id = accs[0]["id"]

            # Find bank account for counter-posting
            bank_result = await self.client.get("/ledger/account", params={
                "number": "1920", "fields": "id", "count": 1,
            })
            bank_accs = bank_result.get("values", [])
            if not bank_accs:
                logger.error("Bank account 1920 not found")
                return
            bank_id = bank_accs[0]["id"]

            # Find the dimension value ID
            dim_value_id = None
            if linked_value:
                dim_value_id = value_ids.get(linked_value.lower())
                if not dim_value_id:
                    # Search for it
                    try:
                        search = await self.client.get("/ledger/accountingDimensionValue/search", params={
                            "dimensionIndex": dim_index,
                            "fields": "id,displayName",
                            "count": 10,
                        })
                        for v in search.get("values", []):
                            if linked_value.lower() in (v.get("displayName") or "").lower():
                                dim_value_id = v["id"]
                                break
                    except Exception:
                        pass

            # Build postings — link dimension value to BOTH postings
            dim_field = f"freeAccountingDimension{dim_index}" if dim_value_id else None

            debit_posting = {
                "date": today,
                "account": {"id": account_id},
                "amountGross": voucher_amount,
                "amountGrossCurrency": voucher_amount,
                "description": f"{e.get('description') or dim_name} - {linked_value or dim_name}",
                "row": 1,
            }
            credit_posting = {
                "date": today,
                "account": {"id": bank_id},
                "amountGross": -voucher_amount,
                "amountGrossCurrency": -voucher_amount,
                "description": f"Betaling - {linked_value or dim_name}",
                "row": 2,
            }

            # Link dimension value to both postings
            if dim_field and dim_value_id:
                debit_posting[dim_field] = {"id": dim_value_id}
                credit_posting[dim_field] = {"id": dim_value_id}
                logger.info(f"Linking {dim_field}={dim_value_id} to both postings")

            postings = [debit_posting, credit_posting]

            try:
                result = await self.client.post("/ledger/voucher", {
                    "date": today,
                    "description": e.get("description") or f"Voucher with {dim_name}",
                    "postings": postings,
                })
                voucher_id = result["value"]["id"]
                logger.info(f"Created voucher id={voucher_id} linked to dimension value")
            except Exception as ex:
                logger.error(f"Voucher creation failed: {ex}")
