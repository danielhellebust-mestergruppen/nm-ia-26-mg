"""
Accounting Expert Test Generator.
Uses Gemini to generate realistic accounting task prompts in all 7 languages,
then tests our agent's classification and extraction against them.

Usage:
    python3 tests/generate_test_prompts.py
    python3 tests/generate_test_prompts.py --run  # also execute handlers against sandbox
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from google import genai
from google.genai import types
from config import GOOGLE_API_KEY
from llm.client import classify_and_extract

logging.basicConfig(level="INFO", format="%(asctime)s %(name)s: %(message)s")
logger = logging.getLogger("test_gen")

GENERATOR_PROMPT = """You are a Norwegian accounting expert who creates test prompts for an AI accounting agent.

Generate realistic accounting task prompts that a Norwegian business would encounter in Tripletex.
Each prompt should be in one of these languages: nb (Norwegian Bokmål), nn (Nynorsk), en (English), de (German), es (Spanish), pt (Portuguese), fr (French).

For each prompt, provide:
- The prompt text (realistic, with specific names, numbers, amounts)
- The expected task_type
- The expected extracted entities

Generate varied prompts covering:
1. Create employee with admin role
2. Create customer with org number
3. Create supplier (not customer)
4. Create product with price
5. Create department
6. Create project linked to customer
7. Create invoice with specific amount
8. Register payment on invoice
9. Create credit note
10. Create travel expense
11. Delete travel expense
12. Update employee contact info
13. Invoice with multiple line items
14. Create customer with full address
15. Project with specific start/end dates

Use realistic Norwegian company names, person names, org numbers (9 digits), and amounts.
Include special characters (æ, ø, å, ü, ñ, ã, é) where appropriate.

Return a JSON array of objects, each with:
- "language": language code
- "prompt": the task prompt text
- "expected_task_type": the task type string
- "expected_entities": dict of expected extracted fields

Generate exactly 20 test prompts covering different languages and task types.
"""


async def generate_prompts() -> list[dict]:
    client = genai.Client(api_key=GOOGLE_API_KEY)

    logger.info("Generating test prompts via Gemini...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=GENERATOR_PROMPT,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.8,
        ),
    )

    prompts = json.loads(response.text)
    logger.info(f"Generated {len(prompts)} test prompts")
    return prompts


async def test_classification(prompts: list[dict]) -> list[dict]:
    results = []
    for i, p in enumerate(prompts):
        logger.info(f"Testing {i+1}/{len(prompts)}: [{p['language']}] {p['prompt'][:60]}...")

        try:
            plan = await classify_and_extract(p["prompt"])
            match_type = plan.task_type.value == p["expected_task_type"]

            # Check key entity matches
            entity_matches = {}
            for key, expected_val in p.get("expected_entities", {}).items():
                actual = plan.entities.get(key)
                entity_matches[key] = {
                    "expected": expected_val,
                    "actual": actual,
                    "match": str(actual).lower() == str(expected_val).lower() if actual else False,
                }

            matched_count = sum(1 for v in entity_matches.values() if v["match"])
            total_fields = len(entity_matches)

            result = {
                "prompt": p["prompt"],
                "language": p["language"],
                "expected_type": p["expected_task_type"],
                "actual_type": plan.task_type.value,
                "type_match": match_type,
                "entity_matches": entity_matches,
                "entity_score": f"{matched_count}/{total_fields}",
                "all_extracted": plan.entities,
            }
            results.append(result)

            icon = "✓" if match_type else "✗"
            logger.info(f"  {icon} type: {plan.task_type.value} (expected: {p['expected_task_type']}) | entities: {matched_count}/{total_fields}")

        except Exception as e:
            results.append({
                "prompt": p["prompt"],
                "language": p["language"],
                "error": str(e),
            })
            logger.error(f"  ✗ Error: {e}")

    return results


async def main():
    run_handlers = "--run" in sys.argv

    # Generate prompts
    prompts = await generate_prompts()

    # Save generated prompts
    out_dir = Path(__file__).parent.parent / "logs"
    prompts_file = out_dir / "generated-test-prompts.json"
    with open(prompts_file, "w") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved prompts to {prompts_file}")

    # Test classification
    results = await test_classification(prompts)

    # Save results
    results_file = out_dir / "classification-test-results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Summary
    type_matches = sum(1 for r in results if r.get("type_match"))
    total = len(results)
    logger.info(f"\n{'='*60}")
    logger.info(f"CLASSIFICATION ACCURACY: {type_matches}/{total} ({100*type_matches//total}%)")

    # Per-language breakdown
    by_lang = {}
    for r in results:
        lang = r.get("language", "?")
        by_lang.setdefault(lang, {"total": 0, "correct": 0})
        by_lang[lang]["total"] += 1
        if r.get("type_match"):
            by_lang[lang]["correct"] += 1

    for lang, stats in sorted(by_lang.items()):
        logger.info(f"  {lang}: {stats['correct']}/{stats['total']}")

    # Failures
    failures = [r for r in results if not r.get("type_match") and "error" not in r]
    if failures:
        logger.info(f"\nMISCLASSIFICATIONS:")
        for r in failures:
            logger.info(f"  [{r['language']}] expected={r['expected_type']}, got={r['actual_type']}")
            logger.info(f"    Prompt: {r['prompt'][:100]}")


if __name__ == "__main__":
    asyncio.run(main())
