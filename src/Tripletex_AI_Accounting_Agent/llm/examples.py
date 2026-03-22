"""Build few-shot examples from successful submission logs."""
import json
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "logs"
SUBMISSIONS_FILE = LOGS_DIR / "submissions.json"
# Manual examples for tasks we haven't seen yet or want to override
MANUAL_EXAMPLES: list[dict] = []


def load_examples() -> list[dict]:
    """Load successful submissions as few-shot examples.
    Returns list of {prompt, task_type, entities} dicts."""
    examples = list(MANUAL_EXAMPLES)
    seen_types = {e.get("task_type") for e in examples}

    if SUBMISSIONS_FILE.exists():
        subs = json.loads(SUBMISSIONS_FILE.read_text())
        for sub in subs:
            if sub.get("status") != "ok":
                continue
            task_type = sub.get("task_type", "")
            if not task_type or task_type in seen_types:
                continue  # One example per task type
            examples.append({
                "prompt": sub.get("prompt", "")[:300],
                "task_type": task_type.lower(),
                "entities": sub.get("entities", {}),
            })
            seen_types.add(task_type)

    return examples


def format_examples_for_prompt() -> str:
    """Format examples as text to append to the system prompt."""
    examples = load_examples()
    if not examples:
        return ""

    lines = ["\n## Real Examples (from previous successful submissions)\n"]
    for ex in examples:
        lines.append(f"Prompt: {ex['prompt']}")
        output = {"task_type": ex["task_type"], "entities": ex["entities"]}
        lines.append(f"Output: {json.dumps(output, ensure_ascii=False)}\n")

    return "\n".join(lines)
