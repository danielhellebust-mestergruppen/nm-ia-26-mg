"""Shared utility for building order lines with product creation."""
import logging

logger = logging.getLogger("handler.order_utils")


async def build_order_lines(client, entities: dict) -> list[dict]:
    """Build order lines from extracted entities, creating products if they have numbers."""
    order_lines = []

    for line in entities.get("orderLines", []):
        order_line = {
            "description": line.get("description", line.get("product", "")),
            "count": line.get("quantity", 1),
            "unitPriceExcludingVatCurrency": line.get("unitPrice", 0),
        }
        # Set vatType on order line if specified (ensures correct VAT even with pre-existing products)
        if line.get("vatTypeId"):
            order_line["vatType"] = {"id": line["vatTypeId"]}

        # Find product by number, or create if not found
        if line.get("number"):
            try:
                result = await client.get("/product", params={
                    "number": str(line["number"]),
                    "fields": "id,name,number",
                    "count": 1,
                })
                products = result.get("values", [])
                if products:
                    order_line["product"] = {"id": products[0]["id"]}
                    logger.info(f"Found product id={products[0]['id']} number={line['number']}")
                else:
                    # Create product
                    prod_body = {
                        "name": line.get("product", line.get("description", "")),
                        "number": str(line["number"]),
                        "priceExcludingVatCurrency": line.get("unitPrice", 0),
                    }
                    if line.get("vatTypeId"):
                        prod_body["vatType"] = {"id": line["vatTypeId"]}
                    prod_result = await client.post("/product", prod_body)
                    order_line["product"] = {"id": prod_result["value"]["id"]}
                    logger.info(f"Created product number={line['number']}")
            except Exception as ex:
                logger.warning(f"Product lookup/create failed: {ex}")
        elif line.get("product"):
            # No product number — search by name (GETs are free), but DON'T create
            # Order lines work fine without a product reference, saving a write call
            prod_name = line.get("product") or line.get("description") or ""
            if prod_name:
                try:
                    result = await client.get("/product", params={
                        "name": prod_name,
                        "fields": "id,name,number",
                        "count": 5,
                    })
                    for p in result.get("values", []):
                        if prod_name.lower() in (p.get("name") or "").lower():
                            order_line["product"] = {"id": p["id"]}
                            logger.info(f"Found product by name '{prod_name}' id={p['id']}")
                            break
                except Exception:
                    pass
            # If not found, skip product — order line works with just description

        order_lines.append(order_line)

    # Fallback: single line from top-level fields
    if not order_lines:
        desc = entities.get("description") or entities.get("productName") or entities.get("comment") or "Service"
        amount = entities.get("unitPrice", entities.get("amount", entities.get("totalAmount", 0)))
        if amount:
            order_lines.append({
                "description": desc,
                "count": entities.get("quantity", 1),
                "unitPriceExcludingVatCurrency": amount,
            })

    return order_lines
