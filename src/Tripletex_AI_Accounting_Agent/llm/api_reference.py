"""Condensed Tripletex API reference injected into the LLM system prompt."""

API_REFERENCE = """
## Tripletex API Reference (required fields and key details)

### POST /employee
Required: firstName, lastName, userType (STANDARD|EXTENDED|NO_ACCESS), department.id
Optional: email, dateOfBirth (YYYY-MM-DD), phoneNumberMobile, employeeNumber, address
Admin role: after creation, PUT /employee/entitlement/:grantEntitlementsByTemplate?employeeId={id}&template=ALL_PRIVILEGES
Note: Must find default department first via GET /department

### POST /customer
Required: name
Optional: email, organizationNumber, phoneNumber, phoneNumberMobile, isCustomer (bool), isSupplier (bool), invoiceEmail, postalAddress, language (NO|EN)
Note: For suppliers, set isSupplier=true. If ONLY supplier (not customer), set isCustomer=false.

### POST /product
Required: name
Optional: number, priceExcludingVatCurrency, priceIncludingVatCurrency, description, vatType.id, costExcludingVatCurrency

### POST /department
Required: name
Optional: departmentNumber, departmentManager.id

### POST /project
Required: name, startDate (YYYY-MM-DD)
Optional: number, customer.id, projectManager.id, endDate, description
Note: Find customer via GET /customer?name=X, find employee via GET /employee?firstName=X

### POST /order
Required: customer.id, orderDate (YYYY-MM-DD), deliveryDate (YYYY-MM-DD)
Optional: orderLines[] (each: description, count, unitPriceExcludingVatCurrency, vatType.id, product.id)

### POST /invoice
Required: invoiceDate (YYYY-MM-DD), invoiceDueDate (YYYY-MM-DD), orders[].id
Optional: customer.id, kid, comment, invoiceNumber
Prerequisite: company must have bank account number on ledger account 1920
Setup: GET /ledger/account?number=1920 → PUT /ledger/account/{id} with bankAccountNumber

### PUT /invoice/{id}/:payment
Register payment on existing invoice.
Parameters: paymentDate (YYYY-MM-DD), paymentTypeId (int), paidAmount (number)
Find payment types: GET /invoice/paymentType

### OrderLine fields
description, count (quantity), unitPriceExcludingVatCurrency, vatType.id, product.id, discount (%)

### GET /travelExpense, POST /travelExpense, DELETE /travelExpense/{id}
Required for POST: employee.id, title
Optional: travelDetails.departureDate, travelDetails.returnDate, travelDetails.destination, travelDetails.purpose, project.id, costs[]
IMPORTANT: departureDate and returnDate go INSIDE travelDetails object, NOT at top level
Find employee first via GET /employee

### GET /ledger/voucher, POST /ledger/voucher, DELETE /ledger/voucher/{id}
POST requires: date, description, postings[]
Each posting: debit.id or credit.id (account), amount, description

### POST /travelExpense/cost — Add cost line to travel expense
Required: travelExpense.id, date, amountCurrencyIncVat, costCategory.id, paymentType.id
Available costCategory IDs: query GET /travelExpense/costCategory?fields=*
paymentType.id: use 0 for default

### Special query requirements
- GET /invoice requires: invoiceDateFrom, invoiceDateTo
- GET /order requires: orderDateFrom, orderDateTo
- GET /ledger/voucher requires: dateFrom, dateTo

### Common query parameters
- fields: comma-separated or "*" for all (e.g., "id,firstName,lastName,email")
- count: max results (e.g., 100)
- from: pagination offset
- name: search filter (for customer, employee)
- firstName, lastName: search filters for employee

### GET /currency — Look up currencies and exchange rates (FREE — GETs don't count)
- GET /currency?code=EUR → find currency ID
- GET /currency/{id}/exchangeRate?date=YYYY-MM-DD&amount=X → convert amount to NOK
- GET /currency/{id}/rate?date=YYYY-MM-DD → get exchange rate for date
- Currency IDs: NOK=1, SEK=2, DKK=3, USD=4, EUR=5

### CRITICAL: Scoring only counts WRITE calls
- Only POST, PUT, DELETE, PATCH count toward call efficiency
- GET requests are FREE — read as much as needed
- Error cleanliness only counts WRITE call errors (4xx on POST/PUT/DELETE)
- Minimize writes, use GETs liberally to verify and explore

### Authentication
Basic Auth — username: "0", password: session_token

### VatType IDs (Norwegian standard)
- 0: No VAT (exempt / fritatt)
- 3: 25% outgoing MVA (standard rate, "Utgående avgift, høy sats")
- 5: 0% outgoing, no VAT treatment domestic ("Ingen utgående avgift, innenfor")
- 6: 0% outgoing, no VAT treatment foreign ("Ingen utgående avgift, utenfor")
- 7: 0% no VAT treatment at all
- Default for products without explicit VAT type: id=6
Note: When prompt says "uten MVA"/"sem IVA"/"without VAT"/"ohne MwSt", omit vatType (let API use default)
"""
