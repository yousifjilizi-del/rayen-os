"""Shared provider types.

The brain works with a normalised, provider-agnostic message format:

  {"role": "system"|"user"|"assistant"|"tool", "content": str,
   "tool_calls": [ToolCall...]?,        # assistant only
   "tool_call_id": str?, "name": str?}  # tool messages

Each provider converts this to/from its own wire format.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ProviderError(RuntimeError):
    """Raised when a provider call fails (network, auth, etc.)."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)
