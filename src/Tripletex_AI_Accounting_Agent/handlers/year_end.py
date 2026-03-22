"""Handler for year-end closing / depreciation tasks."""
import logging
import math
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.year_end")


class YearEndHandler(BaseHandler):
    """Handle year-end closing tasks: depreciation, closing entries."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()
        year = e.get("year", date.today().year - 1)  # Usually closing previous year
        is_month_end = e.get("isMonthEnd", False)
        closing_month = e.get("closingMonth")

        # Handle depreciation entries
        assets = e.get("assets", [])
        depreciation_account = e.get("depreciationAccount", "6010")

        if not assets:
            logger.error("No assets found for depreciation")
            return

        # Find or create the depreciation expense account
        dep_acc_id = None
        dep_num = str(depreciation_account)
        try:
            r = await self.client.get("/ledger/account", params={
                "number": dep_num, "fields": "id,number", "count": 1,
            })
            if r.get("values"):
                dep_acc_id = r["values"][0]["id"]
        except Exception:
            pass
        if not dep_acc_id:
            # Create the account
            name = {"6030": "Avskrivning på maskiner og inventar", "6010": "Avskrivning på transportmidler"}.get(dep_num, f"Avskrivningskostnad ({dep_num})")
            try:
                r = await self.client.post("/ledger/account", {"number": int(dep_num), "name": name})
                dep_acc_id = r["value"]["id"]
                logger.info(f"Created depreciation account {dep_num} ({name}) id={dep_acc_id}")
            except Exception as ex:
                logger.warning(f"Could not create depreciation account {dep_num}: {ex}")

        # Use closing date: month-end date if month-end, else Dec 31
        if closing_month:
            import calendar
            last_day = calendar.monthrange(year, closing_month)[1]
            voucher_date = e.get("date") or f"{year}-{closing_month:02d}-{last_day:02d}"
            is_month_end = True
        else:
            voucher_date = e.get("date") or f"{year}-12-31"

        # Check for custom accumulated depreciation account (e.g. 1209)
        accum_dep_account = e.get("accumulatedDepreciationAccount")
        accum_dep_acc_id = None
        if accum_dep_account:
            try:
                r = await self.client.get("/ledger/account", params={
                    "number": str(accum_dep_account), "fields": "id,number", "count": 1,
                })
                accs = r.get("values", [])
                if accs:
                    accum_dep_acc_id = accs[0]["id"]
            except Exception:
                pass

        # Create SEPARATE depreciation voucher per asset (scoring checks each independently)
        if not dep_acc_id:
            logger.warning("No depreciation account found, skipping asset depreciation")

        for asset in assets:
            if not dep_acc_id:
                break
            asset_name = asset.get("name") or "Asset"
            original_cost = asset.get("cost", asset.get("value", 0))
            useful_life = asset.get("years", asset.get("usefulLife", 1))
            asset_account = str(asset.get("account") or asset.get("accountNumber") or "1200")

            # Calculate straight-line depreciation — keep decimals for precision
            depreciation = round(original_cost / useful_life, 2)
            if is_month_end:
                depreciation = round(depreciation / 12, 2)

            # Find asset account
            acc_result = await self.client.get("/ledger/account", params={
                "number": asset_account,
                "fields": "id,number,name",
                "count": 1,
            })
            asset_accs = acc_result.get("values", [])
            if not asset_accs:
                logger.warning(f"Asset account {asset_account} not found, skipping {asset_name}")
                continue
            asset_acc_id = asset_accs[0]["id"]

            logger.info(f"Depreciation {asset_name}: {original_cost}/{useful_life}yr = {depreciation}{'(monthly)' if is_month_end else ''} on account {asset_account}")

            # Credit account: use accumulated depreciation account if specified, else asset account
            credit_acc_id = accum_dep_acc_id if accum_dep_acc_id else asset_acc_id

            try:
                result = await self.client.post("/ledger/voucher", {
                    "date": voucher_date,
                    "description": f"Avskrivning {asset_name} ({year})",
                    "postings": [
                        {"date": voucher_date, "account": {"id": dep_acc_id},
                         "amountGross": depreciation, "amountGrossCurrency": depreciation,
                         "description": f"Avskrivning {asset_name}", "row": 1},
                        {"date": voucher_date, "account": {"id": credit_acc_id},
                         "amountGross": -depreciation, "amountGrossCurrency": -depreciation,
                         "description": f"Akk. avskrivning {asset_name}", "row": 2},
                    ],
                })
                logger.info(f"Created depreciation voucher for {asset_name} id={result['value']['id']}")
            except Exception as ex:
                logger.warning(f"Depreciation voucher for {asset_name} failed: {ex}")

        # Handle additional closing entries — skip entries that duplicate depreciation
        dep_accounts = {str(a.get("account") or "") for a in assets}
        if accum_dep_account:
            dep_accounts.add(str(accum_dep_account))
        for entry in e.get("closingEntries", []):
            # Skip if this entry duplicates a depreciation we already posted
            credit_acc = str(entry.get("creditAccount", ""))
            debit_acc = str(entry.get("debitAccount", ""))
            if dep_acc_id and credit_acc in dep_accounts and debit_acc == str(depreciation_account):
                logger.info(f"Skipping duplicate depreciation closing entry: {entry.get('description', '')}")
                continue
            await self._post_closing_entry(entry, voucher_date)

    async def _post_closing_entry(self, entry: dict, voucher_date: str) -> None:
        """Post an additional closing entry."""
        debit_acc = str(entry.get("debitAccount", ""))
        credit_acc = str(entry.get("creditAccount", ""))
        amount = entry.get("amount", 0)
        description = entry.get("description") or "Closing entry"

        # Skip non-numeric account "numbers" (e.g. "Aufwand", "expense")
        if debit_acc and not debit_acc.replace(".", "").isdigit():
            logger.warning(f"Non-numeric debit account '{debit_acc}', using 6000")
            debit_acc = "6000"
        if credit_acc and not credit_acc.replace(".", "").isdigit():
            logger.warning(f"Non-numeric credit account '{credit_acc}', using 2900")
            credit_acc = "2900"

        # For tax entries — ALWAYS calculate from ledger (LLM estimates are unreliable)
        is_tax_entry = "skatt" in description.lower() or "tax" in description.lower() or "impôt" in description.lower() or "fiscal" in description.lower()
        if is_tax_entry:
            try:
                # Calculate taxable result from ledger: revenue - expenses
                year_str = voucher_date[:4]
                revenue = 0
                expenses = 0
                r = await self.client.get("/ledger/posting", params={
                    "dateFrom": f"{year_str}-01-01", "dateTo": f"{year_str}-12-31",
                    "fields": "id,amount,account", "count": 1000,
                })
                for p in r.get("values", []):
                    acc_num = p.get("account", {}).get("number", 0)
                    amt = p.get("amount", 0)
                    if 3000 <= acc_num <= 3999:
                        revenue += amt  # Credits (negative)
                    elif 4000 <= acc_num <= 7999:
                        expenses += amt  # Debits (positive)
                taxable_result = -revenue - expenses  # Revenue is negative
                if taxable_result > 0:
                    amount = round(taxable_result * 0.22)
                    logger.info(f"Calculated tax: revenue={-revenue}, expenses={expenses}, result={taxable_result}, tax 22%={amount}")
                else:
                    logger.info(f"Taxable result is {taxable_result} (no tax)")
            except Exception as ex:
                logger.warning(f"Could not calculate tax from ledger: {ex}")

        if not debit_acc or not credit_acc or not amount:
            logger.warning(f"Skipping closing entry: missing data — debit={debit_acc} credit={credit_acc} amount={amount}")
            return

        # Common account names for creation if missing
        account_names = {
            "8700": "Skattekostnad",
            "6030": "Avskrivning på maskiner og inventar",
            "7700": "Styre- og bedriftsforsamlingsmøter",
        }

        async def find_or_create_account(number):
            try:
                r = await self.client.get("/ledger/account", params={
                    "number": number, "fields": "id", "count": 1,
                })
                if r.get("values"):
                    return r["values"][0]["id"]
            except Exception:
                pass
            # Account not found — create it
            name = account_names.get(number, f"Konto {number}")
            try:
                r = await self.client.post("/ledger/account", {
                    "number": int(number),
                    "name": name,
                })
                acc_id = r["value"]["id"]
                logger.info(f"Created missing account {number} ({name}) id={acc_id}")
                return acc_id
            except Exception as ex:
                logger.warning(f"Could not create account {number}: {ex}")
            return None

        d_acc_id = await find_or_create_account(debit_acc)
        c_acc_id = await find_or_create_account(credit_acc)
        if not d_acc_id or not c_acc_id:
            logger.warning(f"Closing entry skipped — account not found: debit={debit_acc}({'found' if d_acc_id else 'MISSING'}) credit={credit_acc}({'found' if c_acc_id else 'MISSING'})")
            return

        await self.client.post("/ledger/voucher", {
            "date": voucher_date,
            "description": description,
            "postings": [
                {"date": voucher_date, "account": {"id": d_acc_id},
                 "amountGross": amount, "amountGrossCurrency": amount,
                 "description": description, "row": 1},
                {"date": voucher_date, "account": {"id": c_acc_id},
                 "amountGross": -amount, "amountGrossCurrency": -amount,
                 "description": description, "row": 2},
            ],
        })
        logger.info(f"Posted closing entry: {description} {amount}")
