"""Handler for incoming/supplier invoices."""
import logging
from datetime import date

from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.supplier_invoice")


class CreateSupplierInvoiceHandler(BaseHandler):
    """Register an incoming/supplier invoice. Falls back to manual voucher if API fails."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        await ensure_bank_account(self.client)

        # Find or create supplier (competition may pre-create suppliers)
        supplier_name = e.get("supplierName", e.get("customerName", "Supplier"))
        supplier_id = None

        # Search first (GETs are free)
        try:
            params = {"fields": "id,name,organizationNumber", "count": 5}
            if e.get("organizationNumber"):
                params["organizationNumber"] = e["organizationNumber"]
            else:
                params["name"] = supplier_name
            result = await self.client.get("/customer", params=params)
            for c in result.get("values", []):
                supplier_id = c["id"]
                logger.info(f"Found existing supplier id={supplier_id}")
                break
        except Exception:
            pass

        if not supplier_id:
            supplier_body = {
                "name": supplier_name,
                "isSupplier": True,
                "isCustomer": True,
            }
            if e.get("organizationNumber"):
                supplier_body["organizationNumber"] = e["organizationNumber"]
            if e.get("email"):
                supplier_body["email"] = e["email"]
                supplier_body["invoiceEmail"] = e["email"]
            if e.get("address") or e.get("postalAddress"):
                addr = e.get("address") or e.get("postalAddress") or ""
                supplier_body["postalAddress"] = {
                    "addressLine1": addr,
                    "postalCode": e.get("postalCode") or "",
                    "city": e.get("city") or "",
                }
            sup_result = await self.client.post("/customer", supplier_body)
            supplier_id = sup_result["value"]["id"]
            logger.info(f"Created supplier id={supplier_id}")

        amount = e.get("amount", e.get("totalAmount", 0))

        # Check if supplier already has existing vouchers or invoices we should reference
        # GETs are free — look for pre-created data
        try:
            existing = await self.client.get("/ledger/voucher", params={
                "dateFrom": "2026-01-01", "dateTo": "2026-12-31",
                "supplierId": supplier_id,
                "fields": "id,number,date,description",
                "count": 5,
            })
            if existing.get("values"):
                logger.info(f"Found {len(existing['values'])} existing vouchers for supplier {supplier_id}")
                # If vouchers already exist, the invoice may already be registered
                for v in existing.get("values", []):
                    logger.info(f"  Existing voucher: {v.get('description', '')[:60]}")
        except Exception:
            pass

        # Try GET on incomingInvoice (BETA for POST, but GET might work)
        try:
            incoming = await self.client.get("/incomingInvoice", params={
                "supplierId": supplier_id,
                "fields": "id,invoiceNumber,invoiceDate,dueDate,amount",
                "count": 5,
            })
            incoming_list = incoming.get("values", [])
            if incoming_list:
                logger.info(f"Found {len(incoming_list)} incoming invoices for supplier")
                for inv in incoming_list:
                    logger.info(f"  Incoming invoice: {inv}")
        except Exception:
            pass

        # POST /incomingInvoice is [BETA] — always 403. Use manual voucher directly.
        # Create manual voucher
        # Debit expense account, credit supplier account (2400)
        expense_acc_id = None
        supplier_acc_id = None

        # Find expense account (from prompt or default 6590)
        acc_num = e.get("accountNumber", "6590")
        result = await self.client.get("/ledger/account", params={
            "number": str(acc_num), "fields": "id,number", "count": 1,
        })
        accs = result.get("values", [])
        if accs:
            expense_acc_id = accs[0]["id"]

        # Find accounts payable (2400)
        result = await self.client.get("/ledger/account", params={
            "number": "2400", "fields": "id,number", "count": 1,
        })
        accs = result.get("values", [])
        if accs:
            supplier_acc_id = accs[0]["id"]

        if expense_acc_id and supplier_acc_id:
            # Calculate VAT split if VAT rate is specified
            vat_rate = e.get("vatRate", 25)  # Default 25%
            gross_amount = amount  # Amount incl. VAT (TTC)
            net_amount = round(gross_amount / (1 + vat_rate / 100))
            vat_amount = gross_amount - net_amount

            postings = []
            row = 1
            voucher_date = e.get("invoiceDate") or today

            # Debit expense account (net amount excl. VAT)
            postings.append({
                "date": voucher_date,
                "account": {"id": expense_acc_id},
                "amountGross": net_amount, "amountGrossCurrency": net_amount,
                "description": e.get("description") or "Supplier expense",
                "row": row,
            })
            row += 1

            # Debit input VAT account (1610 = inngående MVA høy sats)
            if vat_amount > 0:
                vat_acc_id = None
                result = await self.client.get("/ledger/account", params={
                    "number": "1610", "fields": "id,number", "count": 1,
                })
                accs = result.get("values", [])
                if accs:
                    vat_acc_id = accs[0]["id"]

                if vat_acc_id:
                    postings.append({
                        "date": voucher_date,
                        "account": {"id": vat_acc_id},
                        "amountGross": vat_amount, "amountGrossCurrency": vat_amount,
                        "description": f"Inngående MVA {vat_rate}%",
                        "row": row,
                    })
                    row += 1

            # Credit accounts payable (gross amount) — MUST link supplier
            postings.append({
                "date": voucher_date,
                "account": {"id": supplier_acc_id},
                "supplier": {"id": supplier_id},
                "amountGross": -gross_amount, "amountGrossCurrency": -gross_amount,
                "description": f"Leverandørgjeld {supplier_name}",
                "row": row,
            })

            try:
                result = await self.client.post("/ledger/voucher", {
                    "date": voucher_date,
                    "description": f"Leverandørfaktura {supplier_name} {e.get('invoiceNumber', '')} - {e.get('description', '')}",
                    "postings": postings,
                })
                logger.info(f"Created supplier invoice voucher id={result['value']['id']} net={net_amount} vat={vat_amount} gross={gross_amount}")
            except Exception as ex:
                logger.error(f"Supplier invoice voucher failed: {ex}")
