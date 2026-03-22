"""Norwegian accounting domain knowledge injected into the LLM system prompt."""

ACCOUNTING_KNOWLEDGE = """
## Norwegian Accounting Domain Knowledge

### Terminology (key terms across all 7 languages)

| Concept | Norwegian (nb) | Nynorsk (nn) | English | German | Spanish | Portuguese | French |
|---|---|---|---|---|---|---|---|
| Employee | Ansatt | Tilsett | Employee | Mitarbeiter | Empleado | Empregado/Funcionário | Employé |
| Customer | Kunde | Kunde | Customer | Kunde | Cliente | Cliente | Client |
| Supplier | Leverandør | Leverandør | Supplier | Lieferant | Proveedor | Fornecedor | Fournisseur |
| Invoice | Faktura | Faktura | Invoice | Rechnung | Factura | Fatura | Facture |
| Credit note | Kreditnota | Kreditnota | Credit note | Gutschrift | Nota de crédito | Nota de crédito | Avoir |
| Payment | Betaling | Betaling | Payment | Zahlung | Pago | Pagamento | Paiement |
| Travel expense | Reiseregning | Reiserekning | Travel expense | Reisekostenabrechnung | Gasto de viaje | Despesa de viagem | Note de frais |
| Project | Prosjekt | Prosjekt | Project | Projekt | Proyecto | Projeto | Projet |
| Department | Avdeling | Avdeling | Department | Abteilung | Departamento | Departamento | Département |
| Voucher | Bilag | Bilag | Voucher | Beleg | Comprobante | Comprovante | Pièce comptable |
| Account | Konto | Konto | Account | Konto | Cuenta | Conta | Compte |
| VAT/MVA | Merverdiavgift (MVA) | Meirverdiavgift | VAT | Mehrwertsteuer (MwSt) | IVA | IVA | TVA |
| Product | Produkt | Produkt | Product | Produkt | Producto | Produto | Produit |
| Order | Ordre/Bestilling | Bestilling | Order | Bestellung | Pedido | Pedido/Encomenda | Commande |
| Administrator | Kontoadministrator | Kontoadministrator | Account administrator | Kontoverwalter | Administrador | Administrador | Administrateur |
| Organization number | Org.nr | Org.nr | Org. number | Org.-Nr. | Nº org. | Nº org. | Nº org. |
| Without VAT | Uten MVA | Utan MVA | Without VAT / excl. VAT | Ohne MwSt | Sin IVA | Sem IVA | Hors TVA |
| Including VAT | Inkl. MVA | Inkl. MVA | Including VAT | Inkl. MwSt | Con IVA | Com IVA | TTC |
| Project manager | Prosjektleder | Prosjektleiar | Project manager | Projektleiter | Jefe de proyecto | Gerente de projeto | Chef de projet |
| Due date | Forfallsdato | Forfallsdato | Due date | Fälligkeitsdatum | Fecha de vencimiento | Data de vencimento | Date d'échéance |

### Role keywords (indicates isAdministrator = true)
Norwegian: administrator, kontoadministrator, rolle, tilgang, admin
Nynorsk: administrator, kontoadministrator, rolle, tilgang
English: administrator, admin role, account administrator
German: Administrator, Verwalter, Kontoverwalter, Admin
Spanish: administrador, rol de administrador
Portuguese: administrador, papel de administrador
French: administrateur, rôle administrateur

### Norwegian Chart of Accounts (Norsk Standard Kontoplan NS 4102)
Key accounts used in Tripletex:
- 1920: Bankinnskudd (Bank deposits) — main bank account
- 1950: Bankinnskudd for skattetrekk (Tax deduction bank account)
- 1500: Kundefordringer (Accounts receivable)
- 2400: Leverandørgjeld (Accounts payable)
- 3000: Salgsinntekt (Sales revenue)
- 3100: Salgsinntekt, avgiftsfri (Tax-exempt sales)
- 6000-6999: Other operating expenses
- 7100: Bilgodtgjørelse (Car allowance)
- 7140: Reisekostnad (Travel costs)

### Norwegian VAT (MVA) Rules — Tripletex VAT Type IDs
Outgoing (sales):
- id=3  (number 3):  25% — standard rate (most goods and services)
- id=31 (number 31): 15% — food and beverages
- id=32 (number 33): 12% — transport, cinema, hotel
- id=5  (number 5):  0%  — no outgoing VAT, within MVA law (domestic exempt)
- id=6  (number 6):  0%  — no outgoing VAT, outside MVA law (export, etc.)
- id=0  (number 0):  0%  — no VAT treatment at all

Incoming (purchases):
- id=1  (number 1):  25% — deductible incoming VAT, high rate
- id=11 (number 11): 15% — deductible incoming VAT, medium rate
- id=12 (number 13): 12% — deductible incoming VAT, low rate

When prompt says "uten MVA"/"sem IVA"/"without VAT"/"ohne MwSt"/"sin IVA"/"hors TVA":
→ Do NOT set vatType on order lines. The default (id=6, 0%) will be used.

### Norwegian Standard Chart of Accounts (NS 4102) — Key accounts
- 1500: Kundefordringer (Accounts receivable)
- 1920: Bankinnskudd (Bank deposits) [BANK] — MUST have bankAccountNumber set for invoicing
- 1950: Bankinnskudd for skattetrekk (Tax deduction bank) [BANK]
- 2400: Leverandørgjeld (Accounts payable)
- 3000: Salgsinntekt (Sales revenue)
- 6000-6999: Driftskostnader (Operating expenses)
- 7100: Bilgodtgjørelse (Car allowance)
- 7140: Reisekostnad (Travel costs)

### Common Accounting Workflows
1. Create invoice: customer → order (with lines) → invoice → (optionally register payment)
2. Register payment: create customer → create order → create invoice → GET payment types → PUT /invoice/{id}/:payment
3. Credit note: create customer → create order → create invoice → PUT /invoice/{id}/:createCreditNote
4. Travel expense: find employee → create expense with travelDetails → (optionally add costs via POST /travelExpense/cost)
5. Project billing: find/create customer → create project → create order (linked to project) → invoice
6. Bank reconciliation: import bank statement → match transactions to vouchers
7. Year-end closing: verify all accounts → create closing vouchers → generate reports

### Tripletex-Specific Gotchas
- Fresh accounts have NO bank account number on 1920 — must set it before creating invoices
- Employees require userType (STANDARD/EXTENDED/NO_ACCESS) and department.id
- Admin role = PUT /employee/entitlement/:grantEntitlementsByTemplate?template=ALL_PRIVILEGES
- Project requires startDate
- Travel expense: departureDate/returnDate go inside travelDetails, NOT top level
- GET /invoice requires invoiceDateFrom + invoiceDateTo parameters
- GET /order requires orderDateFrom + orderDateTo parameters
- GET /ledger/voucher requires dateFrom + dateTo parameters
- Supplier = POST /customer with isSupplier=true, isCustomer=false
- Payment registration uses query params, not JSON body: PUT /invoice/{id}/:payment?paymentDate=...&paymentTypeId=...&paidAmount=...
- Credit note also uses query params: PUT /invoice/{id}/:createCreditNote?date=...&comment=...&sendToCustomer=false
"""
