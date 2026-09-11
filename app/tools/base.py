"""Tool base class and result type shared by all tools."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] = {}

    @classmethod
    def ok(cls, message: str, **data: Any) -> "ToolResult":
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, **data: Any) -> "ToolResult":
        return cls(success=False, message=message, data=data)


class Tool(ABC):
    """A single capability the LLM may request. Never called directly by the LLM."""

    #: unique registry key, e.g. "open_app"
    name: str = ""
    #: human description fed to the LLM
    description: str = ""
    #: JSON-schema dict for the arguments accepted from the LLM
    schema: dict[str, Any] = {}
    #: safe | confirmation
    category: str = "safe"
    #: if True and mode == production-without-confirmation, executor refuses
    destructive: bool = False

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult: ...

    def validate(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Validate arguments against self.schema using a dynamically built model."""
        if not self.schema:
            return {}
        pydantic_type = self.schema.get("type")
        if pydantic_type != "object":
            raise ValueError("Tool schema must be an object schema")
        import pydantic

        props: dict[str, Any] = self.schema.get("properties", {})
        required: list[str] = self.schema.get("required", [])
        # normalise "$ref"-free simple schemas into pydantic fields
        fields = {
            k: (
                _pydantic_type(v.get("type", "str")),
                pydantic.Field(..., description=v.get("description", "")) if k in required
                else pydantic.Field(None, description=v.get("description", "")),
            )
            for k, v in props.items()
        }
        Model = pydantic.create_model(f"{self.name}_Args", **fields)
        parsed = Model.model_validate(kwargs)
        return parsed.model_dump(exclude_none=True)


def _pydantic_type(t: str) -> Any:
    return {"string": str, "str": str, "integer": int, "number": float, "boolean": bool}.get(
        t, str
    )
