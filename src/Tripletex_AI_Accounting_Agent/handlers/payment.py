import logging
from datetime import date, timedelta

from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from handlers.order_utils import build_order_lines
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.payment")


class RegisterPaymentHandler(BaseHandler):
    """Register payment. Find existing invoice if pre-populated, otherwise create from scratch."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        await ensure_bank_account(self.client)

        invoice_id = None
        invoice_amount = None

        # Step 1: Try to find existing customer + invoice (competition pre-populates)
        customer_name = e.get("customerName", "")
        customer_id = None

        # Search by org number first (most precise)
        if e.get("customerOrganizationNumber"):
            try:
                result = await self.client.get("/customer", params={
                    "organizationNumber": e["customerOrganizationNumber"],
                    "fields": "id,name", "count": 5,
                })
                if result.get("values"):
                    customer_id = result["values"][0]["id"]
            except Exception:
                pass

        if not customer_id and customer_name:
            try:
                cust_result = await self.client.get("/customer", params={
                    "name": customer_name,
                    "fields": "id,name",
                    "count": 5,
                })
                customers = cust_result.get("values", [])
                if customers:
                    customer_id = customers[0]["id"]
            except Exception:
                pass

        if customer_id:
            try:
                inv_result = await self.client.get("/invoice", params={
                    "invoiceDateFrom": "2026-01-01",
                    "invoiceDateTo": "2026-12-31",
                    "customerId": customer_id,
                    "fields": "id,invoiceNumber,amount,amountOutstanding",
                    "count": 10,
                })
                invoices = inv_result.get("values", [])
                expected = e.get("amount", 0)
                best_match = None
                for inv in invoices:
                    outstanding = inv.get("amountOutstanding", 0)
                    if outstanding and outstanding > 0:
                        inv_amt = inv.get("amount", 0)
                        if expected and inv_amt:
                            if (abs(inv_amt - expected) < 1 or
                                abs(inv_amt - expected * 1.25) < 1 or
                                abs(inv_amt - expected * 1.15) < 1 or
                                abs(inv_amt - expected * 1.12) < 1):
                                best_match = inv
                                break
                        if not best_match:
                            best_match = inv
                if best_match:
                    invoice_id = best_match["id"]
                    invoice_amount = best_match["amount"]
                    logger.info(f"Found existing unpaid invoice id={invoice_id} amount={invoice_amount}")
            except Exception:
                pass

        # Step 2: If no existing invoice, create from scratch
        if not invoice_id:
            customer_body = {"name": customer_name or "Customer", "isCustomer": True}
            if e.get("customerOrganizationNumber"):
                customer_body["organizationNumber"] = e["customerOrganizationNumber"]
            if e.get("customerEmail"):
                customer_body["email"] = e["customerEmail"]
                customer_body["invoiceEmail"] = e["customerEmail"]

            cust_result = await self.client.post("/customer", customer_body)
            customer_id = cust_result["value"]["id"]
            logger.info(f"Created customer id={customer_id}")

            order_lines = await build_order_lines(self.client, e)

            order_result = await self.client.post("/order", {
                "customer": {"id": customer_id},
                "orderDate": e.get("invoiceDate") or today,
                "deliveryDate": e.get("invoiceDate") or today,
                "orderLines": order_lines,
            })
            order_id = order_result["value"]["id"]

            invoice_date = e.get("invoiceDate") or today
            default_due = (date.fromisoformat(invoice_date) + timedelta(days=14)).isoformat()
            inv_result = await self.client.post("/invoice", {
                "invoiceDate": invoice_date,
                "invoiceDueDate": e.get("dueDate") or default_due,
                "customer": {"id": customer_id},
                "orders": [{"id": order_id}],
            })
            invoice_id = inv_result["value"]["id"]
            invoice_amount = inv_result["value"].get("amount", 0)
            logger.info(f"Created invoice id={invoice_id}")

        # Step 3: Find payment type
        pt_result = await self.client.get("/invoice/paymentType", params={
            "fields": "id,description", "count": 10,
        })
        payment_types = pt_result.get("values", [])
        payment_type_id = payment_types[0]["id"] if payment_types else 0
        for pt in payment_types:
            if "bank" in (pt.get("description") or "").lower():
                payment_type_id = pt["id"]
                break

        # Step 4: Register payment — use invoice amount (incl. VAT) if available
        amount = invoice_amount or e.get("amount", e.get("totalAmount", 0))
        if not amount:
            for line in e.get("orderLines", []):
                amount += line.get("unitPrice", 0) * line.get("quantity", 1)

        await self.client.put(
            f"/invoice/{invoice_id}/:payment",
            {},
            params={
                "paymentDate": e.get("paymentDate") or today,
                "paymentTypeId": payment_type_id,
                "paidAmount": amount,
            },
        )
        logger.info(f"Payment registered: {amount} on invoice {invoice_id}")
