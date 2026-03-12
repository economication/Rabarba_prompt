"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseLLMProvider(ABC):
    """
    Abstract interface for all LLM providers.
    Swap providers by implementing this base class and updating config.
    """

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        """Generate free-text response."""
        ...

    @abstractmethod
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[T],
        temperature: float = 0.2,
    ) -> T:
        """
        Generate a response and parse it into the given Pydantic schema.
        Raises ValueError if the output cannot be parsed or validated.
        Per rule 17: never silently coerce malformed output.
        """
        ...
