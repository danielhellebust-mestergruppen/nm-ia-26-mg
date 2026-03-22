import logging
from datetime import date

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.salary")


async def ensure_division(client) -> int:
    """Ensure a division exists, create one if needed. Returns division ID."""
    result = await client.get("/division", params={"fields": "id,name", "count": 1})
    divisions = result.get("values", [])
    if divisions:
        return divisions[0]["id"]

    # Create division — needs municipality
    muni = await client.get("/municipality", params={"fields": "id", "count": 1})
    muni_id = muni["values"][0]["id"] if muni.get("values") else 1

    div_result = await client.post("/division", {
        "name": "Hovedkontor",
        "organizationNumber": "999999999",
        "startDate": "2026-01-01",
        "municipality": {"id": muni_id},
        "municipalityDate": "2026-01-01",
    })
    div_id = div_result["value"]["id"]
    logger.info(f"Created division id={div_id}")
    return div_id


async def ensure_employee_for_payroll(client, employee_id: int, div_id: int, is_new_employee: bool = False) -> None:
    """Ensure employee has employment linked to division for payroll.
    Only modifies employee data if is_new_employee=True (we created them)."""

    # Only set dateOfBirth on employees WE created (not pre-existing)
    if is_new_employee:
        try:
            emp = (await client.get(f"/employee/{employee_id}", params={
                "fields": "id,version,dateOfBirth",
            }))["value"]
            if not emp.get("dateOfBirth"):
                emp["dateOfBirth"] = "1990-01-15"
                await client.put(f"/employee/{employee_id}", emp)
                logger.info(f"Set dateOfBirth on new employee {employee_id}")
        except Exception as ex:
            logger.warning(f"Could not set dateOfBirth: {ex}")

    # Check existing employment — link to division if needed, create only if none exists
    emp_records = (await client.get("/employee/employment", params={
        "employeeId": employee_id, "fields": "*", "count": 5,
    })).get("values", [])

    if emp_records:
        record = emp_records[0]
        if not record.get("division"):
            record["division"] = {"id": div_id}
            await client.put(f"/employee/employment/{record['id']}", record)
            logger.info(f"Linked existing employment {record['id']} to division {div_id}")
        else:
            logger.info(f"Employee already has employment with division — no changes needed")
    else:
        emp_body = {
            "employee": {"id": employee_id},
            "startDate": "2026-01-01",
            "isMainEmployer": True,
            "division": {"id": div_id},
        }
        await client.post("/employee/employment", emp_body)
        logger.info(f"Created employment for employee {employee_id} with division {div_id}")


class RunPayrollHandler(BaseHandler):
    """Run payroll via salary/transaction API (with proper division setup)."""

    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today()

        # Find or create employee
        employee_id = None
        if e.get("employeeName"):
            name = e["employeeName"]
            parts = name.split()
            params = {"fields": "id,firstName,lastName,email", "count": 5}
            params["firstName"] = parts[0]
            if len(parts) > 1:
                params["lastName"] = parts[-1]
            result = await self.client.get("/employee", params=params)
            for emp in result.get("values", []):
                fn = (emp.get("firstName") or "").lower()
                ln = (emp.get("lastName") or "").lower()
                em = (emp.get("email") or "").lower()
                # Strict match: both first AND last name, or email match
                target_email = (e.get("employeeEmail") or "").lower()
                if target_email and target_email == em:
                    employee_id = emp["id"]
                    break
                if parts[0].lower() == fn and len(parts) > 1 and parts[-1].lower() == ln:
                    employee_id = emp["id"]
                    break

        is_new_employee = False
        if not employee_id and e.get("employeeName"):
            # Create the employee
            import unicodedata
            parts = e["employeeName"].split()
            first = parts[0]
            last = parts[-1] if len(parts) > 1 else "Employee"
            email = e.get("employeeEmail") or ""
            if not email:
                fn = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode().lower()
                ln = unicodedata.normalize("NFKD", last).encode("ascii", "ignore").decode().lower()
                email = f"{fn}.{ln}@example.org"

            dept_result = await self.client.get("/department", params={"fields": "id", "count": 1})
            dept_id = dept_result.get("values", [{}])[0].get("id")

            emp_result = await self.client.post("/employee", {
                "firstName": first,
                "lastName": last,
                "email": email,
                "userType": "EXTENDED",
                "department": {"id": dept_id},
            })
            employee_id = emp_result["value"]["id"]
            is_new_employee = True
            logger.info(f"Created employee {e['employeeName']} id={employee_id}")

        if not employee_id:
            result = await self.client.get("/employee", params={"fields": "id", "count": 1})
            employees = result.get("values", [])
            if employees:
                employee_id = employees[0]["id"]

        # Setup: ensure division exists + employee linked
        div_id = await ensure_division(self.client)
        await ensure_employee_for_payroll(self.client, employee_id, div_id, is_new_employee)

        # Find salary types
        result = await self.client.get("/salary/type", params={
            "fields": "id,number,name", "count": 50,
        })
        salary_types = {}
        for st in result.get("values", []):
            salary_types[st["name"].lower()] = st["id"]
            salary_types[st["number"]] = st["id"]

        # Always use current month/year
        month = today.month
        year = today.year
        base_salary = e.get("baseSalary", e.get("amount", 0))
        bonus = e.get("bonus", 0)

        # Build payslip specifications
        specifications = []
        fastlonn_id = salary_types.get("fastlønn") or salary_types.get("2000")
        if fastlonn_id and base_salary:
            specifications.append({
                "salaryType": {"id": fastlonn_id},
                "amount": base_salary,
                "count": 1,
                "rate": base_salary,
                "month": month,
                "year": year,
            })

        if bonus:
            # Find bonus salary type
            bonus_id = None
            for key in salary_types:
                if "bonus" in key.lower() or "tillegg" in key.lower() or "engangs" in key.lower():
                    bonus_id = salary_types[key]
                    break
            if not bonus_id:
                bonus_id = fastlonn_id  # Use base salary type as fallback
            if bonus_id:
                specifications.append({
                    "salaryType": {"id": bonus_id},
                    "amount": bonus,
                    "count": 1,
                    "rate": bonus,
                    "month": month,
                    "year": year,
                })

        if not specifications:
            logger.error("No salary specifications could be built")
            return

        # Create salary transaction
        result = await self.client.post("/salary/transaction", {
            "date": today.isoformat(),
            "month": month,
            "year": year,
            "payslips": [{
                "employee": {"id": employee_id},
                "date": today.isoformat(),
                "month": month,
                "year": year,
                "specifications": specifications,
            }],
        })
        logger.info(f"Salary transaction created! id={result['value']['id']}")
