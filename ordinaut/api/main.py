from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Depends, Header, HTTPException

from ordinaut.engine.registry import ToolRegistry
from ordinaut.plugins import ExtensionLoader
import time
from starlette.requests import Request
from starlette.responses import Response


def create_app() -> FastAPI:
    app = FastAPI(title="Ordinaut", version="0.1.0")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Initialize shared registries and context offered to extensions
    tool_registry = ToolRegistry()
    context: dict[str, Any] = {}

    # Load extensions and mount routers
    loader = ExtensionLoader(app)
    infos = loader.load_all(tool_registry=tool_registry, context=context)
    # Freeze tool registry post-load for stability
    tool_registry.freeze()

    @app.middleware("http")
    async def ext_metrics_middleware(request: Request, call_next):
        path = request.url.path
        plugin_id = None
        if path.startswith("/ext/"):
            parts = path.split("/", 3)
            if len(parts) >= 3:
                plugin_id = parts[2]
                # Lazy-load plugin before routing
                if plugin_id in loader.specs and plugin_id not in loader.loaded:
                    loader._ensure_loaded(plugin_id, tool_registry=tool_registry, context=context)
                    from starlette.responses import RedirectResponse
                    return RedirectResponse(url=str(request.url), status_code=307)
        start = time.time()
        ok = True
        try:
            response: Response = await call_next(request)
            return response
        except Exception:
            ok = False
            raise
        finally:
            if plugin_id:
                loader.record_request(plugin_id, (time.time() - start) * 1000.0, ok)

    # Expose simple discovery endpoint
    @app.get("/extensions")
    def extensions():
        out = []
        for pid, spec in loader.specs.items():
            entry = {
                "id": pid,
                "root": str(spec.root),
                "module": spec.module,
                "enabled": spec.enabled,
                "eager": spec.eager,
                "source": getattr(spec, "source", "unknown"),
                "grants": [c.name for c in (spec.grants or set())],
                "status": loader.status.get(pid, {}),
                "metrics": loader.metrics.get(pid, {}),
            }
            out.append(entry)
        return out

    @app.get("/extensions/{plugin_id}/events/health")
    async def extension_events_health(plugin_id: str, namespace: str | None = None):
        em = getattr(loader, "_events_manager", None)
        if not em:
            raise HTTPException(status_code=404, detail="events manager not enabled")
        try:
            res = await em.health_for_plugin(plugin_id, namespace=namespace)
        except Exception as ex:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(ex))
        return res

    # Provide simple tools listing for visibility
    @app.get("/tools")
    def tools():
        return {k: {"description": v.get("description", "")} for k, v in tool_registry.list().items()}

    return app


app = create_app()
