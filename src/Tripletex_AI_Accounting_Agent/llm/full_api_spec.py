FULL_API_SPEC = """
# Complete Tripletex API Reference (auto-generated from OpenAPI spec)
# [BETA-MAY-403] endpoints may return 403 — handle gracefully
# Only write calls (POST/PUT/DELETE) count toward efficiency score
# GET requests are FREE — use liberally

GET /activity params=[id,name,number,description,isProjectActivity,isGeneral,isChargeable,isTask,isInactive,from,count,sorting]
POST /activity body=[activityType:string(GENERAL_ACTIVITY|PROJECT_GENERAL_ACTIVITY|PROJECT_SPECIFIC_ACTIVITY|TASK)|costPercentage:number|description:string|isChargeable:boolean|name:string|number:string|rate:number]
GET /activity/>forTimeSheet params=[projectId,employeeId,date,filterExistingHours,query,from,count,sorting,fields]
POST /activity/list
GET /activity/{id} params=[fields]
GET /bank params=[id,registerNumbers,isBankReconciliationSupport,isAutoPaySupported,isZtlSupported,query,from,count,sorting,fields]
GET /bank/reconciliation params=[id,accountingPeriodId,accountId,from,count,sorting,fields]
POST /bank/reconciliation body=[account:Account|accountingPeriod:AccountingPeriod|attachment:Document|bankAccountClosingBalanceCurrency:number|closedByContact:Contact|closedByEmployee:Employee|isClosed:boolean|type:string(MANUAL|AUTOMATIC)|voucher:Voucher]
GET /bank/reconciliation/>last params=[accountId,fields]
GET /bank/reconciliation/>lastClosed params=[accountId,after,fields]
GET /bank/reconciliation/closedWithUnmatchedTransactions params=[accountId,start,fields]
GET /bank/reconciliation/match params=[id,bankReconciliationId,count,approved,from,sorting,fields]
POST /bank/reconciliation/match body=[bankReconciliation:BankReconciliation|postings:array|transactions:array|type:string(MANUAL|PENDING_SUGGESTION|REJECTED_SUGGESTION|APPROVED_SUGGESTION|ADJUSTMENT)]
PUT /bank/reconciliation/match/:suggest params=[bankReconciliationId]
GET /bank/reconciliation/match/count params=[bankReconciliationId,fields]
GET /bank/reconciliation/match/query params=[bankReconciliationId,approved,count,from,sorting,fields]
GET /bank/reconciliation/match/{id} params=[fields]
PUT /bank/reconciliation/match/{id} body=[bankReconciliation:BankReconciliation|postings:array|transactions:array|type:string(MANUAL|PENDING_SUGGESTION|REJECTED_SUGGESTION|APPROVED_SUGGESTION|ADJUSTMENT)]
DELETE /bank/reconciliation/match/{id}
GET /bank/reconciliation/matches/counter [BETA-MAY-403] params=[bankReconciliationId,fields]
POST /bank/reconciliation/matches/counter [BETA-MAY-403]
GET /bank/reconciliation/paymentType params=[id,description,from,count,sorting,fields]
GET /bank/reconciliation/paymentType/{id} params=[fields]
GET /bank/reconciliation/settings params=[fields]
POST /bank/reconciliation/settings body=[numberOfMatchesPerPage:string(ITEMS_10|ITEMS_50|ITEMS_100|ITEMS_500|ITEMS_1000)]
PUT /bank/reconciliation/settings/{id} body=[numberOfMatchesPerPage:string(ITEMS_10|ITEMS_50|ITEMS_100|ITEMS_500|ITEMS_1000)]
PUT /bank/reconciliation/transactions/unmatched:csv params=[reconciliationId]
GET /bank/reconciliation/{id} params=[fields]
PUT /bank/reconciliation/{id} body=[account:Account|accountingPeriod:AccountingPeriod|attachment:Document|bankAccountClosingBalanceCurrency:number|closedByContact:Contact|closedByEmployee:Employee|isClosed:boolean|type:string(MANUAL|AUTOMATIC)|voucher:Voucher]
DELETE /bank/reconciliation/{id}
PUT /bank/reconciliation/{id}/:adjustment
GET /bank/statement params=[id,accountId,fileFormats,from,count,sorting,fields]
POST /bank/statement/import
GET /bank/statement/transaction params=[bankStatementId,from,count,sorting,fields]
GET /bank/statement/transaction/{id} params=[fields]
GET /bank/statement/transaction/{id}/details params=[fields]
GET /bank/statement/{id} params=[fields]
DELETE /bank/statement/{id}
GET /bank/{id} params=[fields]
PUT /company body=[address:Address|currency:Currency|email:string|endDate:string|faxNumber:string|name:string|organizationNumber:string|phoneNumber:string|phoneNumberMobile:string|startDate:string|type:string(NONE|ENK|AS|NUF|ANS)]
GET /company/>withLoginAccess params=[from,count,sorting,fields]
GET /company/divisions params=[from,count,sorting,fields]
GET /company/salesmodules [BETA-MAY-403] params=[from,count,sorting,fields]
POST /company/salesmodules [BETA-MAY-403] body=[costStartDate:string|name:string(MAMUT|MAMUT_WITH_WAGE|AGRO_LICENCE|AGRO_CLIENT|AGRO_DOCUMENT_CENTER)]
GET /company/settings/altinn params=[fields]
PUT /company/settings/altinn body=[altInnId:integer|altInnPassword:string]
GET /company/{id} params=[fields]
GET /contact params=[id,firstName,lastName,email,customerId,departmentId,from,count,sorting,fields]
POST /contact body=[customer:Customer|department:Department|email:string|firstName:string|isInactive:boolean|lastName:string|phoneNumberMobile:string|phoneNumberMobileCountry:Country|phoneNumberWork:string]
POST /contact/list
DELETE /contact/list [BETA-MAY-403]
GET /contact/{id} params=[fields]
PUT /contact/{id} body=[customer:Customer|department:Department|email:string|firstName:string|isInactive:boolean|lastName:string|phoneNumberMobile:string|phoneNumberMobileCountry:Country|phoneNumberWork:string]
GET /currency params=[id,code,from,count,sorting,fields]
GET /currency/{fromCurrencyID}/exchangeRate params=[amount,date,fields]
GET /currency/{fromCurrencyID}/{toCurrencyID}/exchangeRate params=[amount,date,fields]
GET /currency/{id} params=[fields]
GET /currency/{id}/rate params=[date,fields]
GET /customer params=[id,customerAccountNumber,organizationNumber,email,invoiceEmail,customerName,phoneNumberMobile,isInactive,accountManagerId,changedSince,from,count]
POST /customer body=[accountManager:Employee|bankAccountPresentation:array|bankAccounts:array|category1:CustomerCategory|category2:CustomerCategory|category3:CustomerCategory|currency:Currency|customerNumber:integer|deliveryAddress:DeliveryAddress|department:Department|description:string|discountPercentage:number|email:string|emailAttachmentType:string(LINK|ATTACHMENT)|globalLocationNumber:integer|invoiceEmail:string|invoiceSMSNotificationNumber:string|invoiceSendMethod:string(EMAIL|EHF|EFAKTURA|AVTALEGIRO|VIPPS)|invoiceSendSMSNotification:boolean|invoicesDueIn:integer|invoicesDueInType:string(DAYS|MONTHS|RECURRING_DAY_OF_MONTH)|isAutomaticNoticeOfDebtCollectionEnabled:boolean|isAutomaticReminderEnabled:boolean|isAutomaticSoftReminderEnabled:boolean|isFactoring:boolean|isInactive:boolean|isPrivateIndividual:boolean|isSupplier:boolean|language:string(NO|EN)|ledgerAccount:Account|name:string|organizationNumber:string|overdueNoticeEmail:string|phoneNumber:string|phoneNumberMobile:string|physicalAddress:Address|postalAddress:Address|singleCustomerInvoice:boolean|supplierNumber:integer|website:string]
GET /customer/category params=[id,name,number,description,type,from,count,sorting,fields]
POST /customer/category body=[description:string|name:string|number:string|type:integer]
GET /customer/category/{id} params=[fields]
PUT /customer/category/{id} body=[description:string|name:string|number:string|type:integer]
POST /customer/list [BETA-MAY-403]
PUT /customer/list [BETA-MAY-403]
GET /customer/{id} params=[fields]
PUT /customer/{id} body=[accountManager:Employee|bankAccountPresentation:array|bankAccounts:array|category1:CustomerCategory|category2:CustomerCategory|category3:CustomerCategory|currency:Currency|customerNumber:integer|deliveryAddress:DeliveryAddress|department:Department|description:string|discountPercentage:number|email:string|emailAttachmentType:string(LINK|ATTACHMENT)|globalLocationNumber:integer|invoiceEmail:string|invoiceSMSNotificationNumber:string|invoiceSendMethod:string(EMAIL|EHF|EFAKTURA|AVTALEGIRO|VIPPS)|invoiceSendSMSNotification:boolean|invoicesDueIn:integer|invoicesDueInType:string(DAYS|MONTHS|RECURRING_DAY_OF_MONTH)|isAutomaticNoticeOfDebtCollectionEnabled:boolean|isAutomaticReminderEnabled:boolean|isAutomaticSoftReminderEnabled:boolean|isFactoring:boolean|isInactive:boolean|isPrivateIndividual:boolean|isSupplier:boolean|language:string(NO|EN)|ledgerAccount:Account|name:string|organizationNumber:string|overdueNoticeEmail:string|phoneNumber:string|phoneNumberMobile:string|physicalAddress:Address|postalAddress:Address|singleCustomerInvoice:boolean|supplierNumber:integer|website:string]
DELETE /customer/{id} [BETA-MAY-403]
GET /department params=[id,name,departmentNumber,departmentManagerId,isInactive,from,count,sorting,fields]
POST /department body=[departmentManager:Employee|departmentNumber:string|isInactive:boolean|name:string]
POST /department/list
PUT /department/list
GET /department/query params=[id,query,count,fields,isInactive,from,sorting]
GET /department/{id} params=[fields]
PUT /department/{id} body=[departmentManager:Employee|departmentNumber:string|isInactive:boolean|name:string]
DELETE /department/{id}
GET /division params=[query,from,count,sorting,fields]
POST /division body=[endDate:string|municipality:Municipality|municipalityDate:string|name:string|organizationNumber:string|startDate:string]
POST /division/list
PUT /division/list
PUT /division/{id} body=[endDate:string|municipality:Municipality|municipalityDate:string|name:string|organizationNumber:string|startDate:string]
GET /employee params=[id,firstName,lastName,employeeNumber,email,allowInformationRegistration,includeContacts,departmentId,onlyProjectManagers,onlyContacts,assignableProjectManagers,periodStart]
POST /employee body=[address:Address|bankAccountNumber:string|bic:string|comments:string|creditorBankCountryId:integer|dateOfBirth:string|department:Department|dnumber:string|email:string|employeeCategory:EmployeeCategory|employeeNumber:string|employments:array|firstName:string|holidayAllowanceEarned:HolidayAllowanceEarned|iban:string|internationalId:InternationalId|isContact:boolean|lastName:string|nationalIdentityNumber:string|phoneNumberHome:string|phoneNumberMobile:string|phoneNumberMobileCountry:Country|phoneNumberWork:string|userType:string(STANDARD|EXTENDED|NO_ACCESS)|usesAbroadPayment:boolean]
GET /employee/category params=[id,name,number,query,from,count,sorting,fields]
POST /employee/category body=[description:string|name:string|number:string]
POST /employee/category/list
PUT /employee/category/list
DELETE /employee/category/list
GET /employee/category/{id} params=[fields]
PUT /employee/category/{id} body=[description:string|name:string|number:string]
DELETE /employee/category/{id}
GET /employee/employment params=[employeeId,from,count,sorting,fields]
POST /employee/employment body=[division:Division|employee:Employee|employmentDetails:array|employmentEndReason:string(EMPLOYMENT_END_EXPIRED|EMPLOYMENT_END_EMPLOYEE|EMPLOYMENT_END_EMPLOYER|EMPLOYMENT_END_WRONGLY_REPORTED|EMPLOYMENT_END_SYSTEM_OR_ACCOUNTANT_CHANGE)|employmentId:string|endDate:string|isMainEmployer:boolean|isRemoveAccessAtEmploymentEnded:boolean|lastSalaryChangeDate:string|latestSalary:EmploymentDetails|noEmploymentRelationship:boolean|startDate:string|taxDeductionCode:string(loennFraHovedarbeidsgiver|loennFraBiarbeidsgiver|pensjon|loennTilUtenrikstjenestemann|loennKunTrygdeavgiftTilUtenlandskBorger)]
GET /employee/employment/details params=[employmentId,from,count,sorting,fields]
POST /employee/employment/details body=[annualSalary:number|date:string|employment:Employment|employmentForm:string(PERMANENT|TEMPORARY|PERMANENT_AND_HIRED_OUT|TEMPORARY_AND_HIRED_OUT|TEMPORARY_ON_CALL)|employmentType:string(ORDINARY|MARITIME|FREELANCE|NOT_CHOSEN)|hourlyWage:number|maritimeEmployment:MaritimeEmployment|occupationCode:OccupationCode|payrollTaxMunicipalityId:Municipality|percentageOfFullTimeEquivalent:number|remunerationType:string(MONTHLY_WAGE|HOURLY_WAGE|COMMISION_PERCENTAGE|FEE|NOT_CHOSEN)|shiftDurationHours:number|workingHoursScheme:string(NOT_SHIFT|ROUND_THE_CLOCK|SHIFT_365|OFFSHORE_336|CONTINUOUS)]
GET /employee/employment/details/{id} params=[fields]
PUT /employee/employment/details/{id} body=[annualSalary:number|date:string|employment:Employment|employmentForm:string(PERMANENT|TEMPORARY|PERMANENT_AND_HIRED_OUT|TEMPORARY_AND_HIRED_OUT|TEMPORARY_ON_CALL)|employmentType:string(ORDINARY|MARITIME|FREELANCE|NOT_CHOSEN)|hourlyWage:number|maritimeEmployment:MaritimeEmployment|occupationCode:OccupationCode|payrollTaxMunicipalityId:Municipality|percentageOfFullTimeEquivalent:number|remunerationType:string(MONTHLY_WAGE|HOURLY_WAGE|COMMISION_PERCENTAGE|FEE|NOT_CHOSEN)|shiftDurationHours:number|workingHoursScheme:string(NOT_SHIFT|ROUND_THE_CLOCK|SHIFT_365|OFFSHORE_336|CONTINUOUS)]
GET /employee/employment/employmentType params=[from,count,sorting,fields]
GET /employee/employment/employmentType/employmentEndReasonType params=[from,count,sorting,fields]
GET /employee/employment/employmentType/employmentFormType params=[from,count,sorting,fields]
GET /employee/employment/employmentType/maritimeEmploymentType params=[type,from,count,sorting,fields]
GET /employee/employment/employmentType/salaryType params=[from,count,sorting,fields]
GET /employee/employment/employmentType/scheduleType params=[from,count,sorting,fields]
GET /employee/employment/leaveOfAbsence params=[employmentIds,date,minPercentage,maxPercentage,from,count,sorting,fields]
POST /employee/employment/leaveOfAbsence body=[employment:Employment|endDate:string|importedLeaveOfAbsenceId:string|isWageDeduction:boolean|percentage:number|startDate:string|type:string(LEAVE_OF_ABSENCE|FURLOUGH|PARENTAL_BENEFITS|MILITARY_SERVICE|EDUCATIONAL)]
POST /employee/employment/leaveOfAbsence/list
GET /employee/employment/leaveOfAbsence/{id} params=[fields]
PUT /employee/employment/leaveOfAbsence/{id} body=[employment:Employment|endDate:string|importedLeaveOfAbsenceId:string|isWageDeduction:boolean|percentage:number|startDate:string|type:string(LEAVE_OF_ABSENCE|FURLOUGH|PARENTAL_BENEFITS|MILITARY_SERVICE|EDUCATIONAL)]
GET /employee/employment/leaveOfAbsenceType params=[from,count,sorting,fields]
GET /employee/employment/occupationCode params=[id,nameNO,code,from,count,sorting,fields]
GET /employee/employment/occupationCode/{id} params=[fields]
GET /employee/employment/remunerationType params=[from,count,sorting,fields]
GET /employee/employment/workingHoursScheme params=[from,count,sorting,fields]
GET /employee/employment/{id} params=[fields]
PUT /employee/employment/{id} body=[division:Division|employee:Employee|employmentDetails:array|employmentEndReason:string(EMPLOYMENT_END_EXPIRED|EMPLOYMENT_END_EMPLOYEE|EMPLOYMENT_END_EMPLOYER|EMPLOYMENT_END_WRONGLY_REPORTED|EMPLOYMENT_END_SYSTEM_OR_ACCOUNTANT_CHANGE)|employmentId:string|endDate:string|isMainEmployer:boolean|isRemoveAccessAtEmploymentEnded:boolean|lastSalaryChangeDate:string|latestSalary:EmploymentDetails|noEmploymentRelationship:boolean|startDate:string|taxDeductionCode:string(loennFraHovedarbeidsgiver|loennFraBiarbeidsgiver|pensjon|loennTilUtenrikstjenestemann|loennKunTrygdeavgiftTilUtenlandskBorger)]
GET /employee/entitlement params=[employeeId,from,count,sorting,fields]
PUT /employee/entitlement/:grantClientEntitlementsByTemplate [BETA-MAY-403] params=[employeeId,customerId,template,addToExisting]
PUT /employee/entitlement/:grantEntitlementsByTemplate [BETA-MAY-403] params=[employeeId,template]
GET /employee/entitlement/client [BETA-MAY-403] params=[employeeId,customerId,from,count,sorting,fields]
GET /employee/entitlement/{id} params=[fields]
GET /employee/hourlyCostAndRate params=[employeeId,from,count,sorting,fields]
POST /employee/hourlyCostAndRate body=[budgetRate:number|date:string|employee:Employee|hourCostRate:number|rate:number]
GET /employee/hourlyCostAndRate/{id} params=[fields]
PUT /employee/hourlyCostAndRate/{id} body=[budgetRate:number|date:string|employee:Employee|hourCostRate:number|rate:number]
POST /employee/list
GET /employee/nextOfKin params=[employeeId,from,count,sorting,fields]
POST /employee/nextOfKin body=[address:string|employee:Employee|name:string|phoneNumber:string|typeOfRelationship:string(SPOUSE|PARTNER|PARENT|CHILD|SIBLING)]
GET /employee/nextOfKin/{id} params=[fields]
PUT /employee/nextOfKin/{id} body=[address:string|employee:Employee|name:string|phoneNumber:string|typeOfRelationship:string(SPOUSE|PARTNER|PARENT|CHILD|SIBLING)]
GET /employee/preferences params=[id,employeeId,fields]
PUT /employee/preferences/:changeLanguage params=[language]
GET /employee/preferences/>loggedInEmployeePreferences params=[fields]
PUT /employee/preferences/list
PUT /employee/preferences/{id} body=[companyId:integer|employeeId:integer|filterOnProjectManager:boolean|filterOnProjectParticipant:boolean|language:string(NO|EN)]
GET /employee/searchForEmployeesAndContacts params=[id,firstName,lastName,email,includeContacts,isInactive,hasSystemAccess,excludeReadOnly,fields,from,count,sorting]
GET /employee/standardTime params=[employeeId,from,count,sorting,fields]
POST /employee/standardTime body=[employee:Employee|fromDate:string|hoursPerDay:number]
GET /employee/standardTime/byDate params=[employeeId,date,fields]
GET /employee/standardTime/{id} params=[fields]
PUT /employee/standardTime/{id} body=[employee:Employee|fromDate:string|hoursPerDay:number]
GET /employee/{id} params=[fields]
PUT /employee/{id} body=[address:Address|bankAccountNumber:string|bic:string|comments:string|creditorBankCountryId:integer|dateOfBirth:string|department:Department|dnumber:string|email:string|employeeCategory:EmployeeCategory|employeeNumber:string|employments:array|firstName:string|holidayAllowanceEarned:HolidayAllowanceEarned|iban:string|internationalId:InternationalId|isContact:boolean|lastName:string|nationalIdentityNumber:string|phoneNumberHome:string|phoneNumberMobile:string|phoneNumberMobileCountry:Country|phoneNumberWork:string|userType:string(STANDARD|EXTENDED|NO_ACCESS)|usesAbroadPayment:boolean]
POST /incomingInvoice [BETA-MAY-403] body=[invoiceHeader:IncomingInvoiceHeaderExternalWrite|orderLines:array]
GET /incomingInvoice/search [BETA-MAY-403] params=[voucherId,invoiceDateFrom,invoiceDateTo,invoiceNumber,vendorId,status,from,count,sorting,fields]
GET /incomingInvoice/{voucherId} [BETA-MAY-403] params=[fields]
PUT /incomingInvoice/{voucherId} [BETA-MAY-403] body=[invoiceHeader:IncomingInvoiceHeaderExternalWrite|orderLines:array] params=[sendTo]
POST /incomingInvoice/{voucherId}/addPayment [BETA-MAY-403] body=[amountCurrency:number|creditorIbanOrBban:string|kidOrReceiverReference:string|partialPayment:boolean|paymentDate:string|paymentTypeClientUUId:string|useDefaultPaymentType:boolean]
GET /invoice params=[id,invoiceDateFrom,invoiceDateTo,invoiceNumber,kid,voucherId,customerId,from,count,sorting,fields]
POST /invoice body=[comment:string|currency:Currency|customer:Customer|ehfSendStatus:string(DO_NOT_SEND|SEND|SENT|SEND_FAILURE_RECIPIENT_NOT_FOUND)|invoiceDate:string|invoiceDueDate:string|invoiceNumber:integer|invoiceRemark:InvoiceRemark|invoiceRemarks:string|kid:string|orders:array|paidAmount:number|paymentTypeId:integer|voucher:Voucher]
GET /invoice/details params=[id,invoiceDateFrom,invoiceDateTo,from,count,sorting,fields]
GET /invoice/details/{id} params=[fields]
POST /invoice/list [BETA-MAY-403]
GET /invoice/paymentType params=[id,description,query,from,count,sorting,fields]
GET /invoice/paymentType/{id} params=[fields]
GET /invoice/{id} params=[fields]
PUT /invoice/{id}/:createCreditNote params=[date,comment,creditNoteEmail,sendToCustomer,sendType]
PUT /invoice/{id}/:createReminder params=[type,date,includeCharge,includeInterest,dispatchType,dispatchTypes,smsNumber,email,address,postalCode,city]
PUT /invoice/{id}/:payment params=[paymentDate,paymentTypeId,paidAmount,paidAmountCurrency]
PUT /invoice/{id}/:send params=[sendType,overrideEmailAddress]
GET /invoice/{invoiceId}/pdf params=[download]
GET /invoiceRemark/{id} params=[fields]
GET /ledger params=[dateFrom,dateTo,openPostings,accountId,supplierId,customerId,employeeId,departmentId,projectId,productId,accountingDimensionValue1Id,accountingDimensionValue2Id]
GET /ledger/account params=[id,number,isBankAccount,isInactive,isApplicableForSupplierInvoice,ledgerType,isBalanceAccount,saftCode,from,count,sorting,fields]
POST /ledger/account body=[bankAccountCountry:Country|bankAccountIBAN:string|bankAccountNumber:string|bankAccountSWIFT:string|bankName:string|currency:Currency|department:Department|description:string|groupingCode:string|invoicingDepartment:Department|isApplicableForSupplierInvoice:boolean|isBankAccount:boolean|isCloseable:boolean|isInactive:boolean|isInvoiceAccount:boolean|isPostingsExist:boolean|ledgerType:string(GENERAL|CUSTOMER|VENDOR|EMPLOYEE|ASSET)|name:string|number:integer|quantityType1:ProductUnit|quantityType2:ProductUnit|requireReconciliation:boolean|requiresDepartment:boolean|requiresProject:boolean|saftCode:string|vatLocked:boolean|vatType:VatType]
POST /ledger/account/list
PUT /ledger/account/list
DELETE /ledger/account/list
GET /ledger/account/{id} params=[fields]
PUT /ledger/account/{id} body=[bankAccountCountry:Country|bankAccountIBAN:string|bankAccountNumber:string|bankAccountSWIFT:string|bankName:string|currency:Currency|department:Department|description:string|groupingCode:string|invoicingDepartment:Department|isApplicableForSupplierInvoice:boolean|isBankAccount:boolean|isCloseable:boolean|isInactive:boolean|isInvoiceAccount:boolean|isPostingsExist:boolean|ledgerType:string(GENERAL|CUSTOMER|VENDOR|EMPLOYEE|ASSET)|name:string|number:integer|quantityType1:ProductUnit|quantityType2:ProductUnit|requireReconciliation:boolean|requiresDepartment:boolean|requiresProject:boolean|saftCode:string|vatLocked:boolean|vatType:VatType]
DELETE /ledger/account/{id}
GET /ledger/accountingDimensionName params=[activeOnly,fields,from,count,sorting]
POST /ledger/accountingDimensionName body=[active:boolean|description:string|dimensionName:string]
GET /ledger/accountingDimensionName/search params=[dimensionIndex,activeOnly,onlyDimensionsWithActiveValues,fields,from,count,sorting]
GET /ledger/accountingDimensionName/{id} params=[fields]
PUT /ledger/accountingDimensionName/{id} body=[active:boolean|description:string|dimensionName:string]
DELETE /ledger/accountingDimensionName/{id}
POST /ledger/accountingDimensionValue body=[active:boolean|dimensionIndex:integer|number:string|position:integer|showInVoucherRegistration:boolean]
PUT /ledger/accountingDimensionValue/list
GET /ledger/accountingDimensionValue/search params=[dimensionIndex,activeOnly,showInVoucherRegistration,fields,from,count,sorting]
GET /ledger/accountingDimensionValue/{id} params=[fields]
DELETE /ledger/accountingDimensionValue/{id}
GET /ledger/accountingPeriod params=[id,numberFrom,numberTo,startFrom,startTo,endFrom,endTo,count,from,sorting,fields]
GET /ledger/accountingPeriod/{id} params=[fields]
GET /ledger/annualAccount params=[id,yearFrom,yearTo,from,count,sorting,fields]
GET /ledger/annualAccount/{id} params=[fields]
GET /ledger/closeGroup params=[id,dateFrom,dateTo,from,count,sorting,fields]
GET /ledger/closeGroup/{id} params=[fields]
GET /ledger/openPost params=[date,accountId,supplierId,customerId,employeeId,departmentId,projectId,productId,accountingDimensionValue1Id,accountingDimensionValue2Id,accountingDimensionValue3Id,from]
GET /ledger/paymentTypeOut [BETA-MAY-403] params=[id,description,isInactive,from,count,sorting,fields]
POST /ledger/paymentTypeOut [BETA-MAY-403] body=[creditAccount:Account|currencyCode:string|currencyId:integer|description:string|isBruttoWageDeduction:boolean|isInactive:boolean|requiresSeparateVoucher:boolean|sequence:integer|showIncomingInvoice:boolean|showVatReturns:boolean|showWagePayment:boolean|showWagePeriodTransaction:boolean]
POST /ledger/paymentTypeOut/list [BETA-MAY-403]
PUT /ledger/paymentTypeOut/list [BETA-MAY-403]
GET /ledger/paymentTypeOut/{id} [BETA-MAY-403] params=[fields]
PUT /ledger/paymentTypeOut/{id} [BETA-MAY-403] body=[creditAccount:Account|currencyCode:string|currencyId:integer|description:string|isBruttoWageDeduction:boolean|isInactive:boolean|requiresSeparateVoucher:boolean|sequence:integer|showIncomingInvoice:boolean|showVatReturns:boolean|showWagePayment:boolean|showWagePeriodTransaction:boolean]
DELETE /ledger/paymentTypeOut/{id} [BETA-MAY-403]
GET /ledger/posting params=[dateFrom,dateTo,openPostings,accountId,supplierId,customerId,employeeId,departmentId,projectId,productId,accountNumberFrom,accountNumberTo]
PUT /ledger/posting/:closePostings
GET /ledger/posting/openPost params=[date,accountId,supplierId,customerId,employeeId,departmentId,projectId,productId,accountNumberFrom,accountNumberTo,accountingDimensionValue1Id,accountingDimensionValue2Id]
GET /ledger/posting/{id} params=[fields]
GET /ledger/postingByDate params=[dateFrom,dateTo,from,count,sorting,fields]
GET /ledger/postingRules params=[fields]
GET /ledger/vatSettings params=[fields]
PUT /ledger/vatSettings body=[vatRegistrationStatus:string(VAT_NOT_REGISTERED|VAT_APPLICANT|VAT_REGISTERED|VAT_COMPENSATION)]
GET /ledger/vatType params=[id,number,typeOfVat,vatDate,shouldIncludeSpecificationTypes,from,count,sorting,fields]
PUT /ledger/vatType/createRelativeVatType params=[name,vatTypeId,percentage]
GET /ledger/vatType/{id} params=[fields]
GET /ledger/voucher params=[id,number,numberFrom,numberTo,typeId,dateFrom,dateTo,from,count,sorting,fields]
POST /ledger/voucher body=[attachment:Document|date:string|description:string|document:Document|ediDocument:Document|externalVoucherNumber:string|postings:array|reverseVoucher:Voucher|vendorInvoiceNumber:string|voucherType:VoucherType]
GET /ledger/voucher/>externalVoucherNumber params=[externalVoucherNumber,from,count,sorting,fields]
GET /ledger/voucher/>nonPosted params=[dateFrom,dateTo,includeNonApproved,changedSince,from,count,sorting,fields]
GET /ledger/voucher/>voucherReception params=[dateFrom,dateTo,searchText,from,count,sorting,fields]
PUT /ledger/voucher/historical/:closePostings [BETA-MAY-403] params=[postingIds]
PUT /ledger/voucher/historical/:reverseHistoricalVouchers [BETA-MAY-403]
POST /ledger/voucher/historical/employee [BETA-MAY-403] body=[address:Address|bankAccountNumber:string|bic:string|comments:string|creditorBankCountryId:integer|dateOfBirth:string|department:Department|dnumber:string|email:string|employeeCategory:EmployeeCategory|employeeNumber:string|employments:array|firstName:string|holidayAllowanceEarned:HolidayAllowanceEarned|iban:string|internationalId:InternationalId|isContact:boolean|lastName:string|nationalIdentityNumber:string|phoneNumberHome:string|phoneNumberMobile:string|phoneNumberMobileCountry:Country|phoneNumberWork:string|userType:string(STANDARD|EXTENDED|NO_ACCESS)|usesAbroadPayment:boolean]
POST /ledger/voucher/historical/historical
POST /ledger/voucher/historical/{voucherId}/attachment
POST /ledger/voucher/importDocument
POST /ledger/voucher/importGbat10
PUT /ledger/voucher/list params=[sendToLedger]
GET /ledger/voucher/openingBalance [BETA-MAY-403] params=[fields]
POST /ledger/voucher/openingBalance [BETA-MAY-403] body=[balancePostings:array|customerPostings:array|employeePostings:array|supplierPostings:array|voucherDate:string]
DELETE /ledger/voucher/openingBalance [BETA-MAY-403]
GET /ledger/voucher/openingBalance/>correctionVoucher [BETA-MAY-403] params=[fields]
GET /ledger/voucher/{id} params=[fields]
PUT /ledger/voucher/{id} body=[attachment:Document|date:string|description:string|document:Document|ediDocument:Document|externalVoucherNumber:string|postings:array|reverseVoucher:Voucher|vendorInvoiceNumber:string|voucherType:VoucherType] params=[sendToLedger]
DELETE /ledger/voucher/{id}
PUT /ledger/voucher/{id}/:reverse params=[date]
PUT /ledger/voucher/{id}/:sendToInbox params=[version,comment]
PUT /ledger/voucher/{id}/:sendToLedger params=[version,number]
GET /ledger/voucher/{id}/options params=[fields]
POST /ledger/voucher/{voucherId}/attachment
DELETE /ledger/voucher/{voucherId}/attachment
GET /ledger/voucher/{voucherId}/pdf
POST /ledger/voucher/{voucherId}/pdf/{fileName}
GET /ledger/voucherType params=[name,from,count,sorting,fields]
GET /ledger/voucherType/{id} params=[fields]
GET /municipality params=[includePayrollTaxZones,from,count,sorting,fields]
GET /municipality/query [BETA-MAY-403] params=[id,query,fields,count,from,sorting]
GET /order params=[id,number,customerId,orderDateFrom,orderDateTo,deliveryComment,isClosed,isSubscription,from,count,sorting,fields]
POST /order body=[attn:Contact|contact:Contact|currency:Currency|customer:Customer|deliveryAddress:DeliveryAddress|deliveryComment:string|deliveryDate:string|department:Department|discountPercentage:number|invoiceComment:string|invoiceOnAccountVatHigh:boolean|invoiceSMSNotificationNumber:string|invoicesDueIn:integer|invoicesDueInType:string(DAYS|MONTHS|RECURRING_DAY_OF_MONTH)|isClosed:boolean|isPrioritizeAmountsIncludingVat:boolean|isShowOpenPostsOnInvoices:boolean|isSubscription:boolean|isSubscriptionAutoInvoicing:boolean|markUpOrderLines:number|number:string|orderDate:string|orderGroups:array|orderLineSorting:string(ID|PRODUCT|PRODUCT_DESCENDING|CUSTOM)|orderLines:array|ourContact:Contact|ourContactEmployee:Employee|overdueNoticeEmail:string|preliminaryInvoice:Invoice|project:Project|receiverEmail:string|reference:string|sendMethodDescription:string|status:string(NOT_CHOSEN|NEW|CONFIRMATION_SENT|READY_FOR_PICKING|PICKED)|subscriptionDuration:integer|subscriptionDurationType:string(MONTHS|YEAR)|subscriptionInvoicingTime:integer|subscriptionInvoicingTimeInAdvanceOrArrears:string(ADVANCE|ARREARS)|subscriptionInvoicingTimeType:string(DAYS|MONTHS)|subscriptionPeriodsOnInvoice:integer]
PUT /order/:invoiceMultipleOrders [BETA-MAY-403] params=[id,invoiceDate,sendToCustomer,createBackorders]
POST /order/list [BETA-MAY-403]
GET /order/orderConfirmation/{orderId}/pdf params=[download]
GET /order/orderGroup params=[ids,orderIds,from,count,sorting,fields]
POST /order/orderGroup body=[comment:string|order:Order|orderLines:array|sortIndex:integer|title:string]
PUT /order/orderGroup body=[comment:string|order:Order|orderLines:array|sortIndex:integer|title:string] params=[OrderLineIds,removeExistingOrderLines]
GET /order/orderGroup/{id} params=[fields]
DELETE /order/orderGroup/{id}
POST /order/orderline body=[count:number|currency:Currency|description:string|discount:number|inventory:Inventory|inventoryLocation:InventoryLocation|isCharged:boolean|isPicked:boolean|isSubscription:boolean|markup:number|order:Order|orderGroup:OrderGroup|orderedQuantity:number|pickedDate:string|product:Product|sortIndex:integer|subscriptionPeriodEnd:string|subscriptionPeriodStart:string|unitCostCurrency:number|unitPriceExcludingVatCurrency:number|unitPriceIncludingVatCurrency:number|vatType:VatType|vendor:Company]
POST /order/orderline/list
GET /order/orderline/orderLineTemplate [BETA-MAY-403] params=[orderId,productId,fields]
GET /order/orderline/{id} params=[fields]
PUT /order/orderline/{id} [BETA-MAY-403] body=[count:number|currency:Currency|description:string|discount:number|inventory:Inventory|inventoryLocation:InventoryLocation|isCharged:boolean|isPicked:boolean|isSubscription:boolean|markup:number|order:Order|orderGroup:OrderGroup|orderedQuantity:number|pickedDate:string|product:Product|sortIndex:integer|subscriptionPeriodEnd:string|subscriptionPeriodStart:string|unitCostCurrency:number|unitPriceExcludingVatCurrency:number|unitPriceIncludingVatCurrency:number|vatType:VatType|vendor:Company]
DELETE /order/orderline/{id} [BETA-MAY-403]
PUT /order/orderline/{id}/:pickLine [BETA-MAY-403] params=[inventoryId,inventoryLocationId,pickDate]
PUT /order/orderline/{id}/:unpickLine [BETA-MAY-403]
GET /order/packingNote/{orderId}/pdf params=[type,download]
PUT /order/sendInvoicePreview/{orderId} params=[email,message,saveAsDefault]
PUT /order/sendOrderConfirmation/{orderId} params=[email,message,saveAsDefault]
PUT /order/sendPackingNote/{orderId} params=[email,message,saveAsDefault,type]
GET /order/{id} params=[fields]
PUT /order/{id} body=[attn:Contact|contact:Contact|currency:Currency|customer:Customer|deliveryAddress:DeliveryAddress|deliveryComment:string|deliveryDate:string|department:Department|discountPercentage:number|invoiceComment:string|invoiceOnAccountVatHigh:boolean|invoiceSMSNotificationNumber:string|invoicesDueIn:integer|invoicesDueInType:string(DAYS|MONTHS|RECURRING_DAY_OF_MONTH)|isClosed:boolean|isPrioritizeAmountsIncludingVat:boolean|isShowOpenPostsOnInvoices:boolean|isSubscription:boolean|isSubscriptionAutoInvoicing:boolean|markUpOrderLines:number|number:string|orderDate:string|orderGroups:array|orderLineSorting:string(ID|PRODUCT|PRODUCT_DESCENDING|CUSTOM)|orderLines:array|ourContact:Contact|ourContactEmployee:Employee|overdueNoticeEmail:string|preliminaryInvoice:Invoice|project:Project|receiverEmail:string|reference:string|sendMethodDescription:string|status:string(NOT_CHOSEN|NEW|CONFIRMATION_SENT|READY_FOR_PICKING|PICKED)|subscriptionDuration:integer|subscriptionDurationType:string(MONTHS|YEAR)|subscriptionInvoicingTime:integer|subscriptionInvoicingTimeInAdvanceOrArrears:string(ADVANCE|ARREARS)|subscriptionInvoicingTimeType:string(DAYS|MONTHS)|subscriptionPeriodsOnInvoice:integer] params=[updateLinesAndGroups]
DELETE /order/{id}
PUT /order/{id}/:approveSubscriptionInvoice params=[invoiceDate]
PUT /order/{id}/:attach
PUT /order/{id}/:invoice params=[invoiceDate,sendToCustomer,sendType,paymentTypeId,paidAmount,paidAmountAccountCurrency,paymentTypeIdRestAmount,paidAmountAccountCurrencyRest,createOnAccount,amountOnAccount,onAccountComment,createBackorder]
PUT /order/{id}/:unApproveSubscriptionInvoice
GET /product params=[number,ids,productNumber,name,ean,isInactive,isStockItem,isSupplierProduct,supplierId,currencyId,vatTypeId,productUnitId]
POST /product body=[account:Account|costExcludingVatCurrency:number|currency:Currency|department:Department|description:string|discountGroup:DiscountGroup|ean:string|expenses:number|hasSupplierProductConnected:boolean|hsnCode:string|image:Document|isDeletable:boolean|isInactive:boolean|isStockItem:boolean|mainSupplierProduct:SupplierProduct|minStockLevel:number|name:string|number:string|orderLineDescription:string|priceExcludingVatCurrency:number|priceIncludingVatCurrency:number|productUnit:ProductUnit|resaleProduct:Product|supplier:Supplier|vatType:VatType|volume:number|volumeUnit:string(cm3|dm3|m3)|weight:number|weightUnit:string(kg|g|hg)]
GET /product/discountGroup params=[id,name,number,from,count,sorting,fields]
GET /product/discountGroup/{id} params=[fields]
GET /product/external [BETA-MAY-403] params=[name,wholesaler,organizationNumber,elNumber,nrfNumber,isInactive,from,count,sorting,fields]
GET /product/external/{id} [BETA-MAY-403] params=[fields]
GET /product/group params=[id,name,query,from,count,sorting,fields]
POST /product/group body=[name:string|parentGroup:ProductGroup]
POST /product/group/list
PUT /product/group/list
DELETE /product/group/list
GET /product/group/query params=[query,name,fields,count,from,sorting]
GET /product/group/{id} params=[fields]
PUT /product/group/{id} body=[name:string|parentGroup:ProductGroup]
DELETE /product/group/{id}
GET /product/groupRelation params=[id,productId,productGroupId,from,count,sorting,fields]
POST /product/groupRelation body=[product:Product|productGroup:ProductGroup]
POST /product/groupRelation/list
DELETE /product/groupRelation/list
GET /product/groupRelation/{id} params=[fields]
DELETE /product/groupRelation/{id}
GET /product/inventoryLocation params=[productId,inventoryId,isMainLocation,from,count,sorting,fields]
POST /product/inventoryLocation body=[inventory:Inventory|inventoryLocation:InventoryLocation|isInactive:boolean|isMainLocation:boolean|product:Product]
POST /product/inventoryLocation/list
PUT /product/inventoryLocation/list
GET /product/inventoryLocation/{id} params=[fields]
PUT /product/inventoryLocation/{id} body=[inventory:Inventory|inventoryLocation:InventoryLocation|isInactive:boolean|isMainLocation:boolean|product:Product]
DELETE /product/inventoryLocation/{id}
POST /product/list
PUT /product/list
GET /product/logisticsSettings params=[fields]
PUT /product/logisticsSettings body=[hasWarehouseLocation:boolean|moduleBring:boolean|moduleSuggestedProductNumber:boolean|purchaseOrderDefaultComment:string|showOnboardingWizard:boolean|suggestedProductNumber:string]
GET /product/productPrice params=[productId,fromDate,toDate,showOnlyLastPrice,from,count,sorting,fields]
GET /product/supplierProduct params=[productId,resaleIds,vendorId,query,isInactive,productGroupId,count,fields,targetCurrencyId,from,sorting]
POST /product/supplierProduct body=[cost:number|costExcludingVatCurrency:number|currency:Currency|description:string|ean:string|isInactive:boolean|isMainSupplierProduct:boolean|isStockItem:boolean|name:string|number:string|priceExcludingVatCurrency:number|priceIncludingVatCurrency:number|productUnit:ProductUnit|resaleProduct:Product|supplier:Supplier|vatType:VatType]
POST /product/supplierProduct/getSupplierProductsByIds
POST /product/supplierProduct/list
PUT /product/supplierProduct/list
GET /product/supplierProduct/{id} params=[fields]
PUT /product/supplierProduct/{id} body=[cost:number|costExcludingVatCurrency:number|currency:Currency|description:string|ean:string|isInactive:boolean|isMainSupplierProduct:boolean|isStockItem:boolean|name:string|number:string|priceExcludingVatCurrency:number|priceIncludingVatCurrency:number|productUnit:ProductUnit|resaleProduct:Product|supplier:Supplier|vatType:VatType]
DELETE /product/supplierProduct/{id}
GET /product/unit params=[id,name,nameShort,commonCode,from,count,sorting,fields]
POST /product/unit body=[commonCode:string|isDeletable:boolean|name:string|nameEN:string|nameShort:string|nameShortEN:string]
POST /product/unit/list
PUT /product/unit/list
GET /product/unit/master params=[id,name,nameShort,commonCode,peppolName,peppolSymbol,isInactive,count,from,sorting,fields]
GET /product/unit/master/{id} params=[fields]
GET /product/unit/query params=[query,count,fields,from,sorting]
GET /product/unit/{id} params=[fields]
PUT /product/unit/{id} body=[commonCode:string|isDeletable:boolean|name:string|nameEN:string|nameShort:string|nameShortEN:string]
DELETE /product/unit/{id}
GET /product/{id} params=[fields]
PUT /product/{id} body=[account:Account|costExcludingVatCurrency:number|currency:Currency|department:Department|description:string|discountGroup:DiscountGroup|ean:string|expenses:number|hasSupplierProductConnected:boolean|hsnCode:string|image:Document|isDeletable:boolean|isInactive:boolean|isStockItem:boolean|mainSupplierProduct:SupplierProduct|minStockLevel:number|name:string|number:string|orderLineDescription:string|priceExcludingVatCurrency:number|priceIncludingVatCurrency:number|productUnit:ProductUnit|resaleProduct:Product|supplier:Supplier|vatType:VatType|volume:number|volumeUnit:string(cm3|dm3|m3)|weight:number|weightUnit:string(kg|g|hg)]
DELETE /product/{id}
POST /product/{id}/image
DELETE /product/{id}/image
GET /project params=[id,name,number,isOffer,projectManagerId,customerAccountManagerId,employeeInProjectId,departmentId,startDateFrom,startDateTo,endDateFrom,endDateTo]
POST /project body=[accessType:string(NONE|READ|WRITE)|accountingDimensionValues:array|attention:Contact|boligmappaAddress:Address|contact:Contact|currency:Currency|customer:Customer|deliveryAddress:Address|department:Department|description:string|displayNameFormat:string(NAME_STANDARD|NAME_INCL_CUSTOMER_NAME|NAME_INCL_PARENT_NAME|NAME_INCL_PARENT_NUMBER|NAME_INCL_PARENT_NAME_AND_NUMBER)|endDate:string|externalAccountsNumber:string|fixedprice:number|forParticipantsOnly:boolean|generalProjectActivitiesPerProjectOnly:boolean|ignoreCompanyProductDiscountAgreement:boolean|invoiceComment:string|invoiceDueDate:integer|invoiceDueDateType:string(DAYS|MONTHS|RECURRING_DAY_OF_MONTH)|invoiceOnAccountVatHigh:boolean|invoiceReceiverEmail:string|isClosed:boolean|isFixedPrice:boolean|isInternal:boolean|isOffer:boolean|isPriceCeiling:boolean|isReadyForInvoicing:boolean|mainProject:Project|markUpFeesEarned:number|markUpOrderLines:number|name:string|number:string|overdueNoticeEmail:string|participants:array|preliminaryInvoice:Invoice|priceCeilingAmount:number|projectActivities:array|projectCategory:ProjectCategory|projectHourlyRates:array|projectManager:Employee|reference:string|startDate:string|useProductNetPrice:boolean|vatType:VatType]
DELETE /project [BETA-MAY-403]
GET /project/>forTimeSheet params=[includeProjectOffers,employeeId,date,from,count,sorting,fields]
GET /project/batchPeriod/budgetStatusByProjectIds params=[ids,from,count,sorting,fields]
GET /project/batchPeriod/invoicingReserveByProjectIds params=[ids,dateFrom,dateTo,from,count,sorting,fields]
GET /project/category params=[id,name,number,description,from,count,sorting,fields]
POST /project/category body=[description:string|name:string|number:string]
GET /project/category/{id} params=[fields]
PUT /project/category/{id} body=[description:string|name:string|number:string]
GET /project/controlForm [BETA-MAY-403] params=[projectId,from,count,sorting,fields]
GET /project/controlForm/{id} [BETA-MAY-403] params=[fields]
GET /project/controlFormType [BETA-MAY-403] params=[from,count,sorting,fields]
GET /project/controlFormType/{id} [BETA-MAY-403] params=[fields]
PUT /project/dynamicControlForm/{id}/:copyFieldValuesFromLastEditedForm
GET /project/hourlyRates params=[id,projectId,type,startDateFrom,startDateTo,showInProjectOrder,from,count,sorting,fields]
POST /project/hourlyRates body=[fixedRate:number|hourlyRateModel:string(TYPE_PREDEFINED_HOURLY_RATES|TYPE_PROJECT_SPECIFIC_HOURLY_RATES|TYPE_FIXED_HOURLY_RATE)|project:Project|projectSpecificRates:array|showInProjectOrder:boolean|startDate:string]
DELETE /project/hourlyRates/deleteByProjectIds
POST /project/hourlyRates/list
PUT /project/hourlyRates/list
DELETE /project/hourlyRates/list
GET /project/hourlyRates/projectSpecificRates params=[id,projectHourlyRateId,employeeId,activityId,from,count,sorting,fields]
POST /project/hourlyRates/projectSpecificRates body=[activity:Activity|employee:Employee|hourlyCostPercentage:number|hourlyRate:number|projectHourlyRate:ProjectHourlyRate]
POST /project/hourlyRates/projectSpecificRates/list
PUT /project/hourlyRates/projectSpecificRates/list
DELETE /project/hourlyRates/projectSpecificRates/list
GET /project/hourlyRates/projectSpecificRates/{id} params=[fields]
PUT /project/hourlyRates/projectSpecificRates/{id} body=[activity:Activity|employee:Employee|hourlyCostPercentage:number|hourlyRate:number|projectHourlyRate:ProjectHourlyRate]
DELETE /project/hourlyRates/projectSpecificRates/{id}
PUT /project/hourlyRates/updateOrAddHourRates body=[fixedRate:number|hourlyRateModel:string(TYPE_PREDEFINED_HOURLY_RATES|TYPE_PROJECT_SPECIFIC_HOURLY_RATES|TYPE_FIXED_HOURLY_RATE)|projectSpecificRates:array|startDate:string] params=[ids]
GET /project/hourlyRates/{id} params=[fields]
PUT /project/hourlyRates/{id} body=[fixedRate:number|hourlyRateModel:string(TYPE_PREDEFINED_HOURLY_RATES|TYPE_PROJECT_SPECIFIC_HOURLY_RATES|TYPE_FIXED_HOURLY_RATE)|project:Project|projectSpecificRates:array|showInProjectOrder:boolean|startDate:string]
DELETE /project/hourlyRates/{id}
POST /project/import
POST /project/list [BETA-MAY-403]
PUT /project/list [BETA-MAY-403]
DELETE /project/list [BETA-MAY-403]
GET /project/number/{number} params=[fields]
GET /project/orderline [BETA-MAY-403] params=[projectId,isBudget,from,count,sorting,fields]
POST /project/orderline [BETA-MAY-403] body=[count:number|currency:Currency|customSortIndex:integer|date:string|description:string|discount:number|inventory:Inventory|inventoryLocation:InventoryLocation|invoice:Invoice|isChargeable:boolean|markup:number|product:Product|project:Project|unitCostCurrency:number|unitPriceExcludingVatCurrency:number|vatType:VatType|vendor:Company|voucher:Voucher]
POST /project/orderline/list [BETA-MAY-403]
GET /project/orderline/orderLineTemplate [BETA-MAY-403] params=[projectId,productId,fields]
GET /project/orderline/query [BETA-MAY-403] params=[id,projectId,query,isBudget,from,count,sorting,fields]
GET /project/orderline/{id} [BETA-MAY-403] params=[fields]
PUT /project/orderline/{id} [BETA-MAY-403] body=[count:number|currency:Currency|customSortIndex:integer|date:string|description:string|discount:number|inventory:Inventory|inventoryLocation:InventoryLocation|invoice:Invoice|isChargeable:boolean|markup:number|product:Product|project:Project|unitCostCurrency:number|unitPriceExcludingVatCurrency:number|vatType:VatType|vendor:Company|voucher:Voucher]
DELETE /project/orderline/{id}
POST /project/participant [BETA-MAY-403] body=[adminAccess:boolean|employee:Employee|project:Project]
POST /project/participant/list [BETA-MAY-403]
DELETE /project/participant/list [BETA-MAY-403]
GET /project/participant/{id} [BETA-MAY-403] params=[fields]
PUT /project/participant/{id} [BETA-MAY-403] body=[adminAccess:boolean|employee:Employee|project:Project]
POST /project/projectActivity body=[activity:Activity|budgetFeeCurrency:number|budgetHourlyRateCurrency:number|budgetHours:number|endDate:string|isClosed:boolean|project:Project|startDate:string]
DELETE /project/projectActivity/list
GET /project/projectActivity/{id} params=[fields]
DELETE /project/projectActivity/{id}
GET /project/resourcePlanBudget params=[projectId,periodStart,periodEnd,periodType,fields]
GET /project/settings params=[useNkode,fields]
PUT /project/settings body=[allowMultipleProjectInvoiceVat:boolean|approveHourLists:boolean|approveInvoices:boolean|autoCloseInvoicedProjects:boolean|autoConnectIncomingOrderlineToProject:boolean|autoGenerateProjectNumber:boolean|autoGenerateStartingNumber:integer|budgetOnSubcontracts:boolean|controlFormsRequiredForHourTracking:array|controlFormsRequiredForInvoicing:array|customControlForms:boolean|defaultProjectContractComment:string|defaultProjectInvoicingComment:string|dynamicControlFormIdsRequiredForHourTracking:array|dynamicControlFormIdsRequiredForInvoicing:array|emailOnDocuments:string|emailOnProjectBudget:string|emailOnProjectContract:string|fixedPriceProjectsFeeCalcMethod:string(FIXED_PRICE_PROJECTS_CALC_METHOD_INVOICED_FEE|FIXED_PRICE_PROJECTS_CALC_METHOD_PERCENT_COMPLETED)|fixedPriceProjectsInvoiceByProgress:boolean|historicalInformation:boolean|holidayPlan:boolean|hourCostPercentage:boolean|hourlyRateProjectsWriteUpDown:boolean|isCurrentMonthDefaultPeriod:boolean|isNHOMember:boolean|markReadyForInvoicing:boolean|mustApproveRegisteredHours:boolean|onlyProjectActivitiesTimesheetRegistration:boolean|onlyProjectMembersCanRegisterInfo:boolean|projectBudgetReferenceFee:boolean|projectCategories:boolean|projectForecast:boolean|projectHourlyRateModel:string(TYPE_PREDEFINED_HOURLY_RATES|TYPE_PROJECT_SPECIFIC_HOURLY_RATES|TYPE_FIXED_HOURLY_RATE)|projectNameScheme:string(NAME_STANDARD|NAME_INCL_CUSTOMER_NAME|NAME_INCL_PARENT_NAME|NAME_INCL_PARENT_NUMBER|NAME_INCL_PARENT_NAME_AND_NUMBER)|projectOrderLinesSortOrder:string(SORT_ORDER_ID|SORT_ORDER_DATE|SORT_ORDER_PRODUCT|SORT_ORDER_CUSTOM)|projectTypeOfContract:string(PROJECT_FIXED_PRICE|PROJECT_HOUR_RATES)|referenceFee:boolean|resourceGroups:boolean|resourcePlanPeriod:string(PERIOD_MONTH|PERIOD_WEEK|PERIOD_DAY)|resourcePlanning:boolean|showProjectOnboarding:boolean|showProjectOrderLinesToAllProjectParticipants:boolean|showRecentlyClosedProjectsOnSupplierInvoice:boolean|sortOrderProjects:string(SORT_ORDER_NAME_AND_NUMBER|SORT_ORDER_NAME)|standardReinvoicing:boolean|useLoggedInUserEmailOnDocuments:boolean|useLoggedInUserEmailOnProjectBudget:boolean|useLoggedInUserEmailOnProjectContract:boolean|useProductNetPrice:boolean]
GET /project/subcontract params=[projectId,from,count,sorting,fields]
POST /project/subcontract body=[budgetExpensesCurrency:number|budgetFeeCurrency:number|budgetIncomeCurrency:number|budgetNetAmountCurrency:number|company:Company|description:string|name:string|project:Project]
GET /project/subcontract/query params=[id,projectId,query,from,count,sorting,fields]
GET /project/subcontract/{id} params=[fields]
PUT /project/subcontract/{id} body=[budgetExpensesCurrency:number|budgetFeeCurrency:number|budgetIncomeCurrency:number|budgetNetAmountCurrency:number|company:Company|description:string|name:string|project:Project]
DELETE /project/subcontract/{id}
GET /project/task params=[projectId,from,count,sorting,fields]
GET /project/template/{id} params=[fields]
GET /project/{id} params=[fields]
PUT /project/{id} [BETA-MAY-403] body=[accessType:string(NONE|READ|WRITE)|accountingDimensionValues:array|attention:Contact|boligmappaAddress:Address|contact:Contact|currency:Currency|customer:Customer|deliveryAddress:Address|department:Department|description:string|displayNameFormat:string(NAME_STANDARD|NAME_INCL_CUSTOMER_NAME|NAME_INCL_PARENT_NAME|NAME_INCL_PARENT_NUMBER|NAME_INCL_PARENT_NAME_AND_NUMBER)|endDate:string|externalAccountsNumber:string|fixedprice:number|forParticipantsOnly:boolean|generalProjectActivitiesPerProjectOnly:boolean|ignoreCompanyProductDiscountAgreement:boolean|invoiceComment:string|invoiceDueDate:integer|invoiceDueDateType:string(DAYS|MONTHS|RECURRING_DAY_OF_MONTH)|invoiceOnAccountVatHigh:boolean|invoiceReceiverEmail:string|isClosed:boolean|isFixedPrice:boolean|isInternal:boolean|isOffer:boolean|isPriceCeiling:boolean|isReadyForInvoicing:boolean|mainProject:Project|markUpFeesEarned:number|markUpOrderLines:number|name:string|number:string|overdueNoticeEmail:string|participants:array|preliminaryInvoice:Invoice|priceCeilingAmount:number|projectActivities:array|projectCategory:ProjectCategory|projectHourlyRates:array|projectManager:Employee|reference:string|startDate:string|useProductNetPrice:boolean|vatType:VatType]
DELETE /project/{id} [BETA-MAY-403]
GET /project/{id}/period/budgetStatus params=[fields]
GET /project/{id}/period/hourlistReport params=[dateFrom,dateTo,fields]
GET /project/{id}/period/invoiced params=[dateFrom,dateTo,fields]
GET /project/{id}/period/invoicingReserve params=[dateFrom,dateTo,fields]
GET /project/{id}/period/monthlyStatus params=[dateFrom,dateTo,from,count,sorting,fields]
GET /project/{id}/period/overallStatus params=[dateFrom,dateTo,fields]
GET /salary/compilation params=[employeeId,year,fields]
GET /salary/compilation/pdf params=[employeeId,year]
POST /salary/financeTax/reconciliation/context body=[customerId:integer|term:integer|year:integer]
GET /salary/financeTax/reconciliation/{reconciliationId}/overview params=[fields]
GET /salary/financeTax/reconciliation/{reconciliationId}/paymentsOverview params=[fields]
POST /salary/holidayAllowance/reconciliation/context body=[customerId:integer|term:integer|year:integer]
GET /salary/holidayAllowance/reconciliation/{reconciliationId}/holidayAllowanceDetails params=[fields]
GET /salary/holidayAllowance/reconciliation/{reconciliationId}/holidayAllowanceSummary params=[fields]
POST /salary/mandatoryDeduction/reconciliation/context body=[customerId:integer|term:integer|year:integer]
GET /salary/mandatoryDeduction/reconciliation/{reconciliationId}/overview params=[fields]
GET /salary/mandatoryDeduction/reconciliation/{reconciliationId}/paymentsOverview params=[fields]
POST /salary/payrollTax/reconciliation/context body=[customerId:integer|term:integer|year:integer]
GET /salary/payrollTax/reconciliation/{reconciliationId}/overview params=[fields]
GET /salary/payrollTax/reconciliation/{reconciliationId}/paymentsOverview params=[fields]
GET /salary/payslip params=[id,employeeId,wageTransactionId,activityId,yearFrom,yearTo,monthFrom,monthTo,voucherDateFrom,voucherDateTo,comment,from]
GET /salary/payslip/{id} params=[fields]
GET /salary/payslip/{id}/pdf
GET /salary/settings params=[fields]
PUT /salary/settings body=[municipality:Municipality|payrollTaxCalcMethod:string(AA|BB|CC|C2|DD)]
GET /salary/settings/holiday params=[from,count,sorting,fields]
POST /salary/settings/holiday body=[days:number|isMaxPercentage2Amount6G:boolean|vacationPayPercentage1:number|vacationPayPercentage2:number|year:integer]
POST /salary/settings/holiday/list
PUT /salary/settings/holiday/list
DELETE /salary/settings/holiday/list
PUT /salary/settings/holiday/{id} body=[days:number|isMaxPercentage2Amount6G:boolean|vacationPayPercentage1:number|vacationPayPercentage2:number|year:integer]
GET /salary/settings/pensionScheme params=[number,from,count,sorting,fields]
POST /salary/settings/pensionScheme body=[endDate:string|number:string|pensionSchemeId:integer|startDate:string]
POST /salary/settings/pensionScheme/list
PUT /salary/settings/pensionScheme/list
DELETE /salary/settings/pensionScheme/list
GET /salary/settings/pensionScheme/{id} params=[fields]
PUT /salary/settings/pensionScheme/{id} body=[endDate:string|number:string|pensionSchemeId:integer|startDate:string]
DELETE /salary/settings/pensionScheme/{id}
GET /salary/settings/standardTime params=[from,count,sorting,fields]
POST /salary/settings/standardTime body=[company:Company|fromDate:string|hoursPerDay:number]
GET /salary/settings/standardTime/byDate params=[date,fields]
GET /salary/settings/standardTime/{id} params=[fields]
PUT /salary/settings/standardTime/{id} body=[company:Company|fromDate:string|hoursPerDay:number]
POST /salary/taxDeduction/reconciliation/context body=[customerId:integer|term:integer|year:integer]
GET /salary/taxDeduction/reconciliation/{reconciliationId}/balanceAndOwedAmount params=[fields]
GET /salary/taxDeduction/reconciliation/{reconciliationId}/overview params=[fields]
GET /salary/taxDeduction/reconciliation/{reconciliationId}/paymentsOverview params=[fields]
POST /salary/transaction body=[date:string|isHistorical:boolean|month:integer|paySlipsAvailableDate:string|payslips:array|year:integer]
GET /salary/transaction/{id} params=[fields]
DELETE /salary/transaction/{id}
POST /salary/transaction/{id}/attachment
POST /salary/transaction/{id}/attachment/list
PUT /salary/transaction/{id}/deleteAttachment params=[sendToVoucherInbox,split]
GET /salary/type params=[id,number,name,description,showInTimesheet,isInactive,employeeIds,from,count,sorting,fields]
GET /salary/type/{id} params=[fields]
GET /supplier params=[id,supplierNumber,organizationNumber,email,invoiceEmail,isInactive,accountManagerId,changedSince,isWholesaler,showProducts,from,count]
POST /supplier body=[accountManager:Employee|bankAccountPresentation:array|bankAccounts:array|category1:CustomerCategory|category2:CustomerCategory|category3:CustomerCategory|currency:Currency|customerNumber:integer|deliveryAddress:DeliveryAddress|description:string|email:string|invoiceEmail:string|isCustomer:boolean|isInactive:boolean|isPrivateIndividual:boolean|language:string(NO|EN)|ledgerAccount:Account|name:string|organizationNumber:string|overdueNoticeEmail:string|phoneNumber:string|phoneNumberMobile:string|physicalAddress:Address|postalAddress:Address|showProducts:boolean|supplierNumber:integer|website:string]
POST /supplier/list
PUT /supplier/list
GET /supplier/{id} params=[fields]
PUT /supplier/{id} body=[accountManager:Employee|bankAccountPresentation:array|bankAccounts:array|category1:CustomerCategory|category2:CustomerCategory|category3:CustomerCategory|currency:Currency|customerNumber:integer|deliveryAddress:DeliveryAddress|description:string|email:string|invoiceEmail:string|isCustomer:boolean|isInactive:boolean|isPrivateIndividual:boolean|language:string(NO|EN)|ledgerAccount:Account|name:string|organizationNumber:string|overdueNoticeEmail:string|phoneNumber:string|phoneNumberMobile:string|physicalAddress:Address|postalAddress:Address|showProducts:boolean|supplierNumber:integer|website:string]
DELETE /supplier/{id}
GET /supplierCustomer/search params=[query,from,count,sorting,fields]
GET /supplierInvoice params=[id,invoiceDateFrom,invoiceDateTo,invoiceNumber,kid,voucherId,supplierId,from,count,sorting,fields]
PUT /supplierInvoice/:addRecipient params=[employeeId,invoiceIds,comment]
PUT /supplierInvoice/:approve params=[invoiceIds,comment]
PUT /supplierInvoice/:reject params=[comment,invoiceIds]
GET /supplierInvoice/forApproval params=[searchText,showAll,employeeId,from,count,sorting,fields]
PUT /supplierInvoice/voucher/{id}/postings [BETA-MAY-403] params=[sendToLedger,voucherDate]
GET /supplierInvoice/{id} params=[fields]
POST /supplierInvoice/{invoiceId}/:addPayment
PUT /supplierInvoice/{invoiceId}/:addRecipient params=[employeeId,comment]
PUT /supplierInvoice/{invoiceId}/:approve params=[comment]
PUT /supplierInvoice/{invoiceId}/:changeDimension params=[debitPostingIds,dimension,dimensionId]
PUT /supplierInvoice/{invoiceId}/:reject params=[comment]
GET /supplierInvoice/{invoiceId}/pdf
GET /timesheet/allocated params=[ids,employeeIds,projectIds,activityIds,dateFrom,dateTo,from,count,sorting,fields]
POST /timesheet/allocated body=[activity:Activity|date:string|employee:Employee|hours:number|isApproved:boolean|managerComment:string|project:Project]
PUT /timesheet/allocated/:approveList params=[ids,employeeIds,dateFrom,dateTo,managerComment]
PUT /timesheet/allocated/:unapproveList params=[ids,employeeIds,dateFrom,dateTo,managerComment]
POST /timesheet/allocated/list
PUT /timesheet/allocated/list
GET /timesheet/allocated/{id} params=[fields]
PUT /timesheet/allocated/{id} body=[activity:Activity|date:string|employee:Employee|hours:number|isApproved:boolean|managerComment:string|project:Project]
DELETE /timesheet/allocated/{id}
PUT /timesheet/allocated/{id}/:approve params=[managerComment]
PUT /timesheet/allocated/{id}/:unapprove params=[managerComment]
GET /timesheet/companyHoliday [BETA-MAY-403] params=[ids,years,from,count,sorting,fields]
POST /timesheet/companyHoliday [BETA-MAY-403] body=[date:string|percentage:number]
GET /timesheet/companyHoliday/{id} [BETA-MAY-403] params=[fields]
PUT /timesheet/companyHoliday/{id} [BETA-MAY-403] body=[date:string|percentage:number]
DELETE /timesheet/companyHoliday/{id} [BETA-MAY-403]
GET /timesheet/entry params=[id,employeeId,projectId,activityId,dateFrom,dateTo,comment,from,count,sorting,fields]
POST /timesheet/entry body=[activity:Activity|comment:string|date:string|employee:Employee|hours:number|invoice:Invoice|project:Project|projectChargeableHours:number]
GET /timesheet/entry/>recentActivities params=[employeeId,projectId,from,count,sorting,fields]
GET /timesheet/entry/>recentProjects params=[employeeId,from,count,sorting,fields]
GET /timesheet/entry/>totalHours params=[employeeId,startDate,endDate,fields]
POST /timesheet/entry/list
PUT /timesheet/entry/list
GET /timesheet/entry/{id} params=[fields]
PUT /timesheet/entry/{id} body=[activity:Activity|comment:string|date:string|employee:Employee|hours:number|invoice:Invoice|project:Project|projectChargeableHours:number]
DELETE /timesheet/entry/{id}
PUT /timesheet/month/:approve params=[id,employeeIds,monthYear,approvedUntilDate]
PUT /timesheet/month/:complete params=[id,employeeIds,monthYear]
PUT /timesheet/month/:reopen params=[id,employeeIds,monthYear]
PUT /timesheet/month/:unapprove params=[id,employeeIds,monthYear]
GET /timesheet/month/byMonthNumber params=[employeeIds,monthYear,from,count,sorting,fields]
GET /timesheet/month/byMonthNumberList params=[employeeIds,monthYearList,from,count,sorting,fields]
GET /timesheet/month/{id} params=[fields]
GET /timesheet/salaryProjectTypeSpecification params=[dateFrom,dateTo,employeeId,projectId,activityId,includeNotConnectedToActivities,from,count,sorting,fields]
POST /timesheet/salaryProjectTypeSpecification body=[activity:Activity|count:number|date:string|description:string|employee:Employee|project:Project|salaryType:SalaryType|wagePayment:Payslip]
GET /timesheet/salaryProjectTypeSpecification/{id} params=[fields]
PUT /timesheet/salaryProjectTypeSpecification/{id} body=[activity:Activity|count:number|date:string|description:string|employee:Employee|project:Project|salaryType:SalaryType|wagePayment:Payslip]
DELETE /timesheet/salaryProjectTypeSpecification/{id}
GET /timesheet/salaryTypeSpecification [BETA-MAY-403] params=[dateFrom,dateTo,employeeId,from,count,sorting,fields]
POST /timesheet/salaryTypeSpecification [BETA-MAY-403] body=[count:number|date:string|description:string|employee:Employee|salaryType:SalaryType]
GET /timesheet/salaryTypeSpecification/{id} [BETA-MAY-403] params=[fields]
PUT /timesheet/salaryTypeSpecification/{id} [BETA-MAY-403] body=[count:number|date:string|description:string|employee:Employee|salaryType:SalaryType]
DELETE /timesheet/salaryTypeSpecification/{id} [BETA-MAY-403]
GET /timesheet/settings [BETA-MAY-403] params=[fields]
GET /timesheet/timeClock params=[id,employeeId,projectId,activityId,dateFrom,dateTo,hourId,isRunning,from,count,sorting,fields]
PUT /timesheet/timeClock/:start params=[employeeId,projectId,activityId,date,lunchBreakDuration,comment]
GET /timesheet/timeClock/present params=[employeeId,fields]
GET /timesheet/timeClock/{id} params=[fields]
PUT /timesheet/timeClock/{id} body=[activity:Activity|date:string|employee:Employee|hoursStart:number|lunchBreakDuration:number|project:Project|timeStart:string|timeStop:string|timesheetEntry:TimesheetEntry]
PUT /timesheet/timeClock/{id}/:stop params=[version,comment]
GET /timesheet/week params=[ids,employeeIds,weekYear,approvedBy,from,count,sorting,fields]
PUT /timesheet/week/:approve params=[id,employeeId,weekYear]
PUT /timesheet/week/:complete params=[id,employeeId,weekYear]
PUT /timesheet/week/:reopen params=[id,employeeId,weekYear]
PUT /timesheet/week/:unapprove params=[id,employeeId,weekYear]
GET /travelExpense params=[employeeId,departmentId,projectId,projectManagerId,departureDateFrom,returnDateTo,state,from,count,sorting,fields]
POST /travelExpense body=[approvedBy:Employee|attachment:Document|attestation:Attestation|attestationSteps:array|completedBy:Employee|costs:array|department:Department|employee:Employee|fixedInvoicedAmount:number|freeDimension1:AccountingDimensionValue|freeDimension2:AccountingDimensionValue|freeDimension3:AccountingDimensionValue|invoice:Invoice|isChargeable:boolean|isFixedInvoicedAmount:boolean|isIncludeAttachedReceiptsWhenReinvoicing:boolean|isMarkupInvoicedPercent:boolean|markupInvoicedPercent:number|paymentCurrency:Currency|payslip:Payslip|perDiemCompensations:array|project:Project|rejectedBy:Employee|title:string|travelAdvance:number|travelDetails:TravelDetails|vatType:VatType|voucher:Voucher]
PUT /travelExpense/:approve params=[id,overrideApprovalFlow]
PUT /travelExpense/:copy params=[id]
PUT /travelExpense/:createVouchers params=[id,date]
PUT /travelExpense/:deliver params=[id]
PUT /travelExpense/:unapprove params=[id]
PUT /travelExpense/:undeliver body=[approvedBy:Employee|attachment:Document|attestation:Attestation|attestationSteps:array|completedBy:Employee|costs:array|department:Department|employee:Employee|fixedInvoicedAmount:number|freeDimension1:AccountingDimensionValue|freeDimension2:AccountingDimensionValue|freeDimension3:AccountingDimensionValue|invoice:Invoice|isChargeable:boolean|isFixedInvoicedAmount:boolean|isIncludeAttachedReceiptsWhenReinvoicing:boolean|isMarkupInvoicedPercent:boolean|markupInvoicedPercent:number|paymentCurrency:Currency|payslip:Payslip|perDiemCompensations:array|project:Project|rejectedBy:Employee|title:string|travelAdvance:number|travelDetails:TravelDetails|vatType:VatType|voucher:Voucher] params=[id]
GET /travelExpense/accommodationAllowance params=[travelExpenseId,rateTypeId,rateCategoryId,rateFrom,rateTo,countFrom,countTo,amountFrom,amountTo,location,address,from]
POST /travelExpense/accommodationAllowance body=[address:string|amount:number|count:integer|location:string|rate:number|rateCategory:TravelExpenseRateCategory|rateType:TravelExpenseRate|travelExpense:TravelExpense|zone:string]
GET /travelExpense/accommodationAllowance/{id} params=[fields]
PUT /travelExpense/accommodationAllowance/{id} body=[address:string|amount:number|count:integer|location:string|rate:number|rateCategory:TravelExpenseRateCategory|rateType:TravelExpenseRate|travelExpense:TravelExpense|zone:string]
DELETE /travelExpense/accommodationAllowance/{id}
GET /travelExpense/cost params=[travelExpenseId,vatTypeId,currencyId,rateFrom,rateTo,countFrom,countTo,amountFrom,amountTo,location,address,from]
POST /travelExpense/cost body=[amountCurrencyIncVat:number|amountNOKInclVAT:number|category:string|comments:string|costCategory:TravelCostCategory|currency:Currency|date:string|isChargeable:boolean|participants:array|paymentType:TravelPaymentType|predictions:object|rate:number|travelExpense:TravelExpense|vatType:VatType]
PUT /travelExpense/cost/list
GET /travelExpense/cost/{id} params=[fields]
PUT /travelExpense/cost/{id} body=[amountCurrencyIncVat:number|amountNOKInclVAT:number|category:string|comments:string|costCategory:TravelCostCategory|currency:Currency|date:string|isChargeable:boolean|participants:array|paymentType:TravelPaymentType|predictions:object|rate:number|travelExpense:TravelExpense|vatType:VatType]
DELETE /travelExpense/cost/{id}
GET /travelExpense/costCategory params=[id,description,isInactive,showOnEmployeeExpenses,query,from,count,sorting,fields]
GET /travelExpense/costCategory/{id} params=[fields]
POST /travelExpense/costParticipant body=[cost:Cost|employeeId:integer]
POST /travelExpense/costParticipant/createCostParticipantAdvanced
POST /travelExpense/costParticipant/list
DELETE /travelExpense/costParticipant/list
GET /travelExpense/costParticipant/{costId}/costParticipants params=[from,count,sorting,fields]
GET /travelExpense/costParticipant/{id} params=[fields]
DELETE /travelExpense/costParticipant/{id}
POST /travelExpense/drivingStop body=[latitude:number|locationName:string|longitude:number|mileageAllowance:MileageAllowance|sortIndex:integer|type:integer]
GET /travelExpense/drivingStop/{id} params=[fields]
DELETE /travelExpense/drivingStop/{id}
GET /travelExpense/mileageAllowance params=[travelExpenseId,rateTypeId,rateCategoryId,kmFrom,kmTo,rateFrom,rateTo,amountFrom,amountTo,departureLocation,destination,dateFrom]
POST /travelExpense/mileageAllowance body=[amount:number|date:string|departureLocation:string|destination:string|isCompanyCar:boolean|km:number|passengerSupplement:MileageAllowance|rate:number|rateCategory:TravelExpenseRateCategory|rateType:TravelExpenseRate|tollCost:Cost|trailerSupplement:MileageAllowance|travelExpense:TravelExpense|vehicleType:integer]
GET /travelExpense/mileageAllowance/{id} params=[fields]
PUT /travelExpense/mileageAllowance/{id} body=[amount:number|date:string|departureLocation:string|destination:string|isCompanyCar:boolean|km:number|passengerSupplement:MileageAllowance|rate:number|rateCategory:TravelExpenseRateCategory|rateType:TravelExpenseRate|tollCost:Cost|trailerSupplement:MileageAllowance|travelExpense:TravelExpense|vehicleType:integer]
DELETE /travelExpense/mileageAllowance/{id}
GET /travelExpense/passenger params=[mileageAllowance,name,from,count,sorting,fields]
POST /travelExpense/passenger body=[mileageAllowance:MileageAllowance|name:string]
POST /travelExpense/passenger/list
DELETE /travelExpense/passenger/list
GET /travelExpense/passenger/{id} params=[fields]
PUT /travelExpense/passenger/{id} body=[mileageAllowance:MileageAllowance|name:string]
DELETE /travelExpense/passenger/{id}
GET /travelExpense/paymentType params=[id,description,isInactive,showOnEmployeeExpenses,query,from,count,sorting,fields]
GET /travelExpense/paymentType/{id} params=[fields]
GET /travelExpense/perDiemCompensation params=[travelExpenseId,rateTypeId,rateCategoryId,overnightAccommodation,countFrom,countTo,rateFrom,rateTo,amountFrom,amountTo,location,address]
POST /travelExpense/perDiemCompensation body=[address:string|amount:number|count:integer|countryCode:string|isDeductionForBreakfast:boolean|isDeductionForDinner:boolean|isDeductionForLunch:boolean|location:string|overnightAccommodation:string(NONE|HOTEL|BOARDING_HOUSE_WITHOUT_COOKING|BOARDING_HOUSE_WITH_COOKING)|rate:number|rateCategory:TravelExpenseRateCategory|rateType:TravelExpenseRate|travelExpense:TravelExpense|travelExpenseZoneId:integer]
GET /travelExpense/perDiemCompensation/{id} params=[fields]
PUT /travelExpense/perDiemCompensation/{id} body=[address:string|amount:number|count:integer|countryCode:string|isDeductionForBreakfast:boolean|isDeductionForDinner:boolean|isDeductionForLunch:boolean|location:string|overnightAccommodation:string(NONE|HOTEL|BOARDING_HOUSE_WITHOUT_COOKING|BOARDING_HOUSE_WITH_COOKING)|rate:number|rateCategory:TravelExpenseRateCategory|rateType:TravelExpenseRate|travelExpense:TravelExpense|travelExpenseZoneId:integer]
DELETE /travelExpense/perDiemCompensation/{id}
GET /travelExpense/rate params=[rateCategoryId,type,isValidDayTrip,isValidAccommodation,isValidDomestic,isValidForeignTravel,requiresZone,requiresOvernightAccommodation,dateFrom,dateTo,from,count]
GET /travelExpense/rate/{id} params=[fields]
GET /travelExpense/rateCategory params=[type,name,travelReportRateCategoryGroupId,ameldingWageCode,wageCodeNumber,isValidDayTrip,isValidAccommodation,isValidDomestic,requiresZone,isRequiresOvernightAccommodation,dateFrom,dateTo]
GET /travelExpense/rateCategory/{id} params=[fields]
GET /travelExpense/rateCategoryGroup params=[name,isForeignTravel,dateFrom,dateTo,from,count,sorting,fields]
GET /travelExpense/rateCategoryGroup/{id} params=[fields]
GET /travelExpense/settings params=[fields]
GET /travelExpense/zone params=[id,code,isDisabled,query,date,from,count,sorting,fields]
GET /travelExpense/zone/{id} params=[fields]
GET /travelExpense/{id} params=[fields]
PUT /travelExpense/{id} body=[approvedBy:Employee|attachment:Document|attestation:Attestation|attestationSteps:array|completedBy:Employee|costs:array|department:Department|employee:Employee|fixedInvoicedAmount:number|freeDimension1:AccountingDimensionValue|freeDimension2:AccountingDimensionValue|freeDimension3:AccountingDimensionValue|invoice:Invoice|isChargeable:boolean|isFixedInvoicedAmount:boolean|isIncludeAttachedReceiptsWhenReinvoicing:boolean|isMarkupInvoicedPercent:boolean|markupInvoicedPercent:number|paymentCurrency:Currency|payslip:Payslip|perDiemCompensations:array|project:Project|rejectedBy:Employee|title:string|travelAdvance:number|travelDetails:TravelDetails|vatType:VatType|voucher:Voucher]
DELETE /travelExpense/{id}
PUT /travelExpense/{id}/convert
GET /travelExpense/{travelExpenseId}/attachment
POST /travelExpense/{travelExpenseId}/attachment
DELETE /travelExpense/{travelExpenseId}/attachment
POST /travelExpense/{travelExpenseId}/attachment/list
"""