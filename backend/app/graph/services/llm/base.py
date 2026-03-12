"""Abstract base class and shared types for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)


@dataclass
class GenerateResult(Generic[T]):
    """
    Wraps an LLM response with token usage and cost metadata.
    data: str for generate(), Pydantic model for generate_structured().
    duration_ms is measured inside the provider — nodes must not re-measure it.
    """
    data: T
    input_tokens: int
    output_tokens: int
    duration_ms: int
    cost_usd: float


class BaseLLMProvider(ABC):
    """
    Abstract interface for all LLM providers.
    Concrete subclasses must set self.model (str) as an instance attribute.
    """

    model: str  # set by each concrete provider in __init__

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> "GenerateResult[str]":
        """Generate free-text response. Returns GenerateResult[str]."""
        ...

    @abstractmethod
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[M],
        temperature: float = 0.2,
    ) -> "GenerateResult[M]":
        """
        Generate a response and parse it into the given Pydantic schema.
        Returns GenerateResult[M] where result.data is the parsed model instance.
        Raises ValueError if the output cannot be parsed or validated.
        """
        ...
