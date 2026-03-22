"""Handler for reversing a payment on an existing invoice."""
import logging
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.reverse_payment")


class ReversePaymentHandler(BaseHandler):
    """Find an existing invoice and reverse its payment with a negative amount."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        # Step 1: Find the customer — prefer org number (more precise than name)
        customer_name = e.get("customerName", "")
        customers = []

        if e.get("customerOrganizationNumber"):
            result = await self.client.get("/customer", params={
                "organizationNumber": e["customerOrganizationNumber"],
                "fields": "id,name",
                "count": 5,
            })
            customers = result.get("values", [])

        if not customers and customer_name:
            result = await self.client.get("/customer", params={
                "name": customer_name,
                "fields": "id,name",
                "count": 5,
            })
            customers = result.get("values", [])

        if not customers:
            logger.error(f"No customer found: {customer_name}")
            return

        customer_id = customers[0]["id"]
        logger.info(f"Found customer id={customer_id}")

        # Step 2: Find the invoice for this customer
        result = await self.client.get("/invoice", params={
            "invoiceDateFrom": "2026-01-01",
            "invoiceDateTo": "2026-12-31",
            "customerId": customer_id,
            "fields": "id,invoiceNumber,amount,amountOutstanding",
            "count": 10,
        })
        invoices = result.get("values", [])

        if not invoices:
            logger.error(f"No invoices found for customer {customer_id}")
            return

        # Find the CORRECT invoice — match by amount if possible
        expected_amount = e.get("amount", 0)
        target = None

        # First try: match paid invoice by amount (excl VAT → incl VAT)
        for inv in invoices:
            outstanding = inv.get("amountOutstanding", inv.get("amount", 0))
            inv_amount = inv.get("amount", 0)
            if outstanding == 0 or outstanding == 0.0:
                # Check if amount matches (with or without VAT)
                if expected_amount and inv_amount:
                    if (abs(inv_amount - expected_amount) < 1 or
                        abs(inv_amount - expected_amount * 1.25) < 1 or
                        abs(inv_amount - expected_amount * 1.15) < 1 or
                        abs(inv_amount - expected_amount * 1.12) < 1):
                        target = inv
                        break

        # Second try: any paid invoice
        if not target:
            for inv in invoices:
                outstanding = inv.get("amountOutstanding", inv.get("amount", 0))
                if outstanding == 0 or outstanding == 0.0:
                    target = inv
                    break

        # Fallback: first invoice
        if not target:
            target = invoices[0]

        invoice_id = target["id"]
        # Use the INVOICE amount (includes VAT), not the prompt amount (excl. VAT)
        # The payment was for the full invoice amount
        amount = abs(target.get("amount", e.get("amount", 0)))
        logger.info(f"Found invoice id={invoice_id} amount={amount}")

        # Step 3: Get payment type
        pt_result = await self.client.get("/invoice/paymentType", params={
            "fields": "id,description", "count": 10,
        })
        payment_types = pt_result.get("values", [])
        payment_type_id = payment_types[0]["id"] if payment_types else 0
        for pt in payment_types:
            if "bank" in (pt.get("description") or "").lower():
                payment_type_id = pt["id"]
                break

        # Step 4: Reverse payment with negative amount
        await self.client.put(
            f"/invoice/{invoice_id}/:payment",
            {},
            params={
                "paymentDate": e.get("paymentDate") or today,
                "paymentTypeId": payment_type_id,
                "paidAmount": -amount,
            },
        )
        logger.info(f"Payment reversed: -{amount} on invoice {invoice_id}")
