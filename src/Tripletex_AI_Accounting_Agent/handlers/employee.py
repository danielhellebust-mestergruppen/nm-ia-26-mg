import logging
import unicodedata
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.employee")


async def get_default_department_id(client) -> int:
    """Find the default department in the account."""
    result = await client.get("/department", params={
        "fields": "id,name",
        "count": 1,
    })
    departments = result.get("values", [])
    if departments:
        return departments[0]["id"]
    dept = await client.post("/department", {"name": "Avdeling"})
    return dept["value"]["id"]


class CreateEmployeeHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities

        # Handle multiple employees
        items = e.get("items", [e])
        for item in items:
            if isinstance(item, str):
                parts = item.split()
                item = {"firstName": parts[0], "lastName": parts[-1] if len(parts) > 1 else ""}
            await self._create_one(item if "firstName" in item else e)

    async def _create_one(self, e: dict) -> None:
        # Find the right department (from PDF contract or default)
        dept_id = None
        if e.get("departmentName"):
            account_ctx = e.get("_account", {})
            for d in account_ctx.get("departments", []):
                if e["departmentName"].lower() in (d.get("name") or "").lower():
                    dept_id = d["id"]
                    break
            if not dept_id:
                # Search departments (GET is free)
                try:
                    result = await self.client.get("/department", params={
                        "fields": "id,name", "count": 20,
                    })
                    for d in result.get("values", []):
                        if e["departmentName"].lower() in (d.get("name") or "").lower():
                            dept_id = d["id"]
                            break
                except Exception:
                    pass

        if not dept_id and e.get("departmentName"):
            # Department not found — create it
            try:
                dept_result = await self.client.post("/department", {"name": e["departmentName"]})
                dept_id = dept_result["value"]["id"]
                logger.info(f"Created department '{e['departmentName']}' id={dept_id}")
            except Exception:
                dept_id = await get_default_department_id(self.client)
        elif not dept_id:
            dept_id = await get_default_department_id(self.client)

        # Use EXTENDED only for admins (requires email), STANDARD for regular employees
        is_admin = e.get("isAdministrator", False)
        user_type = "EXTENDED" if is_admin else "STANDARD"

        body: dict = {
            "firstName": e["firstName"],
            "lastName": e["lastName"],
            "userType": user_type,
            "department": {"id": dept_id},
        }

        # Email — set if available (required for EXTENDED, optional for STANDARD)
        email = e.get("email")
        if not email and is_admin:
            # Only generate default email for admin users who need EXTENDED
            fn = unicodedata.normalize("NFKD", e["firstName"]).encode("ascii", "ignore").decode().lower().replace(" ", ".")
            ln = unicodedata.normalize("NFKD", e["lastName"]).encode("ascii", "ignore").decode().lower().replace(" ", ".")
            email = f"{fn}.{ln}@example.org"
        if email:
            body["email"] = email
        if e.get("dateOfBirth"):
            body["dateOfBirth"] = e["dateOfBirth"]
        if e.get("phoneNumber"):
            body["phoneNumberMobile"] = e["phoneNumber"]
        if e.get("employeeNumber"):
            emp_num = str(e["employeeNumber"])
            # Personnummer (11 digits) goes to nationalIdentityNumber, not employeeNumber
            if len(emp_num) == 11 and emp_num.isdigit():
                body["nationalIdentityNumber"] = emp_num
            else:
                body["employeeNumber"] = emp_num
        if e.get("bankAccountNumber"):
            body["bankAccountNumber"] = str(e["bankAccountNumber"])
        if e.get("address"):
            body["address"] = {
                "addressLine1": e.get("address", ""),
                "postalCode": e.get("postalCode", ""),
                "city": e.get("city", ""),
            }

        result = await self.post_with_retry("/employee", body, fixups={
            "dateOfBirth": "1990-01-01",
        })
        employee_id = result["value"]["id"]
        logger.info(f"Created employee id={employee_id}")

        # Set employment details (startDate, salary, percentage, job code)
        has_employment_data = e.get("startDate") or e.get("annualSalary") or e.get("employmentPercentage")
        if has_employment_data:
            try:
                emp_result = await self.client.get("/employee/employment", params={
                    "employeeId": employee_id,
                    "fields": "*",
                    "count": 1,
                })
                employments = emp_result.get("values", [])

                if employments:
                    emp_record = employments[0]
                    if e.get("startDate"):
                        emp_record["startDate"] = e["startDate"]
                    await self.client.put(f"/employee/employment/{emp_record['id']}", emp_record)
                    employment_id = emp_record["id"]
                    logger.info(f"Updated employment {employment_id}")

                    # Set employment details (salary, percentage, job code)
                    if e.get("annualSalary") or e.get("employmentPercentage") or e.get("jobCode"):
                        try:
                            details = await self.client.get("/employee/employment/details", params={
                                "employmentId": employment_id,
                                "fields": "*",
                                "count": 1,
                            })
                            detail_records = details.get("values", [])
                            if detail_records:
                                detail = detail_records[0]
                                if e.get("annualSalary"):
                                    detail["annualSalary"] = e["annualSalary"]
                                if e.get("employmentPercentage"):
                                    detail["percentageOfFullTimeEquivalent"] = e["employmentPercentage"]
                                if e.get("jobCode"):
                                    detail["occupationCode"] = {"code": str(e["jobCode"])}
                                # Employment form + remuneration type
                                emp_form = (e.get("employmentType") or "").lower()
                                if "fast" in emp_form or "permanent" in emp_form:
                                    detail["employmentForm"] = "PERMANENT"
                                sal_type = (e.get("salaryType") or "").lower()
                                if "fast" in sal_type or "månedlig" in sal_type:
                                    detail["remunerationType"] = "MONTHLY_WAGE"
                                detail["employmentType"] = "ORDINARY"
                                await self.client.put(f"/employee/employment/details/{detail['id']}", detail)
                                logger.info(f"Updated employment details: salary={e.get('annualSalary')}, pct={e.get('employmentPercentage')}")
                            else:
                                # Create details
                                detail_body = {
                                    "employment": {"id": employment_id},
                                    "date": e.get("startDate") or date.today().isoformat(),
                                }
                                if e.get("annualSalary"):
                                    detail_body["annualSalary"] = e["annualSalary"]
                                if e.get("employmentPercentage"):
                                    detail_body["percentageOfFullTimeEquivalent"] = e["employmentPercentage"]
                                if e.get("jobCode"):
                                    detail_body["occupationCode"] = {"code": str(e["jobCode"])}
                                await self.client.post("/employee/employment/details", detail_body)
                                logger.info(f"Created employment details")
                        except Exception as ex:
                            logger.warning(f"Could not set employment details: {ex}")
                else:
                    # Create employment
                    emp_body = {
                        "employee": {"id": employee_id},
                        "startDate": e.get("startDate") or date.today().isoformat(),
                        "isMainEmployer": True,
                    }
                    # Note: employmentType field does NOT exist on the Tripletex employment entity
                    emp_create_result = await self.client.post("/employee/employment", emp_body)
                    employment_id = emp_create_result["value"]["id"]
                    logger.info(f"Created employment id={employment_id}")

                    # Now set employment details (salary, percentage, job code, form, type)
                    if e.get("annualSalary") or e.get("employmentPercentage") or e.get("jobCode"):
                        try:
                            detail_body = {
                                "employment": {"id": employment_id},
                                "date": e.get("startDate") or date.today().isoformat(),
                            }
                            if e.get("annualSalary"):
                                detail_body["annualSalary"] = e["annualSalary"]
                            if e.get("employmentPercentage"):
                                detail_body["percentageOfFullTimeEquivalent"] = e["employmentPercentage"]
                            if e.get("jobCode"):
                                detail_body["occupationCode"] = {"code": str(e["jobCode"])}
                            # Employment form: "Fast stilling" → PERMANENT
                            emp_form = (e.get("employmentType") or "").lower()
                            if "fast" in emp_form or "permanent" in emp_form:
                                detail_body["employmentForm"] = "PERMANENT"
                            elif "midlertidig" in emp_form or "temporary" in emp_form:
                                detail_body["employmentForm"] = "TEMPORARY"
                            # Remuneration type: "Fastlønn" → MONTHLY_WAGE
                            sal_type = (e.get("salaryType") or "").lower()
                            if "fast" in sal_type or "månedlig" in sal_type or "monthly" in sal_type:
                                detail_body["remunerationType"] = "MONTHLY_WAGE"
                            elif "time" in sal_type or "hourly" in sal_type:
                                detail_body["remunerationType"] = "HOURLY_WAGE"
                            # Employment type: default ORDINARY
                            detail_body["employmentType"] = "ORDINARY"
                            await self.client.post("/employee/employment/details", detail_body)
                            logger.info(f"Created employment details: salary={e.get('annualSalary')}, form={detail_body.get('employmentForm')}, remuneration={detail_body.get('remunerationType')}")
                        except Exception as ex:
                            logger.warning(f"Could not set employment details: {ex}")
            except Exception as ex:
                logger.warning(f"Could not set employment: {ex}")

        self.verify(result, {
            "firstName": e["firstName"],
            "lastName": e["lastName"],
            "email": e.get("email"),
        })

        # Set admin role via entitlements template [BETA endpoint — may 403]
        if e.get("isAdministrator"):
            try:
                logger.info(f"Granting ALL_PRIVILEGES to employee {employee_id}")
                await self.client.put(
                    f"/employee/entitlement/:grantEntitlementsByTemplate"
                    f"?employeeId={employee_id}&template=ALL_PRIVILEGES",
                    {}
                )
                logger.info(f"Administrator role set for employee {employee_id}")
            except Exception as ex:
                logger.warning(f"Could not set admin role (BETA endpoint): {ex}")

        # Set standard working hours (7.5h/day is Norwegian standard)
        try:
            await self.client.post("/employee/standardTime", {
                "employee": {"id": employee_id},
                "fromDate": e.get("startDate") or date.today().isoformat(),
                "hoursPerDay": 7.5,
            })
            logger.info(f"Set standard working hours 7.5h/day for employee {employee_id}")
        except Exception as ex:
            logger.warning(f"Could not set standard working hours: {ex}")


class UpdateEmployeeHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        search_name = e.get("searchName", "")

        params = {"fields": "id,version,firstName,lastName,email,phoneNumberMobile,dateOfBirth,dateOfEmployment,address,department,userType", "count": 5}
        if search_name:
            parts = search_name.split()
            params["firstName"] = parts[0]
            if len(parts) > 1:
                params["lastName"] = parts[-1]

        result = await self.client.get("/employee", params=params)
        employees = result.get("values", [])

        if not employees:
            logger.error(f"No employee found matching: {search_name}")
            return

        emp = employees[0]
        employee_id = emp["id"]

        if e.get("firstName"):
            emp["firstName"] = e["firstName"]
        if e.get("lastName"):
            emp["lastName"] = e["lastName"]
        if e.get("email"):
            emp["email"] = e["email"]
        if e.get("phoneNumber"):
            emp["phoneNumberMobile"] = e["phoneNumber"]
        if e.get("dateOfBirth"):
            emp["dateOfBirth"] = e["dateOfBirth"]
        if e.get("address"):
            emp["address"] = emp.get("address") or {}
            emp["address"]["addressLine1"] = e["address"]
        if e.get("postalCode"):
            emp["address"] = emp.get("address") or {}
            emp["address"]["postalCode"] = e["postalCode"]
        if e.get("city"):
            emp["address"] = emp.get("address") or {}
            emp["address"]["city"] = e["city"]

        updated = await self.client.put(f"/employee/{employee_id}", emp)
        logger.info(f"Updated employee id={employee_id}")

        if e.get("isAdministrator"):
            await self.client.put(
                f"/employee/entitlement/:grantEntitlementsByTemplate"
                f"?employeeId={employee_id}&template=ALL_PRIVILEGES",
                {}
            )
            logger.info(f"Administrator role set for employee {employee_id}")
