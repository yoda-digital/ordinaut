from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, FastAPI
from fastapi.responses import Response
from prometheus_client import (
    Counter,
    Histogram,
    CONTENT_TYPE_LATEST,
    generate_latest,
)

from ordinaut.plugins.base import Capability, Extension, ExtensionInfo


class ObservabilityExtension(Extension):
    def __init__(self) -> None:
        # Core HTTP metrics
        self.http_requests_total = Counter(
            'ord_http_requests_total',
            'Total HTTP requests',
            ['method', 'path', 'status'],
        )
        self.http_request_duration = Histogram(
            'ord_http_request_duration_seconds',
            'HTTP request duration in seconds',
            ['method', 'path'],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')),
        )
        # Per-plugin metrics
        self.plugin_requests_total = Counter(
            'ord_plugin_http_requests_total',
            'Total HTTP requests per plugin',
            ['plugin_id', 'status'],
        )
        self.plugin_request_duration = Histogram(
            'ord_plugin_http_request_duration_seconds',
            'HTTP request duration per plugin',
            ['plugin_id'],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')),
        )

    def info(self) -> ExtensionInfo:
        return ExtensionInfo(
            id="observability",
            name="Observability",
            version="0.1.0",
            description="Prometheus metrics and HTTP request instrumentation",
        )

    def requested_capabilities(self) -> set[Capability]:
        return {Capability.ROUTES}

    def setup(
        self,
        *,
        app: FastAPI,
        mount_path: str,
        tool_registry: Any,
        grants: set[Capability],
        context: dict[str, Any] | None = None,
    ) -> Optional[APIRouter]:
        # Register middleware for HTTP and plugin metrics
        @app.middleware("http")
        async def metrics_middleware(request, call_next):
            method = request.method
            path = request.url.path
            plugin_id = None
            if path.startswith('/ext/'):
                parts = path.split('/', 3)
                if len(parts) >= 3:
                    plugin_id = parts[2]
            start = time.time()
            status_code = 500
            try:
                response = await call_next(request)
                status_code = getattr(response, 'status_code', 200)
                return response
            finally:
                dur = time.time() - start
                # General
                self.http_requests_total.labels(method=method, path=path, status=str(status_code)).inc()
                self.http_request_duration.labels(method=method, path=path).observe(dur)
                # Plugin
                if plugin_id:
                    self.plugin_requests_total.labels(plugin_id=plugin_id, status=str(status_code)).inc()
                    self.plugin_request_duration.labels(plugin_id=plugin_id).observe(dur)

        router = APIRouter()

        @router.get("/metrics")
        async def metrics():
            data = generate_latest()
            return Response(content=data, media_type=CONTENT_TYPE_LATEST)

        # Also expose at root for compatibility
        app.add_api_route("/metrics", metrics, methods=["GET"])

        return router


def get_extension() -> Extension:
    return ObservabilityExtension()

