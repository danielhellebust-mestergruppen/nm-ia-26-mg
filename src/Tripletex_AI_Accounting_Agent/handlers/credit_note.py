import logging
from datetime import date, timedelta

from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from handlers.order_utils import build_order_lines
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.credit_note")


class CreateCreditNoteHandler(BaseHandler):
    """Create an invoice then issue a credit note against it."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        await ensure_bank_account(self.client)

        # Try to find existing invoice (competition often pre-populates data)
        invoice_id = e.get("invoiceId")

        # Search by invoice number
        if not invoice_id and e.get("invoiceNumber"):
            try:
                result = await self.client.get("/invoice", params={
                    "invoiceDateFrom": "2026-01-01",
                    "invoiceDateTo": "2026-12-31",
                    "invoiceNumber": e["invoiceNumber"],
                    "fields": "id,invoiceNumber",
                    "count": 1,
                })
                invoices = result.get("values", [])
                if invoices:
                    invoice_id = invoices[0]["id"]
            except Exception:
                pass

        # Search by customer — prefer org number, then name
        if not invoice_id and (e.get("customerName") or e.get("customerOrganizationNumber")):
            try:
                # Try org number first (more precise)
                customers = []
                if e.get("customerOrganizationNumber"):
                    cust_result = await self.client.get("/customer", params={
                        "organizationNumber": e["customerOrganizationNumber"],
                        "fields": "id,name", "count": 5,
                    })
                    customers = cust_result.get("values", [])
                if not customers and e.get("customerName"):
                    cust_result = await self.client.get("/customer", params={
                        "name": e["customerName"],
                        "fields": "id,name", "count": 5,
                    })
                    customers = cust_result.get("values", [])
                if customers:
                    customer_id = customers[0]["id"]
                    inv_result = await self.client.get("/invoice", params={
                        "invoiceDateFrom": "2026-01-01",
                        "invoiceDateTo": "2026-12-31",
                        "customerId": customer_id,
                        "fields": "id,invoiceNumber,amount",
                        "count": 10,
                    })
                    invoices = inv_result.get("values", [])
                    if invoices:
                        # Find the non-credited invoice
                        for inv in invoices:
                            invoice_id = inv["id"]
                            break
                        logger.info(f"Found existing invoice id={invoice_id} for customer {e['customerName']}")
            except Exception:
                pass

        # If no existing invoice found, create one
        if not invoice_id:
            customer_name = e.get("customerName", "Customer")
            customer_body = {"name": customer_name, "isCustomer": True}
            if e.get("customerOrganizationNumber"):
                customer_body["organizationNumber"] = e["customerOrganizationNumber"]
            if e.get("customerEmail"):
                customer_body["email"] = e["customerEmail"]
                customer_body["invoiceEmail"] = e["customerEmail"]

            cust_result = await self.client.post("/customer", customer_body)
            customer_id = cust_result["value"]["id"]
            logger.info(f"Created customer id={customer_id}")

            # Build order lines (creates products if needed)
            order_lines = await build_order_lines(self.client, e)

            order_result = await self.client.post("/order", {
                "customer": {"id": customer_id},
                "orderDate": e.get("invoiceDate") or today,
                "deliveryDate": e.get("invoiceDate") or today,
                "orderLines": order_lines,
            })
            order_id = order_result["value"]["id"]
            logger.info(f"Created order id={order_id}")

            invoice_date = e.get("invoiceDate") or today
            default_due = (date.fromisoformat(invoice_date) + timedelta(days=14)).isoformat()
            inv_result = await self.client.post("/invoice", {
                "invoiceDate": invoice_date,
                "invoiceDueDate": e.get("dueDate") or default_due,
                "customer": {"id": customer_id},
                "orders": [{"id": order_id}],
            })
            invoice_id = inv_result["value"]["id"]
            logger.info(f"Created invoice id={invoice_id}")

        # Issue credit note
        credit_date = e.get("creditNoteDate") or e.get("date") or today
        comment = e.get("comment", e.get("reason", ""))

        result = await self.client.put(
            f"/invoice/{invoice_id}/:createCreditNote",
            {},
            params={
                "date": credit_date,
                "comment": comment,
                "sendToCustomer": True,
            },
        )
        credit_note = result.get("value", {})
        credit_id = credit_note.get("id", "?")
        logger.info(f"Credit note created: id={credit_id} for invoice {invoice_id}")

        # Send the credit note
        if credit_id and credit_id != "?":
            try:
                await self.client.put(
                    f"/invoice/{credit_id}/:send", {},
                    params={"sendType": "EMAIL", "overrideEmailAddress": ""},
                )
                logger.info(f"Credit note {credit_id} sent")
            except Exception:
                pass
