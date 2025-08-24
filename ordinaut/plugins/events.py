from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, List, Dict

from redis.asyncio import Redis


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@dataclass
class EventsFacade:
    plugin_id: str
    _client: Redis
    allow_pub: bool
    allow_sub: bool

    def _stream_name(self, name: str, namespace: Optional[str] = None) -> str:
        # Scoped per plugin: ext:{id}:{namespace}:{name} or default namespace 'events'
        ns = namespace or "events"
        return f"ext:{self.plugin_id}:{ns}:{name}"

    async def publish(self, name: str, payload: dict[str, Any], *, namespace: Optional[str] = None) -> str:
        if not self.allow_pub:
            raise PermissionError("EVENTS_PUB not granted")
        stream = self._stream_name(name, namespace)
        # Serialize complex values to JSON strings for Redis XADD
        serialized_payload = {}
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                import json
                serialized_payload[str(key)] = json.dumps(value)
            else:
                serialized_payload[str(key)] = str(value)
        return await self._client.xadd(stream, serialized_payload)

    async def subscribe(
        self,
        name: str,
        *,
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = 5000,
        create_group: bool = True,
        namespace: Optional[str] = None,
    ) -> AsyncIterator[tuple[str, dict[bytes, bytes]]]:
        if not self.allow_sub:
            raise PermissionError("EVENTS_SUB not granted")
        stream = self._stream_name(name, namespace)
        if create_group:
            try:
                await self._client.xgroup_create(stream, group, id="$", mkstream=True)
            except Exception:
                # group may already exist
                pass
        while True:
            resp = await self._client.xreadgroup(group, consumer, streams={stream: ">"}, count=count, block=block_ms)
            if not resp:
                continue
            for _stream, messages in resp:
                for msg_id, data in messages:
                    yield msg_id, data
                    try:
                        await self._client.xack(stream, group, msg_id)
                    except Exception:
                        pass


class EventsManager:
    def __init__(self) -> None:
        self._client: Optional[Redis] = None

    async def start(self) -> None:
        if self._client is None:
            self._client = Redis.from_url(_redis_url())
            # Ping to validate
            try:
                await self._client.ping()
            except Exception:
                # Leave client; operations will fail fast
                pass

    async def stop(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            finally:
                self._client = None

    def facade_for(self, plugin_id: str, *, pub: bool, sub: bool) -> EventsFacade:
        if self._client is None:
            # For lazy-loaded extensions, initialize the client synchronously
            from redis.asyncio import Redis
            self._client = Redis.from_url(_redis_url())
            # Note: We skip the async ping check for lazy initialization
            print(f"DEBUG: EventsManager auto-started for lazy-loaded extension {plugin_id}")
        return EventsFacade(plugin_id=plugin_id, _client=self._client, allow_pub=pub, allow_sub=sub)

    async def health_for_plugin(self, plugin_id: str, *, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Return basic stream health for all streams under ext:{id}:{ns}:*.

        Uses SCAN to find keys; reports per-stream groups and consumer counts.
        """
        if self._client is None:
            raise RuntimeError("EventsManager not started")
        ns = namespace or "events"
        pattern = f"ext:{plugin_id}:{ns}:*"
        cursor = 0
        streams: List[str] = []
        while True:
            cursor, keys = await self._client.scan(cursor=cursor, match=pattern, count=50)
            for k in keys:
                streams.append(k.decode() if isinstance(k, bytes) else k)
            if cursor == 0:
                break
        details: Dict[str, Any] = {}
        for s in streams:
            try:
                groups = await self._client.xinfo_groups(s)
            except Exception:
                groups = []
            details[s] = {"groups": groups}
        return {"namespace": ns, "streams": details}
