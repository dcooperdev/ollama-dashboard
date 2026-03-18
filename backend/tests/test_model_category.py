"""
Unit tests for model_category.py — categorize_model() function.

Covers all heuristic paths:
  - name-based embedding / code / vision / reasoning signals
  - family-based embedding detection
  - tag-based embedding / code / vision / reasoning detection
  - default fallback to "chat"
"""

import pytest
from model_category import categorize_model


class TestCategorizeModel:
    """Tests for categorize_model()."""

    # ---- Embedding ----

    def test_embedding_from_name(self):
        """Model name containing 'embed' must return 'embedding'."""
        assert categorize_model("nomic-embed-text:latest") == "embedding"

    def test_embedding_bert_name(self):
        """Model name containing 'bert' must return 'embedding'."""
        assert categorize_model("bert-base:latest") == "embedding"

    def test_embedding_from_family(self):
        """Family string containing a known embedding signal must return 'embedding' (line 78)."""
        assert categorize_model("some-model:latest", family="bert") == "embedding"

    def test_embedding_from_tag_embedding(self):
        """'embedding' tag must trigger embedding category (line 80)."""
        assert categorize_model("mysterious-model:latest", family=None, tags=["embedding"]) == "embedding"

    def test_embedding_from_tag_rag(self):
        """'rag' tag must trigger embedding category (line 80)."""
        assert categorize_model("another-model:latest", family=None, tags=["rag"]) == "embedding"

    # ---- Code ----

    def test_code_from_name(self):
        """Model name containing 'code' must return 'code'."""
        assert categorize_model("deepseek-coder:latest") == "code"

    def test_code_from_tag_coding(self):
        """'coding' tag must trigger code category (line 86)."""
        assert categorize_model("general-model:latest", family=None, tags=["coding"]) == "code"

    def test_code_from_tag_code(self):
        """'code' tag must trigger code category (line 86)."""
        assert categorize_model("general-model:latest", family=None, tags=["code"]) == "code"

    # ---- Vision ----

    def test_vision_from_name(self):
        """Model name containing 'llava' must return 'vision'."""
        assert categorize_model("llava:latest") == "vision"

    def test_vision_from_tag_vision(self):
        """'vision' tag must trigger vision category (line 92)."""
        assert categorize_model("base-model:latest", family=None, tags=["vision"]) == "vision"

    def test_vision_from_tag_multimodal(self):
        """'multimodal' tag must trigger vision category (line 92)."""
        assert categorize_model("base-model:latest", family=None, tags=["multimodal"]) == "vision"

    # ---- Reasoning ----

    def test_reasoning_from_name_r1(self):
        """Model name containing '-r1' must return 'reasoning'."""
        assert categorize_model("deepseek-r1:latest") == "reasoning"

    def test_reasoning_from_name_deepseek_r(self):
        """Model name containing 'deepseek-r' must return 'reasoning'."""
        assert categorize_model("deepseek-r:latest") == "reasoning"

    def test_reasoning_from_tag_reasoning(self):
        """'reasoning' tag must trigger reasoning category (line 99)."""
        assert categorize_model("llama3:latest", family=None, tags=["reasoning"]) == "reasoning"

    def test_reasoning_from_tag_chain_of_thought(self):
        """'chain-of-thought' tag must trigger reasoning category (line 99)."""
        assert categorize_model("llama3:latest", family=None, tags=["chain-of-thought"]) == "reasoning"

    # ---- Default chat fallback ----

    def test_default_fallback_to_chat(self):
        """A plain model name with no matching signals must return 'chat'."""
        assert categorize_model("llama3:latest") == "chat"

    def test_empty_name_returns_chat(self):
        """An empty name with no family or tags must return 'chat'."""
        assert categorize_model("") == "chat"

    def test_none_family_is_handled(self):
        """None family must not raise and must fall through to tag checks."""
        assert categorize_model("llama3:latest", family=None) == "chat"

    def test_empty_tags_is_handled(self):
        """Empty tags list must not raise and must fall through to default."""
        assert categorize_model("llama3:latest", tags=[]) == "chat"
