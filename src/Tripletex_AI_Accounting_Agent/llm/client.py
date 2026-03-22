from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_MODEL_VISION
from llm.schemas import TaskPlan, TaskType
from llm.prompts import SYSTEM_PROMPT
from llm.accounting_knowledge import ACCOUNTING_KNOWLEDGE
from llm.api_reference import API_REFERENCE
from llm.examples import format_examples_for_prompt

logger = logging.getLogger("llm")

_client = None
_system_prompt = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


async def classify_and_extract(
    context: str, image_parts: list[types.Part] | None = None
) -> TaskPlan:
    client = get_client()

    contents: list = [context]
    if image_parts:
        contents.extend(image_parts)

    # Build prompt with few-shot examples (cached after first call)
    global _system_prompt
    if _system_prompt is None:
        examples = format_examples_for_prompt()
        _system_prompt = SYSTEM_PROMPT + ACCOUNTING_KNOWLEDGE + API_REFERENCE + examples
        logger.info(f"System prompt built with {examples.count('Prompt:')} few-shot examples")

    model = GEMINI_MODEL_VISION if image_parts else GEMINI_MODEL
    logger.info(f"Calling Gemini ({model}) with {len(contents)} content parts")

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_system_prompt,
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )

    raw = response.text
    logger.info(f"LLM response: {raw}")

    parsed = json.loads(raw)
    task_type_str = parsed.get("task_type", "unknown")

    try:
        task_type = TaskType(task_type_str)
    except ValueError:
        logger.warning(f"Unknown task type from LLM: {task_type_str}")
        task_type = TaskType.UNKNOWN

    entities = parsed.get("entities", {})

    # If LLM returns a list of entities (multi-item task), wrap in a dict
    if isinstance(entities, list):
        entities = {"items": entities}

    return TaskPlan(
        task_type=task_type,
        entities=entities,
    )
