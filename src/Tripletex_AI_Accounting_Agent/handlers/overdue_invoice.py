"""Handler for overdue invoice tasks — find overdue, post reminder fee, partial payment."""
import logging
from datetime import date, timedelta

from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.overdue_invoice")


class OverdueInvoiceHandler(BaseHandler):
    """Find overdue invoice, post reminder fee, create reminder invoice, register partial payment."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()
        account_ctx = e.get("_account", {})

        # Step 0: Bank account setup
        await ensure_bank_account(self.client, account_ctx)

        # Step 1: Find the overdue invoice (GET is free)
        r = await self.client.get("/invoice", params={
            "invoiceDateFrom": "2025-01-01", "invoiceDateTo": today,
            "fields": "id,invoiceNumber,invoiceDate,invoiceDueDate,amount,amountOutstanding,amountCurrency,customer",
            "count": 50,
        })
        invoices = r.get("values", [])

        # Find overdue: past due date AND has outstanding balance
        overdue = None
        for inv in invoices:
            outstanding = inv.get("amountOutstanding", 0)
            due_date = inv.get("invoiceDueDate", "9999-12-31")
            if outstanding > 0 and due_date < today:
                overdue = inv
                break

        # Fallback: any invoice with outstanding balance
        if not overdue:
            for inv in invoices:
                if inv.get("amountOutstanding", 0) > 0:
                    overdue = inv
                    break

        if not overdue:
            logger.error("No overdue invoice found")
            return

        overdue_id = overdue["id"]
        customer = overdue.get("customer", {})
        customer_id = customer.get("id")
        customer_name = customer.get("name", "Kunde")
        outstanding = overdue.get("amountOutstanding", 0)
        logger.info(f"Found overdue invoice id={overdue_id}, customer={customer_name}, outstanding={outstanding}")

        # Step 2: Get account IDs for 1500 and 3400 (GETs are free)
        debit_acc = e.get("debitAccount", "1500")
        credit_acc = e.get("creditAccount", "3400")
        debit_id = await self._get_account_id(debit_acc)
        credit_id = await self._get_account_id(credit_acc)

        reminder_fee = e.get("reminderFee", 50)

        # Step 3: Post reminder fee voucher
        if debit_id and credit_id:
            voucher_body = {
                "date": today,
                "description": f"Purregebyr faktura {overdue.get('invoiceNumber', overdue_id)}",
                "postings": [
                    {
                        "row": 1,
                        "account": {"id": debit_id},
                        "customer": {"id": customer_id},
                        "amountGross": reminder_fee,
                        "amountGrossCurrency": reminder_fee,
                        "description": "Purregebyr",
                    },
                    {
                        "row": 2,
                        "account": {"id": credit_id},
                        "amountGross": -reminder_fee,
                        "amountGrossCurrency": -reminder_fee,
                        "description": "Purregebyr",
                    },
                ],
            }
            try:
                result = await self.client.post("/ledger/voucher", voucher_body)
                logger.info(f"Posted reminder fee voucher: {reminder_fee} kr")
            except Exception as ex:
                logger.warning(f"Reminder fee voucher failed: {ex}")

        # Step 4: Create reminder invoice (order → invoice → send)
        if customer_id:
            order_body = {
                "customer": {"id": customer_id},
                "orderDate": today,
                "deliveryDate": today,
                "orderLines": [{
                    "description": "Purregebyr",
                    "count": 1,
                    "unitPriceExcludingVatCurrency": reminder_fee,
                    "vatType": {"id": 0},  # No VAT on reminder fees
                }],
            }
            try:
                order_result = await self.client.post("/order", order_body)
                order_id = order_result["value"]["id"]

                due_date = (date.today() + timedelta(days=14)).isoformat()
                inv_body = {
                    "invoiceDate": today,
                    "invoiceDueDate": due_date,
                    "customer": {"id": customer_id},
                    "orders": [{"id": order_id}],
                }
                inv_result = await self.client.post("/invoice", inv_body)
                reminder_inv_id = inv_result["value"]["id"]
                logger.info(f"Created reminder invoice id={reminder_inv_id}")

                # Send the reminder invoice
                if e.get("sendReminder", True):
                    try:
                        await self.client.put(
                            f"/invoice/{reminder_inv_id}/:send", {},
                            params={"sendType": "EMAIL", "overrideEmailAddress": ""},
                        )
                        logger.info("Reminder invoice sent")
                    except Exception:
                        pass

            except Exception as ex:
                logger.warning(f"Reminder invoice creation failed: {ex}")

        # Step 5: Register partial payment on the overdue invoice
        partial_amount = e.get("partialPaymentAmount", 0)
        if partial_amount > 0:
            # Get payment type
            pt_result = await self.client.get("/invoice/paymentType", params={
                "fields": "id,description", "count": 10,
            })
            payment_types = pt_result.get("values", [])
            payment_type_id = payment_types[0]["id"] if payment_types else 0
            for pt in payment_types:
                desc = (pt.get("description") or "").lower()
                if "innbetaling" in desc or "bank" in desc:
                    payment_type_id = pt["id"]
                    break

            try:
                await self.client.put(
                    f"/invoice/{overdue_id}/:payment", {},
                    params={
                        "paymentDate": today,
                        "paymentTypeId": payment_type_id,
                        "paidAmount": partial_amount,
                    },
                )
                logger.info(f"Registered partial payment: {partial_amount} kr on invoice {overdue_id}")
            except Exception as ex:
                logger.warning(f"Partial payment failed: {ex}")

        logger.info("Overdue invoice handler completed")

    async def _get_account_id(self, number: str):
        """Get ledger account ID by number."""
        if not hasattr(self, "_account_cache"):
            self._account_cache = {}
        if number in self._account_cache:
            return self._account_cache[number]
        r = await self.client.get("/ledger/account", params={
            "number": str(number), "fields": "id,number", "count": 1,
        })
        vals = r.get("values", [])
        if vals:
            self._account_cache[number] = vals[0]["id"]
            return vals[0]["id"]
        return None
