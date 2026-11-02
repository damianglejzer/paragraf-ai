import json
from pathlib import Path
from typing import Any

import httpx
import openai
from pydantic import BaseModel

from paragraf.providers.cache import DiskCache
from paragraf.providers.openai_llm import OpenAILLM


class Verdict(BaseModel):
    supports: bool


def fake_openai(llm: OpenAILLM, seen: list[dict[str, Any]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"supports": true}'},
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
            },
        )

    llm._client = openai.OpenAI(
        api_key="k", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_structured_output_with_reasoning_and_cache(tmp_path: Path) -> None:
    llm = OpenAILLM("k", "gpt-test", DiskCache(tmp_path / "c.sqlite"), reasoning_effort="none")
    seen: list[dict[str, Any]] = []
    fake_openai(llm, seen)

    first = llm.complete("sys", "prompt", json_schema=Verdict)
    second = llm.complete("sys", "prompt", json_schema=Verdict)

    assert Verdict.model_validate_json(first.text).supports
    assert first.usage.input_tokens == 11 and not first.cached
    assert second.cached and len(seen) == 1  # second call served from the disk cache
    body = seen[0]
    assert body["reasoning_effort"] == "none"
    assert "temperature" not in body  # reasoning models reject a custom temperature
    assert body["response_format"]["json_schema"]["name"] == "Verdict"


def test_temperature_is_sent_without_reasoning() -> None:
    llm = OpenAILLM("k", "gpt-test")
    seen: list[dict[str, Any]] = []
    fake_openai(llm, seen)
    llm.complete("sys", "prompt", temperature=0.7)
    assert seen[0]["temperature"] == 0.7
    assert "reasoning_effort" not in seen[0]
