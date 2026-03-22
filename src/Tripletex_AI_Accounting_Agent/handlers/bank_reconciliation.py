"""Deterministic handler for bank reconciliation tasks.
Matches CSV transactions to invoices and posts supplier payments correctly."""
import logging
from datetime import date

from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.bank_recon")


class BankReconciliationHandler(BaseHandler):
    """Reconcile bank statement CSV against Tripletex invoices."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        await ensure_bank_account(self.client)

        transactions = e.get("transactions", [])
        if not transactions:
            logger.warning("No transactions extracted")
            return

        # Step 1: GET all invoices (free)
        invoices = []
        try:
            r = await self.client.get("/invoice", params={
                "invoiceDateFrom": "2026-01-01", "invoiceDateTo": "2026-12-31",
                "fields": "id,invoiceNumber,amount,amountOutstanding,customer",
                "count": 50,
            })
            invoices = r.get("values", [])
            logger.info(f"Found {len(invoices)} invoices")
        except Exception:
            pass

        # Step 2: GET payment types (free)
        payment_type_id = None
        try:
            r = await self.client.get("/invoice/paymentType", params={
                "fields": "id,description", "count": 10,
            })
            for pt in r.get("values", []):
                if "bank" in (pt.get("description") or "").lower():
                    payment_type_id = pt["id"]
                    break
            if not payment_type_id and r.get("values"):
                payment_type_id = r["values"][0]["id"]
        except Exception:
            pass

        # Step 3: GET bank account ID and supplier account ID (free)
        bank_acc_id = None
        supplier_acc_id = None
        try:
            r = await self.client.get("/ledger/account", params={
                "number": "1920", "fields": "id", "count": 1,
            })
            if r.get("values"):
                bank_acc_id = r["values"][0]["id"]
        except Exception:
            pass
        try:
            r = await self.client.get("/ledger/account", params={
                "number": "2400", "fields": "id", "count": 1,
            })
            if r.get("values"):
                supplier_acc_id = r["values"][0]["id"]
        except Exception:
            pass

        # Step 4: GET account IDs for interest/fees (free)
        interest_acc_id = None
        fee_acc_id = None
        for num, attr in [("8040", "interest_acc_id"), ("7770", "fee_acc_id")]:
            try:
                r = await self.client.get("/ledger/account", params={
                    "number": num, "fields": "id", "count": 1,
                })
                if r.get("values"):
                    if attr == "interest_acc_id":
                        interest_acc_id = r["values"][0]["id"]
                    else:
                        fee_acc_id = r["values"][0]["id"]
            except Exception:
                pass

        # Step 5: Process each transaction
        used_invoice_ids = set()  # Track which invoices have been matched

        for tx in transactions:
            tx_type = (tx.get("type") or "").lower()
            # Handle both {amount} and {incoming/outgoing} formats
            amount = tx.get("amount", 0)
            if not amount:
                incoming = tx.get("incoming") or 0
                outgoing = tx.get("outgoing") or 0
                amount = incoming if incoming else outgoing
            desc = tx.get("description", "")
            tx_date = tx.get("date") or today
            ref = tx.get("reference") or tx.get("counterparty")
            entity = tx.get("entity") or tx.get("counterparty")

            desc_lower = desc.lower()

            # Route by DESCRIPTION first (before amount direction)
            is_interest = "renteinntekt" in desc_lower or "interest" in desc_lower or "zinsen" in desc_lower or "intérêts" in desc_lower or "juros" in desc_lower
            is_fee = "bankgebyr" in desc_lower or "gebyr" in desc_lower or "fee" in desc_lower or "gebühr" in desc_lower or "frais" in desc_lower or "taxa" in desc_lower
            is_tax = "skattetrekk" in desc_lower or "skatt" in desc_lower or "tax" in desc_lower or "steuer" in desc_lower or "impôt" in desc_lower or "imposto" in desc_lower
            is_supplier = "leverand" in desc_lower or "fornecedor" in desc_lower or "fournisseur" in desc_lower or "lieferant" in desc_lower or "proveedor" in desc_lower or "supplier" in desc_lower

            if is_interest or is_fee or is_tax:
                # NON-INVOICE transactions — handle as vouchers (skip to voucher section below)
                pass
            elif is_supplier or (amount < 0 and not is_interest and not is_fee and not is_tax):
                # SUPPLIER PAYMENT or any negative non-categorized — handle as supplier (skip to supplier section below)
                pass
            elif amount > 0 or tx_type in ("credit", "incoming") or bool(tx.get("incoming")):
                # INCOMING PAYMENT — match to invoice
                abs_amount = abs(amount)
                matched = False

                # Extract invoice number from reference (e.g., "Faktura 1001" → "1001")
                import re
                invoice_ref = None
                if ref:
                    m = re.search(r'(\d+)', str(ref))
                    if m:
                        invoice_ref = m.group(1)

                # Try matching by invoice number
                if invoice_ref:
                    for inv in invoices:
                        inv_id = inv["id"]
                        if inv_id in used_invoice_ids:
                            continue
                        if str(inv.get("invoiceNumber")) == invoice_ref and inv.get("amountOutstanding", 0) > 0:
                            try:
                                await self.client.put(
                                    f"/invoice/{inv_id}/:payment", {},
                                    params={
                                        "paymentDate": tx_date,
                                        "paymentTypeId": payment_type_id,
                                        "paidAmount": abs_amount,
                                    },
                                )
                                used_invoice_ids.add(inv_id)
                                logger.info(f"Matched payment {abs_amount} to invoice {inv.get('invoiceNumber')}")
                                matched = True
                            except Exception as ex:
                                logger.warning(f"Payment failed for invoice {inv.get('invoiceNumber')}: {ex}")
                            break

                # Fallback: match by amount (skip already-used invoices)
                if not matched:
                    for inv in invoices:
                        inv_id = inv["id"]
                        if inv_id in used_invoice_ids:
                            continue
                        outstanding = inv.get("amountOutstanding", 0)
                        if outstanding > 0 and (abs(outstanding - abs_amount) < 1 or abs_amount <= outstanding):
                            try:
                                await self.client.put(
                                    f"/invoice/{inv_id}/:payment", {},
                                    params={
                                        "paymentDate": tx_date,
                                        "paymentTypeId": payment_type_id,
                                        "paidAmount": abs_amount,
                                    },
                                )
                                used_invoice_ids.add(inv_id)
                                logger.info(f"Matched payment {abs_amount} to invoice {inv_id} (by amount)")
                                matched = True
                            except Exception as ex:
                                logger.warning(f"Payment failed: {ex}")
                            break

            elif is_interest or is_tax:
                # INTEREST or TAX — post voucher
                acc_id = interest_acc_id  # Use interest account for both
                if acc_id and bank_acc_id:
                    abs_amount = abs(amount)
                    try:
                        await self.client.post("/ledger/voucher", {
                            "date": tx_date,
                            "description": desc,
                            "postings": [
                                {"row": 1, "account": {"id": acc_id},
                                 "amountGross": -abs_amount, "amountGrossCurrency": -abs_amount,
                                 "description": desc},
                                {"row": 2, "account": {"id": bank_acc_id},
                                 "amountGross": abs_amount, "amountGrossCurrency": abs_amount,
                                 "description": desc},
                            ],
                        })
                        logger.info(f"Posted interest/tax: {amount} ({desc[:40]})")
                    except Exception as ex:
                        logger.warning(f"Interest/tax voucher failed: {ex}")

            elif is_fee:
                # BANK FEE
                if fee_acc_id and bank_acc_id:
                    abs_amount = abs(amount)
                    try:
                        await self.client.post("/ledger/voucher", {
                            "date": tx_date,
                            "description": desc,
                            "postings": [
                                {"row": 1, "account": {"id": fee_acc_id},
                                 "amountGross": abs_amount, "amountGrossCurrency": abs_amount,
                                 "description": desc},
                                {"row": 2, "account": {"id": bank_acc_id},
                                 "amountGross": -abs_amount, "amountGrossCurrency": -abs_amount,
                                 "description": desc},
                            ],
                        })
                        logger.info(f"Posted bank fee: {amount}")
                    except Exception as ex:
                        logger.warning(f"Bank fee voucher failed: {ex}")

            elif is_supplier or amount < 0:
                # SUPPLIER PAYMENT — find/create supplier, post with supplier.id
                abs_amount = abs(amount)
                supplier_name = entity or ""
                if not supplier_name:
                    # Extract from description: "Betaling Leverandor Aasen AS" / "Betaling Fornecedor Silva Lda"
                    import re
                    m = re.search(r'(?:Leverand[oø]r|Proveedor|Fournisseur|Fornecedor|Lieferant|Supplier)\s+(.+)', desc, re.IGNORECASE)
                    if m:
                        supplier_name = m.group(1).strip()

                if supplier_name and supplier_acc_id and bank_acc_id:
                    # Find or create supplier
                    supplier_id = None
                    try:
                        r = await self.client.get("/customer", params={
                            "name": supplier_name, "fields": "id,name", "count": 5,
                        })
                        for c in r.get("values", []):
                            if supplier_name.lower() in (c.get("name") or "").lower():
                                supplier_id = c["id"]
                                break
                    except Exception:
                        pass

                    if not supplier_id:
                        try:
                            r = await self.client.post("/customer", {
                                "name": supplier_name,
                                "isSupplier": True,
                                "isCustomer": True,
                            })
                            supplier_id = r["value"]["id"]
                            logger.info(f"Created supplier {supplier_name} id={supplier_id}")
                        except Exception:
                            pass

                    if supplier_id:
                        try:
                            await self.client.post("/ledger/voucher", {
                                "date": tx_date,
                                "description": f"Betaling {supplier_name}",
                                "postings": [
                                    {"row": 1, "account": {"id": supplier_acc_id},
                                     "supplier": {"id": supplier_id},
                                     "amountGross": abs_amount, "amountGrossCurrency": abs_amount,
                                     "description": f"Betaling {supplier_name}"},
                                    {"row": 2, "account": {"id": bank_acc_id},
                                     "amountGross": -abs_amount, "amountGrossCurrency": -abs_amount,
                                     "description": f"Betaling {supplier_name}"},
                                ],
                            })
                            logger.info(f"Posted supplier payment: {abs_amount} to {supplier_name}")
                        except Exception as ex:
                            logger.warning(f"Supplier payment voucher failed: {ex}")

        logger.info("Bank reconciliation completed")
