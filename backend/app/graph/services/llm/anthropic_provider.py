"""Anthropic (Claude) LLM provider."""

import json
import re
import time
from typing import Type, TypeVar

import anthropic
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.cost_config import calculate_cost
from app.graph.services.llm.base import BaseLLMProvider, GenerateResult

M = TypeVar("M", bound=BaseModel)


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
        self.model = settings.anthropic_model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> GenerateResult[str]:
        t0 = time.monotonic()
        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        return GenerateResult(
            data=response.content[0].text,
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
        temperature: float = 0.2,
    ) -> GenerateResult[M]:
        enhanced_system = (
            f"{system_prompt}\n\n"
            "CRITICAL: Your entire response must be a single valid JSON object. "
            "Do not include any text, explanation, or markdown before or after the JSON. "
            "Do not wrap it in a code block."
        )
        t0 = time.monotonic()
        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=temperature,
            system=enhanced_system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        raw = response.content[0].text
        try:
            data = _extract_json(raw)
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
