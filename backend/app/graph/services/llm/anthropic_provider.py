"""Anthropic (Claude) LLM provider."""

import json
import re
from typing import Type, TypeVar

import anthropic
from pydantic import BaseModel

from app.core.config import get_settings
from app.graph.services.llm.base import BaseLLMProvider

T = TypeVar("T", bound=BaseModel)


def _extract_json(text: str) -> dict:
    """
    Extract a JSON object from an LLM response.
    Handles raw JSON, markdown ```json blocks, and bare ``` blocks.
    Raises ValueError if no valid JSON is found.
    """
    text = text.strip()

    # Attempt 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: extract from ```json ... ``` block
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Attempt 3: extract from ``` ... ``` block (any language tag)
    match = re.search(r"```[a-z]*\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Attempt 4: find largest {...} blob
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not extract valid JSON from LLM response. First 300 chars: {text[:300]}"
    )


class AnthropicProvider(BaseLLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[T],
        temperature: float = 0.2,
    ) -> T:
        enhanced_system = (
            f"{system_prompt}\n\n"
            "CRITICAL: Your entire response must be a single valid JSON object. "
            "Do not include any text, explanation, or markdown before or after the JSON. "
            "Do not wrap it in a code block."
        )
        raw = self.generate(enhanced_system, user_prompt, temperature=temperature)
        try:
            data = _extract_json(raw)
            return schema.model_validate(data)
        except Exception as exc:
            raise ValueError(
                f"Structured output parsing failed for {schema.__name__}: {exc}. "
                f"Raw response (first 400 chars): {raw[:400]}"
            ) from exc
