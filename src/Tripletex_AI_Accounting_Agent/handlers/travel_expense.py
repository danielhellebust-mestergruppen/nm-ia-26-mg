import logging
from datetime import date, timedelta

from handlers.base import BaseHandler
from llm.schemas import TaskPlan

logger = logging.getLogger("handler.travel_expense")


class CreateTravelExpenseHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities
        today = date.today().isoformat()

        # Find employee
        employee_id = e.get("employeeId")
        if not employee_id and e.get("employeeName"):
            name = e["employeeName"]
            result = await self.client.get("/employee", params={
                "firstName": name.split()[0],
                "fields": "id,firstName,lastName",
                "count": 5,
            })
            employees = result.get("values", [])
            if employees:
                employee_id = employees[0]["id"]

        if not employee_id:
            result = await self.client.get("/employee", params={"fields": "id", "count": 1})
            employees = result.get("values", [])
            if employees:
                employee_id = employees[0]["id"]

        body: dict = {
            "employee": {"id": employee_id},
            "title": e.get("title") or e.get("description") or "Travel Expense",
        }

        # Travel details — always set dates
        travel_details = {}
        dep_date = e.get("departureDate") or e.get("date") or e.get("startDate") or today
        ret_date = e.get("returnDate") or e.get("endDate") or None

        # If the LLM guessed dates in the past, recalculate from today
        if dep_date < today:
            # Calculate duration from original dates if possible
            if ret_date and dep_date:
                try:
                    duration = (date.fromisoformat(ret_date) - date.fromisoformat(dep_date)).days
                except Exception:
                    duration = (int(e.get("perDiemDays", 1)) - 1) if e.get("perDiemDays") else 0
            elif e.get("perDiemDays"):
                duration = int(e["perDiemDays"]) - 1
            else:
                duration = 0
            dep_date = today
            ret_date = (date.fromisoformat(today) + timedelta(days=duration)).isoformat()
            logger.info(f"Overrode past dates: dep={dep_date} ret={ret_date} (duration={duration}d)")

        # If we have number of days but no return date, calculate it
        if not ret_date and e.get("perDiemDays"):
            dep = date.fromisoformat(dep_date)
            ret_date = (dep + timedelta(days=int(e["perDiemDays"]) - 1)).isoformat()
        if not ret_date:
            ret_date = dep_date
        travel_details["departureDate"] = dep_date
        travel_details["returnDate"] = ret_date
        if e.get("destination"):
            travel_details["destination"] = e["destination"]
        if e.get("purpose"):
            travel_details["purpose"] = e["purpose"]
        if e.get("departureFrom"):
            travel_details["departureFrom"] = e["departureFrom"]

        if travel_details:
            body["travelDetails"] = travel_details

        if e.get("projectId"):
            body["project"] = {"id": e["projectId"]}

        result = await self.client.post("/travelExpense", body)
        expense_id = result["value"]["id"]
        logger.info(f"Created travel expense id={expense_id}")

        # Add cost lines if provided — cache category lookup
        cost_categories = None
        if e.get("costs"):
            try:
                cat_result = await self.client.get("/travelExpense/costCategory", params={
                    "fields": "id,description", "count": 20,
                })
                cost_categories = cat_result.get("values", [])
            except Exception:
                cost_categories = []

        # Look up travel payment type (GETs are free)
        travel_payment_type_id = 0
        try:
            pt_result = await self.client.get("/travelExpense/paymentType", params={
                "fields": "id,description,showOnTravelExpenses", "count": 5,
            })
            for pt in pt_result.get("values", []):
                if pt.get("showOnTravelExpenses"):
                    travel_payment_type_id = pt["id"]
                    break
        except Exception:
            pass

        for cost in e.get("costs", []):
            await self._add_cost(expense_id, cost, cost_categories, travel_payment_type_id)

        # Add mileage allowance if provided
        if e.get("mileage") or e.get("kilometers"):
            await self._add_mileage(expense_id, e)

        # Add per diem if provided
        if e.get("perDiem") or e.get("dailyAllowance") or e.get("perDiemDays"):
            await self._add_per_diem(expense_id, e, dep_date, ret_date)

    async def _add_cost(self, expense_id: int, cost: dict, categories: list = None, payment_type_id: int = 0) -> None:
        """Add a cost line to a travel expense."""
        try:
            if categories is None:
                cat_result = await self.client.get("/travelExpense/costCategory", params={
                    "fields": "id,description", "count": 20,
                })
                categories = cat_result.get("values", [])
            category_id = categories[0]["id"] if categories else None

            # Smart category matching based on cost description
            cat_name = (cost.get("category") or cost.get("description") or "").lower()

            # Common keyword → category mappings
            keyword_map = {
                "fly": "fly", "flight": "fly", "avión": "fly", "avion": "fly", "avião": "fly",
                "bilhete de avião": "fly", "billet d'avion": "fly", "flybillett": "fly", "flug": "fly",
                "taxi": "taxi", "táxi": "taxi",
                "hotel": "hotell", "hotell": "hotell", "hôtel": "hotell",
                "tog": "tog", "train": "tog", "tren": "tog", "zug": "tog",
                "buss": "buss", "bus": "buss", "autobús": "buss", "ônibus": "buss",
                "parkering": "parkering", "parking": "parkering",
                "mat": "mat", "food": "mat", "comida": "mat",
                "drivstoff": "drivstoff", "fuel": "drivstoff", "bensin": "drivstoff",
                "ferge": "ferge", "ferry": "ferge",
            }

            # Find matching category keyword
            target_cat = None
            for keyword, cat_key in keyword_map.items():
                if keyword in cat_name:
                    target_cat = cat_key
                    break

            # Match to actual category
            if target_cat:
                for cat in categories:
                    if target_cat in (cat.get("description") or "").lower():
                        category_id = cat["id"]
                        break

            # Fallback: fuzzy match
            if not target_cat:
                for cat in categories:
                    if cat_name in (cat.get("description") or "").lower():
                        category_id = cat["id"]
                        break

            body = {
                "travelExpense": {"id": expense_id},
                "date": cost.get("date", date.today().isoformat()),
                "amountCurrencyIncVat": cost.get("amount", 0),
                "currency": {"id": 1},  # NOK
                "paymentType": {"id": payment_type_id},
            }
            if category_id:
                body["costCategory"] = {"id": category_id}

            await self.client.post("/travelExpense/cost", body)
            logger.info(f"Added cost {cost.get('amount', 0)} to expense {expense_id}")
        except Exception as ex:
            logger.warning(f"Failed to add cost: {ex}")

    async def _add_mileage(self, expense_id: int, e: dict) -> None:
        """Add mileage allowance to a travel expense."""
        try:
            km = e.get("mileage", e.get("kilometers", 0))
            body = {
                "travelExpense": {"id": expense_id},
                "date": e.get("date", date.today().isoformat()),
                "km": km,
                "rateTypeId": 1,  # Default rate type
            }
            await self.client.post("/travelExpense/mileageAllowance", body)
            logger.info(f"Added mileage {km}km to expense {expense_id}")
        except Exception as ex:
            logger.warning(f"Failed to add mileage: {ex}")

    async def _add_per_diem(self, expense_id: int, e: dict, dep_date: str, ret_date: str) -> None:
        """Add per diem compensation to a travel expense."""
        try:
            days = e.get("perDiemDays", 1)
            rate = e.get("perDiemRate", 800)
            if isinstance(days, str):
                days = int(days) if days.isdigit() else 1
            if isinstance(rate, str):
                rate = int(rate) if rate.isdigit() else 800

            # Find valid rate category — use /travelExpense/rate to find one matching today's dates
            rate_cat_id = None
            try:
                r = await self.client.get("/travelExpense/rate", params={
                    "isValidDomestic": "true",
                    "requiresOvernightAccommodation": "true",
                    "fields": "id,rateCategory",
                    "count": 20,
                })
                rates = r.get("values", [])
                # Pick the HIGHEST rateCategory ID (most recent, valid for current dates)
                best_id = 0
                for rt in rates:
                    rc = rt.get("rateCategory", {})
                    rc_id = rc.get("id", 0)
                    if rc_id > best_id:
                        best_id = rc_id
                if best_id:
                    rate_cat_id = best_id
                    logger.info(f"Using rate category {rate_cat_id} (most recent)")
            except Exception:
                pass
            if not rate_cat_id:
                rate_cat_id = 285  # Latest known domestic overnight category

            body = {
                "travelExpense": {"id": expense_id},
                "count": days,
                "rate": rate,
                "amount": days * rate,
                "overnightAccommodation": "HOTEL",
                "rateCategory": {"id": rate_cat_id},
            }
            if e.get("destination"):
                body["location"] = e["destination"]

            await self.client.post("/travelExpense/perDiemCompensation", body)
            logger.info(f"Added per diem: {days} days × {rate} = {days * rate} (rateCat={rate_cat_id}) to expense {expense_id}")
        except Exception as ex:
            logger.warning(f"Failed to add per diem: {ex}")


class UpdateTravelExpenseHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities

        # Find travel expense
        result = await self.client.get("/travelExpense", params={
            "fields": "id,version,title,employee,travelDetails,project,costs",
            "count": 100,
        })
        expenses = result.get("values", [])

        target = None
        title = (e.get("title") or e.get("description") or "").lower()
        for exp in expenses:
            if title and title in (exp.get("title") or "").lower():
                target = exp
                break
        if not target and expenses:
            target = expenses[0]

        if not target:
            logger.error("No travel expense found to update")
            return

        expense_id = target["id"]

        if e.get("title"):
            target["title"] = e["title"]

        await self.client.put(f"/travelExpense/{expense_id}", target)
        logger.info(f"Updated travel expense id={expense_id}")


class DeleteTravelExpenseHandler(BaseHandler):
    async def execute(self, plan: TaskPlan) -> None:
        e = plan.entities

        result = await self.client.get("/travelExpense", params={
            "fields": "id,title", "count": 100,
        })
        expenses = result.get("values", [])

        if not expenses:
            logger.error("No travel expenses found to delete")
            return

        target = None
        description = (e.get("description") or e.get("title") or "").lower()
        for exp in expenses:
            if description and description in (exp.get("title") or "").lower():
                target = exp
                break
        if not target:
            target = expenses[0]

        await self.client.delete(f"/travelExpense/{target['id']}")
        logger.info(f"Deleted travel expense id={target['id']}")
