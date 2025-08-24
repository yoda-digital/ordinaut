from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, HTMLResponse

from ordinaut.plugins.base import Capability, Extension, ExtensionInfo


class WebUIExtension(Extension):
    def info(self) -> ExtensionInfo:
        return ExtensionInfo(
            id="webui",
            name="Built-in Web UI",
            version="0.1.0",
            description="Simple static web UI served as an extension",
        )

    def requested_capabilities(self) -> set[Capability]:
        return {Capability.ROUTES, Capability.STATIC}

    def setup(
        self,
        *,
        app: FastAPI,
        mount_path: str,
        tool_registry: Any,
        grants: set[Capability],
        context: dict[str, Any] | None = None,
    ) -> Optional[APIRouter]:
        router = APIRouter()
        static_dir = Path(__file__).parent / "static"
        index = static_dir / "index.html"

        @router.get("/")
        def index_page():
            if index.exists():
                return FileResponse(index)
            return HTMLResponse("<h1>Ordinaut Web UI</h1><p>Coming soon.</p>")

        return router


def get_extension() -> Extension:
    return WebUIExtension()
