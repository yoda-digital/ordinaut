from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Optional

from fastapi import APIRouter, FastAPI


class Capability(Enum):
    ROUTES = auto()
    TOOLS = auto()
    EVENTS_PUB = auto()
    EVENTS_SUB = auto()
    STATIC = auto()
    BACKGROUND_TASKS = auto()


@dataclass(frozen=True)
class ExtensionInfo:
    id: str
    name: str
    version: str
    description: str = ""


class Extension:
    def info(self) -> ExtensionInfo:
        raise NotImplementedError

    def requested_capabilities(self) -> set[Capability]:
        return set()

    def setup(
        self,
        *,
        app: FastAPI,
        mount_path: str,
        tool_registry: Any,
        grants: set[Capability],
        context: dict[str, Any] | None = None,
    ) -> Optional[APIRouter]:
        return None

    async def on_startup(self, app: FastAPI) -> None:
        ...

    async def on_shutdown(self, app: FastAPI) -> None:
        ...

