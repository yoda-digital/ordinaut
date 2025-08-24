from __future__ import annotations

from typing import Any, Callable, Dict
from threading import RLock


class ToolRegistry:
    """Minimal tool registry used by extensions to register callable tools.

    Tools are registered by fully qualified name (e.g., "ext.webui.ping").
    Each tool has an optional input_schema and output_schema for validation.
    This is intentionally simple and can be extended later.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()
        self._frozen = False

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        *,
        input_schema: Dict[str, Any] | None = None,
        output_schema: Dict[str, Any] | None = None,
        description: str | None = None,
    ) -> None:
        with self._lock:
            if self._frozen:
                raise RuntimeError("ToolRegistry is frozen; registration is closed")
            if name in self._tools:
                raise ValueError(f"Tool already registered: {name}")
            self._tools[name] = {
                "func": func,
                "input_schema": input_schema or {},
                "output_schema": output_schema or {},
                "description": description or "",
            }

    def get(self, name: str) -> Dict[str, Any]:
        with self._lock:
            return self._tools[name]

    def list(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._tools)

    def freeze(self) -> None:
        with self._lock:
            self._frozen = True


class ToolRegistryView:
    """Read-only view for listing and retrieving tools."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def list(self) -> Dict[str, Dict[str, Any]]:
        return self._registry.list()

    def get(self, name: str) -> Dict[str, Any]:
        return self._registry.get(name)


class NamespacedToolRegistrar:
    """Write-limited wrapper that enforces a namespace prefix per plugin.

    Only allows registering names that start with the given prefix.
    """

    def __init__(self, registry: ToolRegistry, prefix: str) -> None:
        self._registry = registry
        self._prefix = prefix

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        *,
        input_schema: Dict[str, Any] | None = None,
        output_schema: Dict[str, Any] | None = None,
        description: str | None = None,
    ) -> None:
        if not name.startswith(self._prefix):
            raise ValueError(f"Tool name must start with '{self._prefix}'")
        self._registry.register(
            name,
            func,
            input_schema=input_schema,
            output_schema=output_schema,
            description=description,
        )
