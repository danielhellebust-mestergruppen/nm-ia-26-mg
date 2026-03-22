from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
import logging
import re

from llm.schemas import TaskPlan
from tripletex_client.client import TripletexClient, ValidationError

logger = logging.getLogger("handler.base")

# Common validation errors and automatic fixes
AUTO_FIXES = {
    "Feltet må fylles ut": "required_field",      # "Field must be filled"
    "Kan ikke være null": "required_field",        # "Cannot be null"
    "er i bruk": "duplicate",                      # "is in use"
    "Finnes fra før": "duplicate",                 # "Already exists"
    "eksisterer ikke i objektet": "remove_field",  # "Field doesn't exist"
    "Ugyldig": "invalid_value",                    # "Invalid"
    "Brukertype kan ikke": "needs_usertype",       # "User type cannot"
}


class BaseHandler(ABC):
    def __init__(self, client: TripletexClient):
        self.client = client

    @abstractmethod
    async def execute(self, plan: TaskPlan) -> None:
        pass

    def verify(self, response: dict, expected: dict[str, object]) -> bool:
        """Check that the created/updated entity has expected field values."""
        value = response.get("value", response)
        ok = True
        for field, expected_val in expected.items():
            actual = value.get(field)
            if expected_val is not None and actual != expected_val:
                logger.warning(f"Verify: {field} expected={expected_val!r}, got={actual!r}")
                ok = False
        if ok:
            logger.info(f"Verify: all {len(expected)} fields match")
        return ok

    async def smart_post(self, path: str, body: dict) -> dict:
        """POST with intelligent retry on 422. Parses Tripletex error messages
        and applies automatic fixes before retrying once."""
        try:
            return await self.client.post(path, body)
        except ValidationError as e:
            logger.warning(f"smart_post {path} failed: {e.fields}")
            fixed = self._apply_auto_fixes(body, e)
            if fixed:
                logger.info(f"Retrying POST {path} after auto-fix")
                return await self.client.post(path, body)
            raise

    async def smart_put(self, path: str, body: dict, **kwargs) -> dict:
        """PUT with intelligent retry on 422."""
        try:
            return await self.client.put(path, body, **kwargs)
        except ValidationError as e:
            logger.warning(f"smart_put {path} failed: {e.fields}")
            fixed = self._apply_auto_fixes(body, e)
            if fixed:
                logger.info(f"Retrying PUT {path} after auto-fix")
                return await self.client.put(path, body, **kwargs)
            raise

    def _apply_auto_fixes(self, body: dict, error: ValidationError) -> bool:
        """Parse validation errors and apply fixes to the body. Returns True if anything was fixed."""
        fixed = False
        today = date.today().isoformat()

        for field, message in error.fields.items():
            # Determine fix type
            fix_type = None
            for pattern, ftype in AUTO_FIXES.items():
                if pattern.lower() in message.lower():
                    fix_type = ftype
                    break

            if not fix_type:
                continue

            if fix_type == "required_field":
                # Try to set a sensible default for required fields
                defaults = {
                    "startDate": today,
                    "date": today,
                    "orderDate": today,
                    "deliveryDate": today,
                    "invoiceDate": today,
                    "departureDate": today,
                    "returnDate": today,
                    "dateOfBirth": "1990-01-01",
                    "name": "Default",
                    "description": "",
                    "departmentNumber": "1",
                }
                if field in defaults and field not in body:
                    body[field] = defaults[field]
                    logger.info(f"Auto-fix: set required {field}={defaults[field]}")
                    fixed = True
                elif "." in field:
                    # Nested field like "department.id"
                    parts = field.split(".")
                    if parts[0] not in body:
                        if parts[0] == "department":
                            body["department"] = {"id": 1}
                            logger.info(f"Auto-fix: set department.id=1")
                            fixed = True

            elif fix_type == "remove_field":
                # Remove the offending field
                if field in body:
                    del body[field]
                    logger.info(f"Auto-fix: removed invalid field {field}")
                    fixed = True

            elif fix_type == "duplicate":
                # Field value already in use — append suffix
                if field in body and isinstance(body[field], str):
                    body[field] = body[field] + "-2"
                    logger.info(f"Auto-fix: appended suffix to duplicate {field}")
                    fixed = True

            elif fix_type == "needs_usertype":
                if "userType" not in body:
                    body["userType"] = "EXTENDED"
                    logger.info(f"Auto-fix: set userType=EXTENDED")
                    fixed = True

            elif fix_type == "invalid_value":
                # Try removing the invalid field
                if field in body:
                    del body[field]
                    logger.info(f"Auto-fix: removed invalid {field}")
                    fixed = True

        return fixed

    async def post_with_retry(self, path: str, body: dict, fixups: dict[str, object] | None = None) -> dict:
        """POST with retry. Uses smart auto-fixes + explicit fixups."""
        try:
            return await self.client.post(path, body)
        except ValidationError as e:
            # Try explicit fixups first
            if fixups:
                applied = False
                for field, message in e.fields.items():
                    if field in fixups and field not in body:
                        body[field] = fixups[field]
                        applied = True
                        logger.info(f"Fixup: set {field}={fixups[field]}")
                if applied:
                    logger.info(f"Retrying POST {path} after fixup")
                    return await self.client.post(path, body)

            # Fall back to auto-fixes
            fixed = self._apply_auto_fixes(body, e)
            if fixed:
                logger.info(f"Retrying POST {path} after auto-fix")
                return await self.client.post(path, body)
            raise
