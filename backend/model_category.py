"""
Model capability categorization utility.

Single responsibility: given a model's name, Ollama family string, and tags,
return the most appropriate ModelCategory label.

Categories
----------
- "embedding"  : Vector embedding models (not suitable for chat/generation)
- "code"       : Code-specialised models
- "vision"     : Multimodal vision-language models
- "reasoning"  : Chain-of-thought / reasoning-focused models
- "chat"       : General-purpose conversational models (default fallback)
"""

from typing import Literal

# Supported capability categories.
ModelCategory = Literal["embedding", "code", "vision", "reasoning", "chat"]

# ---------------------------------------------------------------------------
# Internal signal sets — checked against lowercase model name / family
# ---------------------------------------------------------------------------

_EMBEDDING_SIGNALS: frozenset[str] = frozenset(
    ["embed", "nomic", "bert", "e5", "bge", "minilm", "mxbai"]
)

_CODE_SIGNALS: frozenset[str] = frozenset(
    ["code", "coder", "starcoder", "codestral", "devstral", "qwen-coder"]
)

_VISION_SIGNALS: frozenset[str] = frozenset(
    ["vision", "llava", "bakllava", "moondream", "minicpm-v", "cogvlm"]
)

_REASONING_SIGNALS: frozenset[str] = frozenset(
    ["deepseek-r", "-r1", ":r1"]
)


def categorize_model(
    name: str,
    family: str | None = None,
    tags: list[str] | None = None,
) -> ModelCategory:
    """
    Derive the capability category of an Ollama model.

    The function applies a priority-ordered set of heuristics based on the
    model's name, Ollama family string, and metadata tags:

        1. embedding  — contains embedding-specialist signals
        2. code       — contains code-specialist signals
        3. vision     — contains multimodal / vision signals
        4. reasoning  — contains chain-of-thought signals
        5. chat       — default fallback for general-purpose LLMs

    Args:
        name:   Full model tag, e.g. ``"nomic-embed-text:latest"`` or
                ``"llama3.2:3b"``.
        family: Ollama ``details.family`` string, e.g. ``"bert"``, or ``None``
                if the field is absent.
        tags:   List of free-form metadata tags from the model catalogue, or
                ``None`` / ``[]`` when unavailable.

    Returns:
        A ``ModelCategory`` literal string.
    """
    name_lower = (name or "").lower()
    family_lower = (family or "").lower()
    tags_lower = {t.lower() for t in (tags or [])}

    # --- 1. Embedding ---
    if _any_signal_in(name_lower, _EMBEDDING_SIGNALS):
        return "embedding"
    if _any_signal_in(family_lower, _EMBEDDING_SIGNALS):
        return "embedding"
    if "embedding" in tags_lower or "rag" in tags_lower:
        return "embedding"

    # --- 2. Code ---
    if _any_signal_in(name_lower, _CODE_SIGNALS):
        return "code"
    if "coding" in tags_lower or "code" in tags_lower:
        return "code"

    # --- 3. Vision ---
    if _any_signal_in(name_lower, _VISION_SIGNALS):
        return "vision"
    if "vision" in tags_lower or "multimodal" in tags_lower:
        return "vision"

    # --- 4. Reasoning ---
    for signal in _REASONING_SIGNALS:
        if signal in name_lower:
            return "reasoning"
    if "reasoning" in tags_lower or "chain-of-thought" in tags_lower:
        return "reasoning"

    # --- 5. Default ---
    return "chat"


def _any_signal_in(text: str, signals: frozenset[str]) -> bool:
    """
    Return True if any signal string is a substring of *text*.

    Args:
        text:    Lowercased string to search within.
        signals: Set of lowercase signal substrings.

    Returns:
        ``True`` if at least one signal is found; ``False`` otherwise.
    """
    return any(signal in text for signal in signals)
