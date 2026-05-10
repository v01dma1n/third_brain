import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACTS_DIR = os.path.join(BASE_DIR, "..", "facts")


def load_facts(
    base_path: str = None,
    inferred_path: str = None,
) -> str:
    """Load and concatenate both fact files for system prompt injection.
    Base facts take precedence — always loaded first."""
    if base_path is None:
        base_path = os.path.join(FACTS_DIR, "base_facts.md")
    if inferred_path is None:
        inferred_path = os.path.join(FACTS_DIR, "inferred_facts.md")

    parts = []
    for path in [base_path, inferred_path]:
        try:
            with open(path, "r") as f:
                content = f.read().strip()
            if content:
                parts.append(content)
        except FileNotFoundError:
            pass

    return "\n\n".join(parts)
