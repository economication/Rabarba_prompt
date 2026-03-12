"""OpenAI (GPT) LLM provider."""

import json
from typing import Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import get_settings
from app.graph.services.llm.base import BaseLLMProvider

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(BaseLLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[T],
        temperature: float = 0.1,
    ) -> T:
        # OpenAI JSON mode guarantees the response is valid JSON
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        try:
            data = json.loads(raw)
            return schema.model_validate(data)
        except Exception as exc:
            raise ValueError(
                f"Structured output parsing failed for {schema.__name__}: {exc}. "
                f"Raw response (first 400 chars): {raw[:400]}"
            ) from exc
