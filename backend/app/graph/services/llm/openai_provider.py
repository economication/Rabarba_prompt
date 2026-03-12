"""OpenAI (GPT) LLM provider."""

import json
import time
from typing import Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.cost_config import calculate_cost
from app.graph.services.llm.base import BaseLLMProvider, GenerateResult

M = TypeVar("M", bound=BaseModel)


class OpenAIProvider(BaseLLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> GenerateResult[str]:
        t0 = time.monotonic()
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        return GenerateResult(
            data=response.choices[0].message.content or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            cost_usd=calculate_cost(self.model, input_tokens, output_tokens),
        )

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[M],
        temperature: float = 0.1,
    ) -> GenerateResult[M]:
        t0 = time.monotonic()
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        raw = response.choices[0].message.content or ""
        try:
            data = json.loads(raw)
            parsed = schema.model_validate(data)
        except Exception as exc:
            raise ValueError(
                f"Structured output parsing failed for {schema.__name__}: {exc}. "
                f"Raw response (first 400 chars): {raw[:400]}"
            ) from exc
        return GenerateResult(
            data=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            cost_usd=calculate_cost(self.model, input_tokens, output_tokens),
        )
