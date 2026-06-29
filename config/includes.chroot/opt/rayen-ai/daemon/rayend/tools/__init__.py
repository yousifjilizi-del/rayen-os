"""Tool implementations for Rayen AI.

Each tool is a plain Python function that takes keyword arguments and returns
a JSON-serialisable result (usually a dict). Tools are registered with an
OpenAI-style JSON schema so any provider can call them.
"""

from .registry import REGISTRY, tool_schemas, execute_tool  # noqa: F401
