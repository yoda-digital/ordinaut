from __future__ import annotations

import asyncio
import os
import random
import string
from typing import Any, Optional, AsyncIterator

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from ordinaut.plugins.base import Capability, Extension, ExtensionInfo


def _rand_suffix(n: int = 6) -> str:
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


class EventsDemo(Extension):
    def info(self) -> ExtensionInfo:
        return ExtensionInfo(id="events_demo", name="Events Demo", version="0.1.0")

    def requested_capabilities(self) -> set[Capability]:
        return {Capability.ROUTES, Capability.EVENTS_PUB, Capability.EVENTS_SUB}

    def setup(
        self,
        *,
        app: FastAPI,
        mount_path: str,
        tool_registry: Any,
        grants: set[Capability],
        context: dict[str, Any] | None = None,
    ):
        if not context or "events" not in context:
            # Shouldn't happen due to grants, but keep graceful
            raise HTTPException(status_code=500, detail="events facade missing")
        events = context["events"]
        router = APIRouter(tags=["events-demo"]) 

        @router.post("/publish/{name}")
        async def publish(name: str, payload: dict[str, Any] | None = None, ns: str | None = None):
            payload = payload or {"ts": str(asyncio.get_event_loop().time())}
            mid = await events.publish(name, payload, namespace=ns)
            return {"ok": True, "message_id": str(mid)}

        @router.get("/stream/{name}")
        async def stream(name: str, group: str = "demo", consumer: str | None = None, ns: str | None = None):
            consumer = consumer or f"c-{_rand_suffix()}"

            async def gen() -> AsyncIterator[bytes]:
                async for msg_id, data in events.subscribe(name, group=group, consumer=consumer, namespace=ns):
                    # encode data
                    try:
                        body = {k.decode(): v.decode() for k, v in data.items()}
                    except Exception:
                        body = {str(k): str(v) for k, v in data.items()}
                    yield f"id: {msg_id}\nevent: message\ndata: {body}\n\n".encode()

            return StreamingResponse(gen(), media_type="text/event-stream")

        return router


def get_extension():
    return EventsDemo()

