"""
Curated static catalogue of popular models available from the Ollama registry.

This list is used when the frontend requests downloadable models.
A static list is preferred over live scraping to avoid brittle HTTP dependencies.
Update this file periodically to reflect new popular models.
"""

from typing import Any

# Each entry mirrors the shape the frontend ModelHub card expects.
# The "category" field is derived from the same heuristics used at runtime
# by model_category.categorize_model(), kept static here to avoid startup cost.
AVAILABLE_MODELS: list[dict[str, Any]] = [
    {
        "name": "llama3.2",
        "display": "Llama 3.2 3B",
        "description": "Meta's compact Llama 3.2 — fast responses, great for edge devices.",
        "parameters": "3B",
        "size": "2.0 GB",
        "tags": ["meta", "fast", "lightweight"],
        "category": "chat",
    },
    {
        "name": "llama3.1",
        "display": "Llama 3.1 8B",
        "description": "Meta's 8B flagship — strong reasoning and instruction following.",
        "parameters": "8B",
        "size": "4.7 GB",
        "tags": ["meta", "general-purpose"],
        "category": "chat",
    },
    {
        "name": "llama3.1:70b",
        "display": "Llama 3.1 70B",
        "description": "Meta's large 70B model — near-GPT-4 quality on many benchmarks.",
        "parameters": "70B",
        "size": "40 GB",
        "tags": ["meta", "large", "high-quality"],
        "category": "chat",
    },
    {
        "name": "mistral",
        "display": "Mistral 7B",
        "description": "Mistral AI's efficient 7B model — excellent quality-to-size ratio.",
        "parameters": "7B",
        "size": "4.1 GB",
        "tags": ["mistral", "efficient"],
        "category": "chat",
    },
    {
        "name": "mixtral",
        "display": "Mixtral 8x7B",
        "description": "Mistral's mixture-of-experts model — top-tier open-source performance.",
        "parameters": "47B (MoE)",
        "size": "26 GB",
        "tags": ["mistral", "moe", "high-quality"],
        "category": "chat",
    },
    {
        "name": "gemma2",
        "display": "Gemma 2 9B",
        "description": "Google's Gemma 2 — strong at coding and instruction tasks.",
        "parameters": "9B",
        "size": "5.4 GB",
        "tags": ["google", "coding"],
        "category": "chat",
    },
    {
        "name": "gemma2:27b",
        "display": "Gemma 2 27B",
        "description": "Google's larger Gemma 2 — near-frontier quality.",
        "parameters": "27B",
        "size": "16 GB",
        "tags": ["google", "large"],
        "category": "chat",
    },
    {
        "name": "phi4",
        "display": "Phi-4 14B",
        "description": "Microsoft's Phi-4 — remarkable reasoning in a compact form.",
        "parameters": "14B",
        "size": "8.9 GB",
        "tags": ["microsoft", "reasoning"],
        "category": "reasoning",
    },
    {
        "name": "phi3.5",
        "display": "Phi-3.5 Mini",
        "description": "Microsoft's tiny powerhouse — best-in-class at 3.8B params.",
        "parameters": "3.8B",
        "size": "2.2 GB",
        "tags": ["microsoft", "fast", "lightweight"],
        "category": "chat",
    },
    {
        "name": "qwen2.5",
        "display": "Qwen 2.5 7B",
        "description": "Alibaba's Qwen 2.5 — strong multilingual and coding abilities.",
        "parameters": "7B",
        "size": "4.4 GB",
        "tags": ["alibaba", "multilingual", "coding"],
        "category": "chat",
    },
    {
        "name": "qwen2.5:72b",
        "display": "Qwen 2.5 72B",
        "description": "Alibaba's largest Qwen model — top multilingual benchmark scores.",
        "parameters": "72B",
        "size": "41 GB",
        "tags": ["alibaba", "large", "multilingual"],
        "category": "chat",
    },
    {
        "name": "deepseek-r1",
        "display": "DeepSeek R1 7B",
        "description": "DeepSeek's reasoning model — chain-of-thought with visible thinking.",
        "parameters": "7B",
        "size": "4.7 GB",
        "tags": ["deepseek", "reasoning", "chain-of-thought"],
        "category": "reasoning",
    },
    {
        "name": "deepseek-r1:70b",
        "display": "DeepSeek R1 70B",
        "description": "DeepSeek's large reasoner — GPT-o1 level on math and logic.",
        "parameters": "70B",
        "size": "42 GB",
        "tags": ["deepseek", "reasoning", "large"],
        "category": "reasoning",
    },
    {
        "name": "codellama",
        "display": "Code Llama 7B",
        "description": "Meta's code-specialised Llama — great for code generation and completion.",
        "parameters": "7B",
        "size": "3.8 GB",
        "tags": ["meta", "coding"],
        "category": "code",
    },
    {
        "name": "nomic-embed-text",
        "display": "Nomic Embed Text",
        "description": "High-quality text embeddings for RAG pipelines and semantic search.",
        "parameters": "137M",
        "size": "274 MB",
        "tags": ["embedding", "rag", "lightweight"],
        "category": "embedding",
    },
    {
        "name": "mxbai-embed-large",
        "display": "MxBai Embed Large",
        "description": "State-of-the-art embeddings — outperforms OpenAI ada-002 on MTEB.",
        "parameters": "335M",
        "size": "670 MB",
        "tags": ["embedding", "rag"],
        "category": "embedding",
    },
]
