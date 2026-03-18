import asyncio
import json
from fastapi import Request
from backend.routers.chat import _meta_agent_interceptor

class MockOllama:
    async def chat(self, model, messages):
        # Simulate LLM output chunk by chunk
        chunks = [
            "Here is the JSON you requested:\n\n",
            "```json\n",
            "{\n",
            '  "action": "recommend_install",\n',
            '  "target_model": "qwen2.5-coder:7b",\n',
            '  "reason": "Advanced coding tasks."\n',
            "}\n",
            "```\n",
            "Hope this helps!\n"
        ]
        for c in chunks:
            yield c
            await asyncio.sleep(0.01)

class MockRequest:
    async def is_disconnected(self):
        return False

async def main():
    ollama = MockOllama()
    req = MockRequest()
    valid = frozenset(["mistral:latest"])
    
    print("Testing interceptor...")
    async for event in _meta_agent_interceptor("mock", [], ollama, req, valid):
        print("EVENT:", event.strip())

if __name__ == "__main__":
    asyncio.run(main())
