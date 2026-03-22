import logging
from datetime import date, timedelta

from handlers.base import BaseHandler
from handlers.order_utils import build_order_lines
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.invoice")


async def ensure_bank_account(client, account_ctx: dict = None) -> None:
    """Ensure the company has a bank account number on account 1920 (required for invoicing).
    Uses pre-scanned context if available to skip the GET (GETs are free but saves time)."""
    # Check pre-scanned context first — only skip if explicitly False (not missing)
    if account_ctx and account_ctx.get("bank_needs_setup") is False:
        logger.info("Bank account already set (from scan)")
        return

    bank = account_ctx.get("bank_account") if account_ctx else None
    if not bank:
        result = await client.get("/ledger/account", params={
            "number": "1920",
            "fields": "id,number,name,bankAccountNumber",
            "count": 1,
        })
        accounts = result.get("values", [])
        bank = accounts[0] if accounts else None

    if bank and not bank.get("bankAccountNumber"):
        bank["bankAccountNumber"] = "86011117947"
        await client.put(f"/ledger/account/{bank['id']}", bank)
        logger.info("Set bank account number on account 1920")
    return

    # Fallback: find any bank account
    result = await client.get("/ledger/account", params={
        "isBankAccount": "true",
        "fields": "id,number,bankAccountNumber",
        "count": 5,
    })
    for acc in result.get("values", []):
        if not acc.get("bankAccountNumber"):
            acc["bankAccountNumber"] = "86011117947"
            await client.put(f"/ledger/account/{acc['id']}", acc)
            logger.info(f"Set bank account number on account {acc['number']}")
            return


class CreateInvoiceHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()
        account_ctx = e.get("_account", {})

        # Step 0: Ensure company has a bank account (uses scan to skip GET)
        await ensure_bank_account(self.client, account_ctx)

        # Step 1: Find or create customer (competition pre-creates customers + products)
        customer_name = e.get("customerName", "Customer")
        customer_id = None

        # Search first (GETs are free)
        try:
            search_params = {"fields": "id,name,organizationNumber", "count": 5}
            if e.get("customerOrganizationNumber"):
                search_params["organizationNumber"] = e["customerOrganizationNumber"]
            else:
                search_params["name"] = customer_name
            result = await self.client.get("/customer", params=search_params)
            for c in result.get("values", []):
                customer_id = c["id"]
                break
        except Exception:
            pass

        if not customer_id:
            customer_body = {
                "name": customer_name,
                "isCustomer": True,
            }
            if e.get("customerEmail"):
                customer_body["email"] = e["customerEmail"]
                customer_body["invoiceEmail"] = e["customerEmail"]
            if e.get("customerOrganizationNumber"):
                customer_body["organizationNumber"] = e["customerOrganizationNumber"]
            cust_result = await self.client.post("/customer", customer_body)
            customer_id = cust_result["value"]["id"]

        logger.info(f"Using customer id={customer_id}")

        # Step 2: Build order lines (creates products if they have numbers)
        order_lines = await build_order_lines(self.client, e)

        # Step 3: Create order
        order_body = {
            "customer": {"id": customer_id},
            "orderDate": e.get("invoiceDate") or today,
            "deliveryDate": e.get("invoiceDate") or today,
            "orderLines": order_lines,
        }

        order_result = await self.client.post("/order", order_body)
        order_id = order_result["value"]["id"]
        logger.info(f"Created order id={order_id}")

        # Step 4: Create invoice (default due date = invoice date + 14 days)
        invoice_date = e.get("invoiceDate") or today
        default_due = (date.fromisoformat(invoice_date) + timedelta(days=14)).isoformat()
        invoice_body = {
            "invoiceDate": invoice_date,
            "invoiceDueDate": e.get("dueDate") or default_due,
            "customer": {"id": customer_id},
            "orders": [{"id": order_id}],
        }

        inv_result = await self.client.post("/invoice", invoice_body)
        invoice_id = inv_result["value"]["id"]
        logger.info(f"Created invoice id={invoice_id}")

        # Step 5: Register payment if requested
        if e.get("registerPayment"):
            # Use the INVOICE amount (incl. VAT), not order line sum (excl. VAT)
            inv_data = inv_result.get("value", {})
            amount = inv_data.get("amount", 0)  # Tripletex returns total incl. VAT
            if not amount:
                amount = e.get("amount") or e.get("totalAmount") or 0
            if not amount:
                for line in e.get("orderLines", []):
                    amount += line.get("unitPrice", 0) * line.get("quantity", 1)

            pt_result = await self.client.get("/invoice/paymentType", params={
                "fields": "id,description", "count": 10,
            })
            payment_types = pt_result.get("values", [])
            payment_type_id = payment_types[0]["id"] if payment_types else 0
            for pt in payment_types:
                if "bank" in (pt.get("description") or "").lower():
                    payment_type_id = pt["id"]
                    break

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

        # Send invoice
        try:
            await self.client.put(
                f"/invoice/{invoice_id}/:send", {},
                params={"sendType": "EMAIL", "overrideEmailAddress": ""},
            )
            logger.info(f"Invoice {invoice_id} sent")
        except Exception:
            logger.debug("Invoice send skipped")
