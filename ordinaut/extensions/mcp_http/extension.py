from __future__ import annotations

from typing import Any, Optional, AsyncIterator

from fastapi import APIRouter, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio

from ordinaut.plugins.base import Capability, Extension, ExtensionInfo


class MCPHttpExtension(Extension):
    def info(self) -> ExtensionInfo:
        return ExtensionInfo(
            id="mcp_http",
            name="MCP over HTTP",
            version="0.2.0",
            description="MCP-like HTTP endpoint (handshake + tools + SSE stream)",
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
        router = APIRouter(tags=["mcp"])

        # Minimal shape to hint intended contract for a remote MCP-style exchange.
        # This is NOT a full MCP implementation; it is a pragmatic placeholder
        # extension surface to iterate on (e.g., handshake, list_tools, call_tool).

        @router.get("/meta")
        def meta():
            return {
                "server": "ordinaut-mcp-http",
                "version": "0.2.0",
                "capabilities": ["handshake", "list_tools", "invoke", "schema", "sse"],
            }

        @router.post("/handshake")
        def handshake(client: dict[str, Any]):
            return {
                "server": {
                    "name": "ordinaut-mcp-http",
                    "version": "0.2.0",
                    "protocol": "mcp-http-lite/0.1",
                },
                "client": client or {},
                "endpoints": {
                    "tools": f"{mount_path}/tools",
                    "invoke": f"{mount_path}/tools/{{name}}",
                    "schema": f"{mount_path}/schema",
                    "stream": f"{mount_path}/stream",
                },
            }

        def _require_scope(x_scopes: str | None, needed: str):
            import os
            require = os.environ.get("ORDINAUT_REQUIRE_SCOPES", "false").lower() in ("1", "true", "yes")
            if not require:
                return
            scopes = {s.strip() for s in (x_scopes or "").split(",") if s.strip()}
            if needed not in scopes:
                raise HTTPException(status_code=403, detail=f"missing scope {needed}")

        @router.get("/tools")
        def list_tools(x_scopes: str | None = Header(default=None, alias="X-Scopes")):
            _require_scope(x_scopes, "ext:mcp_http:mcp")
            return [
                {"name": name, "description": data.get("description", "")}
                for name, data in tool_registry.list().items()
            ]

        @router.get("/tools/{name}/schema")
        def tool_schema(name: str, x_scopes: str | None = Header(default=None, alias="X-Scopes")):
            _require_scope(x_scopes, "ext:mcp_http:mcp")
            try:
                spec = tool_registry.get(name)
            except KeyError:
                return {"error": f"unknown tool: {name}"}
            return {
                "name": name,
                "input_schema": spec.get("input_schema", {}),
                "output_schema": spec.get("output_schema", {}),
                "description": spec.get("description", ""),
            }

        @router.post("/tools/{name}")
        def call_tool(name: str, payload: dict[str, Any] | None = None, x_scopes: str | None = Header(default=None, alias="X-Scopes")):
            _require_scope(x_scopes, "ext:mcp_http:mcp")
            payload = payload or {}
            try:
                spec = tool_registry.get(name)
            except KeyError:
                return {"ok": False, "tool": name, "error": f"unknown tool: {name}"}
            func = spec["func"]
            # Intentionally simple invocation for the skeleton.
            try:
                result = func(**payload) if payload else func()
                return {"ok": True, "tool": name, "result": result}
            except Exception as ex:  # noqa: BLE001
                return {"ok": False, "tool": name, "error": str(ex)}

        @router.get("/schema")
        def schema():
            # Minimal JSON schema envelopes for requests/responses
            return JSONResponse(
                content={
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "title": "mcp-http-lite",
                    "type": "object",
                    "properties": {
                        "handshake": {"type": "object"},
                        "invoke": {"type": "object"},
                        "tool": {"type": "object"},
                    },
                }
            )

        @router.get("/stream")
        async def stream():
            async def event_source() -> AsyncIterator[bytes]:
                i = 0
                while True:
                    i += 1
                    yield f"event: heartbeat\ndata: {{\"tick\": {i}}}\n\n".encode()
                    await asyncio.sleep(5)

            return StreamingResponse(event_source(), media_type="text/event-stream")

        @router.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            await ws.accept()
            try:
                while True:
                    msg = await ws.receive_json()
                    if not isinstance(msg, dict):
                        await ws.send_json({"type": "error", "error": "invalid message"})
                        continue
                    mtype = msg.get("type")
                    if mtype == "ping":
                        await ws.send_json({"type": "pong", "ts": asyncio.get_event_loop().time()})
                    elif mtype == "invoke":
                        name = msg.get("name")
                        payload = msg.get("payload") or {}
                        try:
                            spec = tool_registry.get(name)
                            func = spec["func"]
                            result = func(**payload) if payload else func()
                            await ws.send_json({"type": "result", "tool": name, "ok": True, "result": result})
                        except Exception as ex:  # noqa: BLE001
                            await ws.send_json({"type": "result", "tool": name, "ok": False, "error": str(ex)})
                    else:
                        await ws.send_json({"type": "error", "error": "unknown type"})
            except WebSocketDisconnect:
                return

        return router


def get_extension() -> Extension:
    return MCPHttpExtension()
