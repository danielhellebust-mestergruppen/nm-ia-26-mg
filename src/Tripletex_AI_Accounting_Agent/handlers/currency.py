"""Handler for currency exchange / disagio tasks."""
import logging
import math
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.currency")


class CurrencyPaymentHandler(BaseHandler):
    """Register payment with exchange rate difference (agio/disagio)."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()
        account_ctx = e.get("_account", {})

        # Find the customer and invoice
        customer_name = e.get("customerName", "")
        invoice_id = None
        invoice_amount = None

        # Search for customer — prefer org number (more precise)
        customer_id = None

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
            result = await self.client.get("/customer", params={
                "name": customer_name, "fields": "id,name", "count": 5,
            })
            cust_list = result.get("values", [])
            if cust_list:
                customer_id = cust_list[0]["id"]

        # Find unpaid invoice
        if customer_id:
            result = await self.client.get("/invoice", params={
                "invoiceDateFrom": "2026-01-01",
                "invoiceDateTo": "2026-12-31",
                "customerId": customer_id,
                "fields": "id,invoiceNumber,amount,amountOutstanding,amountCurrency",
                "count": 10,
            })
            invoices = result.get("values", [])
            for inv in invoices:
                if inv.get("amountOutstanding", 0) > 0:
                    invoice_id = inv["id"]
                    invoice_amount = inv["amount"]  # Amount in NOK at original rate
                    break

        if not invoice_id:
            logger.error(f"No unpaid invoice found for {customer_name}")
            return

        # Calculate amounts
        foreign_amount = e.get("foreignAmount", e.get("amount", 0))
        original_rate = e.get("originalRate", e.get("invoiceRate", 0))
        payment_rate = e.get("paymentRate", e.get("currentRate", 0))

        if foreign_amount and original_rate and payment_rate:
            original_nok = foreign_amount * original_rate
            payment_nok = foreign_amount * payment_rate
            exchange_diff = round(original_nok - payment_nok, 2)
        elif foreign_amount and not (original_rate and payment_rate):
            # Rates not in prompt — look up via currency API (GETs are free)
            try:
                currency_code = e.get("currency", "EUR")
                currencies = await self.client.get("/currency", params={
                    "code": currency_code, "fields": "id,code", "count": 1,
                })
                if currencies.get("values"):
                    curr_id = currencies["values"][0]["id"]
                    # Get current exchange rate
                    rate_result = await self.client.get(
                        f"/currency/{curr_id}/exchangeRate",
                        params={"date": today, "amount": 1},
                    )
                    current_rate = rate_result.get("value", 0)
                    if current_rate and not payment_rate:
                        payment_rate = current_rate
                        logger.info(f"Looked up current rate: 1 {currency_code} = {current_rate} NOK")
                    if original_rate and payment_rate:
                        original_nok = foreign_amount * original_rate
                        payment_nok = foreign_amount * payment_rate
                        exchange_diff = round(original_nok - payment_nok, 2)
                    elif payment_rate:
                        payment_nok = foreign_amount * payment_rate
                        exchange_diff = (invoice_amount or 0) - payment_nok
                    else:
                        payment_nok = invoice_amount or 0
                        exchange_diff = 0
                else:
                    payment_nok = invoice_amount or 0
                    exchange_diff = 0
            except Exception as ex:
                logger.warning(f"Currency lookup failed: {ex}")
                payment_nok = invoice_amount or 0
                exchange_diff = 0
        else:
            payment_nok = invoice_amount or 0
            exchange_diff = 0

        logger.info(f"Currency: {foreign_amount} × {original_rate} = {foreign_amount * original_rate if foreign_amount and original_rate else '?'} NOK (original)")
        logger.info(f"Currency: {foreign_amount} × {payment_rate} = {foreign_amount * payment_rate if foreign_amount and payment_rate else '?'} NOK (payment)")
        logger.info(f"Exchange diff: {exchange_diff} NOK")

        # Step 1: Register payment for the actual received amount
        pt_result = await self.client.get("/invoice/paymentType", params={
            "fields": "id,description", "count": 10,
        })
        payment_types = pt_result.get("values", [])
        payment_type_id = payment_types[0]["id"] if payment_types else 0
        for pt in payment_types:
            if "bank" in (pt.get("description") or "").lower():
                payment_type_id = pt["id"]
                break

        # Register payment at the original NOK rate to close the receivable correctly
        original_nok = round(foreign_amount * original_rate, 2) if foreign_amount and original_rate else 0
        payment_nok = round(foreign_amount * payment_rate, 2) if foreign_amount and payment_rate else 0

        # NOTE: invoice["amount"] is in the INVOICE CURRENCY (e.g. EUR incl VAT), NOT in NOK!
        # We must use our calculated original_nok for the payment amount
        payment_params = {
            "paymentDate": e.get("paymentDate") or today,
            "paymentTypeId": payment_type_id,
            "paidAmount": original_nok,  # NOK at original rate
        }
        if foreign_amount:
            payment_params["paidAmountCurrency"] = foreign_amount

        await self.client.put(
            f"/invoice/{invoice_id}/:payment",
            {},
            params=payment_params,
        )
        logger.info(f"Payment registered: {invoice_amount or original_nok} NOK ({foreign_amount} {e.get('currency','')}) on invoice {invoice_id}")

        # Step 2: Post exchange difference voucher
        # Norwegian accounting: 8060 = Valutagevinst (agio/gain), 8160 = Valutatap (disagio/loss)
        # exchange_diff = original_nok - payment_nok
        #   > 0 means loss (we received less) → 8160 disagio
        #   < 0 means gain (we received more) → 8060 agio
        if abs(exchange_diff) > 0:
            if exchange_diff > 0:
                exchange_account = "8160"  # Valutatap (disagio/loss)
            else:
                exchange_account = "8060"  # Valutagevinst (agio/gain)

            exchange_acc_id = None
            bank_acc_id = None

            result = await self.client.get("/ledger/account", params={
                "number": exchange_account, "fields": "id,number", "count": 1,
            })
            accs = result.get("values", [])
            if accs:
                exchange_acc_id = accs[0]["id"]

            result = await self.client.get("/ledger/account", params={
                "number": "1920", "fields": "id", "count": 1,
            })
            accs = result.get("values", [])
            if accs:
                bank_acc_id = accs[0]["id"]

            if exchange_acc_id and bank_acc_id:
                abs_diff = abs(exchange_diff)
                voucher_date = e.get("paymentDate") or today

                if exchange_diff < 0:
                    # AGIO (gain): we received MORE than booked
                    # Debit 1920 (bank gets extra), Credit 8060 (gain)
                    postings = [
                        {"date": voucher_date, "account": {"id": bank_acc_id},
                         "amountGross": abs_diff, "amountGrossCurrency": abs_diff,
                         "description": f"Agio {e.get('currency') or 'EUR'} kurs {original_rate} → {payment_rate}", "row": 1},
                        {"date": voucher_date, "account": {"id": exchange_acc_id},
                         "amountGross": -abs_diff, "amountGrossCurrency": -abs_diff,
                         "description": f"Valutagevinst (agio)", "row": 2},
                    ]
                else:
                    # DISAGIO (loss): we received LESS than booked
                    # Debit 8160 (loss), Credit 1920 (bank got less)
                    postings = [
                        {"date": voucher_date, "account": {"id": exchange_acc_id},
                         "amountGross": abs_diff, "amountGrossCurrency": abs_diff,
                         "description": f"Disagio {e.get('currency') or 'EUR'} kurs {original_rate} → {payment_rate}", "row": 1},
                        {"date": voucher_date, "account": {"id": bank_acc_id},
                         "amountGross": -abs_diff, "amountGrossCurrency": -abs_diff,
                         "description": f"Valutatap (disagio)", "row": 2},
                    ]

                result = await self.client.post("/ledger/voucher", {
                    "date": voucher_date,
                    "description": f"Valutadifferanse {e.get('customerName', '')} - {abs_diff} NOK",
                    "postings": postings,
                })
                logger.info(f"Posted exchange difference voucher: {exchange_diff} NOK (account {exchange_account})")
            else:
                logger.warning(f"Could not post exchange difference — exchange_acc={exchange_acc_id}, bank_acc={bank_acc_id}")
