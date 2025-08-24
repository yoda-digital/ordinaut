from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
import inspect
import asyncio
import time

from .base import Capability, Extension, ExtensionInfo
from .schema import MANIFEST_SCHEMA
from jsonschema import validate
from ordinaut.engine.registry import (
    ToolRegistry,
    ToolRegistryView,
    NamespacedToolRegistrar,
)
from .background import BackgroundTaskSupervisor
from .events import EventsManager
from importlib import metadata as importlib_metadata


@dataclass
class ExtensionSpec:
    id: str
    root: Path
    module: str
    enabled: bool = True
    grants: set[Capability] | None = None
    eager: bool = False


class ExtensionLoader:
    def __init__(self, app: FastAPI, *, mount_root: str = "/ext") -> None:
        self.app = app
        self.mount_root = mount_root.rstrip("/")
        self.loaded: dict[str, Extension] = {}
        self.specs: dict[str, ExtensionSpec] = {}
        self.status: dict[str, dict[str, Any]] = {}
        self.metrics: dict[str, dict[str, float]] = {}
        self._bg_supervisor: BackgroundTaskSupervisor | None = None
        self._events_manager: EventsManager | None = None

    def discover(self) -> list[ExtensionSpec]:
        specs: list[ExtensionSpec] = []
        base = Path("extensions")
        if base.exists():
            for d in sorted(p for p in base.iterdir() if p.is_dir()):
                manifest = d / "extension.json"
                module = d / "extension.py"
                if manifest.exists() and module.exists():
                    with manifest.open() as f:
                        m = json.load(f)
                    validate(instance=m, schema=MANIFEST_SCHEMA)
                    grants = set(Capability[g] for g in m.get("grants", []))
                    specs.append(ExtensionSpec(
                        id=m["id"], root=d, module=str(module),
                        enabled=bool(m.get("enabled", True)), grants=grants,
                        eager=bool(m.get("eager", False)),
                    ))
        env_paths = os.environ.get("ORDINAUT_EXT_PATHS", "")
        for p in filter(None, env_paths.split(":")):
            path = Path(p).expanduser()
            if path.is_dir():
                manifest = path / "extension.json"
                module = path / "extension.py"
                if manifest.exists() and module.exists():
                    with manifest.open() as f:
                        m = json.load(f)
                    validate(instance=m, schema=MANIFEST_SCHEMA)
                    grants = set(Capability[g] for g in m.get("grants", []))
                    specs.append(ExtensionSpec(
                        id=m["id"], root=path, module=str(module),
                        enabled=bool(m.get("enabled", True)), grants=grants,
                        eager=bool(m.get("eager", False)),
                    ))
            elif path.is_file():
                specs.append(ExtensionSpec(
                    id=path.stem, root=path.parent, module=str(path), enabled=True, grants=set()
                ))
        # 3) Python entry points: ordinaut.plugins
        try:
            eps = importlib_metadata.entry_points()
            if hasattr(eps, "select"):
                group = eps.select(group="ordinaut.plugins")
            else:
                group = eps.get("ordinaut.plugins", [])
            # Optional grants/eager config from env (JSON dict: id -> [caps])
            grants_cfg = {}
            eager_cfg = {}
            try:
                import json as _json
                grants_cfg = _json.loads(os.environ.get("ORDINAUT_EXT_ENTRY_GRANTS", "{}"))
                eager_cfg = _json.loads(os.environ.get("ORDINAUT_EXT_ENTRY_EAGER", "{}"))
            except Exception:
                pass
            for ep in group:  # type: ignore[assignment]
                pid = ep.name.replace(" ", "_")
                grants = set()
                for g in grants_cfg.get(pid, []):
                    try:
                        grants.add(Capability[g])
                    except KeyError:
                        pass
                specs.append(ExtensionSpec(
                    id=pid,
                    root=Path("<entrypoint>"),
                    module=str(ep.value),
                    enabled=True,
                    grants=grants,
                    eager=bool(eager_cfg.get(pid, False)),
                ))
        except Exception:
            pass
        return specs

    def _import_from_path(self, module_path: str):
        spec = importlib.util.spec_from_file_location(Path(module_path).stem, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot import extension module: {module_path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)  # type: ignore
        return mod

    def load_all(self, *, tool_registry: ToolRegistry, context: dict[str, Any] | None = None) -> list[ExtensionInfo]:
        infos: list[ExtensionInfo] = []
        # Cache specs and initialize status/metrics
        for spec in self.discover():
            if not spec.enabled:
                continue
            self.specs[spec.id] = spec
            self.status[spec.id] = {"state": "discovered"}
            self.metrics[spec.id] = {"requests_total": 0.0, "errors_total": 0.0, "latency_ms_sum": 0.0}

        # Eager load selected plugins
        for pid, spec in self.specs.items():
            if spec.eager:
                info = self._ensure_loaded(pid, tool_registry=tool_registry, context=context or {})
                if info:
                    infos.append(info)

        # Initialize background supervisor if needed
        if any(Capability.BACKGROUND_TASKS in (s.grants or set()) for s in self.specs.values()):
            self._bg_supervisor = BackgroundTaskSupervisor()
            async def _start_bg():
                await self._bg_supervisor.start()
            async def _stop_bg():
                await self._bg_supervisor.stop()
            self.app.add_event_handler("startup", _start_bg)
            self.app.add_event_handler("shutdown", _stop_bg)

        # Initialize events manager if any plugin needs events
        if any(
            (Capability.EVENTS_PUB in (s.grants or set())) or (Capability.EVENTS_SUB in (s.grants or set()))
            for s in self.specs.values()
        ):
            self._events_manager = EventsManager()
            async def _start_events():
                await self._events_manager.start()
            async def _stop_events():
                await self._events_manager.stop()
            self.app.add_event_handler("startup", _start_events)
            self.app.add_event_handler("shutdown", _stop_events)

        return infos


    def _record_metric(self, plugin_id: str, duration_ms: float, ok: bool) -> None:
        m = self.metrics.get(plugin_id)
        if not m:
            m = self.metrics[plugin_id] = {"requests_total": 0.0, "errors_total": 0.0, "latency_ms_sum": 0.0}
        m["requests_total"] += 1
        m["latency_ms_sum"] += duration_ms
        if not ok:
            m["errors_total"] += 1

    def record_request(self, plugin_id: str, duration_ms: float, ok: bool) -> None:
        self._record_metric(plugin_id, duration_ms, ok)

    def _ensure_loaded(self, plugin_id: str, *, tool_registry: ToolRegistry, context: dict[str, Any]) -> ExtensionInfo | None:
        if plugin_id in self.loaded:
            return self.loaded[plugin_id].info()
        spec = self.specs.get(plugin_id)
        if not spec or not spec.enabled:
            return None
        started = time.time()
        try:
            ext: Extension
            if Path(spec.module).is_file():
                mod = self._import_from_path(spec.module)
                if not hasattr(mod, "get_extension"):
                    raise RuntimeError(f"Extension module {spec.module} missing get_extension()")
                factory = getattr(mod, "get_extension")
                ext = factory()
            else:
                # Treat as import string: 'package.module:get_extension' or 'package.module.factory'
                mod_name, _, attr = spec.module.partition(":")
                if not attr:
                    mod_name, _, attr = spec.module.rpartition(".")
                if not mod_name:
                    raise RuntimeError(f"Invalid extension import string: {spec.module}")
                mod = __import__(mod_name, fromlist=[attr])
                factory = getattr(mod, attr)
                ext = factory()
            info = ext.info()
            if info.id != spec.id:
                raise RuntimeError(f"Extension id mismatch: manifest '{spec.id}' vs class '{info.id}'")
            requested = ext.requested_capabilities()
            granted = spec.grants or set()
            grants = requested.intersection(granted) if granted else requested

            tool_view = ToolRegistryView(tool_registry)
            tool_registrar = NamespacedToolRegistrar(tool_registry, prefix=f"ext.{info.id}.")

            # Initialize events manager if needed for this extension
            if self._events_manager is None and (
                Capability.EVENTS_PUB in grants or Capability.EVENTS_SUB in grants
            ):
                print(f"DEBUG: Initializing events manager for extension {info.id}")
                self._events_manager = EventsManager()
                # Note: EventsManager will auto-start when facade_for is called

            ctx = {"tools_view": tool_view}
            if Capability.BACKGROUND_TASKS in grants and self._bg_supervisor is not None:
                ctx["background"] = self._bg_supervisor
            if self._events_manager is not None and (
                Capability.EVENTS_PUB in grants or Capability.EVENTS_SUB in grants
            ):
                print(f"DEBUG: Adding events context for extension {info.id}")
                ctx["events"] = self._events_manager.facade_for(
                    info.id,
                    pub=Capability.EVENTS_PUB in grants,
                    sub=Capability.EVENTS_SUB in grants,
                )
                print(f"DEBUG: Events context added: {ctx.get('events') is not None}")
            else:
                print(f"DEBUG: No events context for {info.id}: events_manager={self._events_manager is not None}, grants={grants}")

            router: APIRouter | None = ext.setup(
                app=self.app,
                mount_path=f"{self.mount_root}/{info.id}",
                tool_registry=tool_registrar if Capability.TOOLS in grants else tool_view,
                grants=grants,
                context=ctx,
            )
            if router and Capability.ROUTES in grants:
                # Per-plugin simple scope dependency: require 'ext:{id}:routes' unless disabled
                def make_dep(pid: str):
                    async def dep(x_scopes: str | None = Header(default=None, alias="X-Scopes")):
                        require = os.environ.get("ORDINAUT_REQUIRE_SCOPES", "false").lower() in ("1","true","yes")
                        if not require:
                            return
                        scopes = {s.strip() for s in (x_scopes or "").split(",") if s.strip()}
                        needed = f"ext:{pid}:routes"
                        if needed not in scopes:
                            raise HTTPException(status_code=403, detail=f"missing scope {needed}")
                    return dep
                self.app.include_router(
                    router,
                    prefix=f"{self.mount_root}/{info.id}",
                    dependencies=[Depends(make_dep(info.id))],
                )

            async def _startup(e=ext, app=self.app):
                try:
                    # Try async
                    fn = e.on_startup
                    if inspect.iscoroutinefunction(fn):
                        await asyncio.wait_for(fn(app), timeout=10)
                    else:
                        loop = asyncio.get_running_loop()
                        await asyncio.wait_for(loop.run_in_executor(None, fn, app), timeout=10)
                except Exception as ex:  # noqa: BLE001
                    self.status[info.id] = {"state": "error", "phase": "startup", "error": str(ex)}

            async def _shutdown(e=ext, app=self.app):
                try:
                    fn = e.on_shutdown
                    if inspect.iscoroutinefunction(fn):
                        await asyncio.wait_for(fn(app), timeout=10)
                    else:
                        loop = asyncio.get_running_loop()
                        await asyncio.wait_for(loop.run_in_executor(None, fn, app), timeout=10)
                except Exception as ex:  # noqa: BLE001
                    self.status[info.id] = {"state": "error", "phase": "shutdown", "error": str(ex)}

            self.app.add_event_handler("startup", _startup)
            self.app.add_event_handler("shutdown", _shutdown)

            self.loaded[info.id] = ext
            self.status[info.id] = {"state": "loaded", "loaded_ms": int((time.time() - started) * 1000)}
            return info
        except Exception as ex:  # noqa: BLE001
            print(f"DEBUG: Extension {plugin_id} failed to load with exception: {ex}")
            import traceback
            traceback.print_exc()
            self.status[plugin_id] = {"state": "error", "error": str(ex)}
            return None
