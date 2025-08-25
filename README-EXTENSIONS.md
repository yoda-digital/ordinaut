# Ordinaut Extension System — Canonical, Accurate, Tested

This document replaces all previous extension docs. It reflects the code that is actually running in this repository today. If you read conflicting guidance elsewhere, consider it obsolete.

Summary:
- Canonical built-in extensions live in `ordinaut/extensions/`.
- External extensions are loaded via `ORDINAUT_EXT_PATHS` or Python entry points (`ordinaut.plugins`).
- The extension API is defined in `ordinaut/plugins/base.py`; the loader is `ordinaut/plugins/loader.py`.
- Routes are mounted under `/ext/{id}` and can be lazy-loaded on first hit.

## Architecture At A Glance

- `Extension` class: implements `info()`, `requested_capabilities()`, `setup()`, optional `on_startup()`/`on_shutdown()`.
- `Capabilities`: `ROUTES`, `TOOLS`, `STATIC`, `EVENTS_PUB`, `EVENTS_SUB`, `BACKGROUND_TASKS`.
- Manifest (`extension.json`): required fields `id`, `name`, `version`, `module`; optional `enabled`, `eager`, `grants`.
- Loader (`ExtensionLoader`): discovers from `ordinaut/extensions`, `ORDINAUT_EXT_PATHS`, and `ordinaut.plugins` entry points; enforces capability grants; mounts routers; manages lazy-load, background supervisor, and events manager.
- Tool registry: `ToolRegistry` (writable), `ToolRegistryView` (read-only), `NamespacedToolRegistrar` (write-limited `ext.{id}.` prefix).

## Canonical Layout

```
ordinaut/
  api/main.py                 # Production app; initializes ExtensionLoader
  engine/registry.py          # ToolRegistry + helpers for extensions
  plugins/
    base.py                   # Extension API + Capability enum
    loader.py                 # Discovery, grants, router mount, lazy-load
    background.py             # Background task supervisor
    events.py                 # Redis Streams events facade
    schema.py                 # JSON Schema for extension.json
  extensions/                 # Built-in extensions (canonical location)
    webui/
      extension.json
      extension.py
      static/index.html
    mcp_http/
      extension.json
      extension.py
    observability/
      extension.json
      extension.py
    events_demo/
      extension.json
      extension.py
```

Do not create a top-level `extensions/` folder in this repo; it is obsolete. Use `ordinaut/extensions` for built-ins, or external paths via `ORDINAUT_EXT_PATHS` for custom extensions.

## Manifest Schema (what the loader actually validates)

File: `ordinaut/plugins/schema.py`
- Required: `id` (slug), `name`, `version`, `module`
- Optional: `description`, `enabled` (default true), `eager` (default false), `grants` (array of capability names)

Example:
```json
{
  "id": "awesome",
  "name": "Awesome Extension",
  "version": "0.1.0",
  "module": "extension.py",
  "enabled": true,
  "eager": false,
  "grants": ["ROUTES", "TOOLS"]
}
```

## Extension API (exact method names)

File: `ordinaut/plugins/base.py`
- `info() -> ExtensionInfo`: returns `id`, `name`, `version`, `description` (optional)
- `requested_capabilities() -> set[Capability]`: what this extension would like to use
- `setup(app, mount_path, tool_registry, grants, context) -> Optional[APIRouter]`:
  - `tool_registry` is either `ToolRegistryView` (read-only) or `NamespacedToolRegistrar` (if `TOOLS` granted)
  - `grants` is the intersection of requested vs manifest `grants`
  - `context` may contain:
    - `tools_view`: always present (read-only view)
    - `background`: present if `BACKGROUND_TASKS` granted and supervisor enabled
    - `events`: events facade if `EVENTS_*` granted
- Optional lifecycle: `async def on_startup(app)` / `async def on_shutdown(app)`

If `setup()` returns an `APIRouter` and `ROUTES` is granted, the loader mounts it at `/ext/{id}`.

## Discovery & Lazy Loading

The loader (`ExtensionLoader`) discovers extensions in this order:
1) `ordinaut/extensions/*` (built-in)
2) Each path in `ORDINAUT_EXT_PATHS` (colon-separated):
   - If it’s a directory, it must contain `extension.json` and `extension.py`
   - If it’s a file, it is treated as a module; the id becomes the filename stem
3) Python entry points group `ordinaut.plugins` (packaged extensions)

Eager extensions (`"eager": true`) load at startup. Others are lazy-loaded on first request to `/ext/{id}/...`; the loader then issues a 307 redirect so the newly mounted router handles the same URL.

## Security & Scopes

- Capability enforcement: only the intersection of `requested_capabilities()` and manifest `grants` is active.
- Route access control: when `ORDINAUT_REQUIRE_SCOPES` is true, requests to `/ext/{id}` routes must include header `X-Scopes` containing `ext:{id}:routes` or a 403 is returned.
- Tool registration is namespaced: tools must be registered under `ext.{id}.<name>`.

## Writing an Extension (working example)

Create `ordinaut/extensions/awesome/extension.json`:
```json
{
  "id": "awesome",
  "name": "Awesome",
  "version": "0.1.0",
  "module": "extension.py",
  "enabled": true,
  "grants": ["ROUTES", "TOOLS"]
}
```

Create `ordinaut/extensions/awesome/extension.py`:
```python
from __future__ import annotations
from fastapi import APIRouter, FastAPI
from ordinaut.plugins.base import Capability, Extension, ExtensionInfo

class Awesome(Extension):
    def info(self) -> ExtensionInfo:
        return ExtensionInfo(id="awesome", name="Awesome", version="0.1.0")

    def requested_capabilities(self) -> set[Capability]:
        return {Capability.ROUTES, Capability.TOOLS}

    def setup(self, *, app: FastAPI, mount_path: str, tool_registry, grants: set[Capability], context=None):
        router = APIRouter()

        @router.get("/hello")
        def hello():
            return {"hello": "world"}

        if Capability.TOOLS in grants:
            def ping_tool():
                return {"pong": True}
            tool_registry.register("ext.awesome.ping", ping_tool, description="Ping tool from awesome ext")

        return router

def get_extension() -> Extension:
    return Awesome()
```

Run the API:
```
uvicorn api.main:app --reload --port 8080
# http://localhost:8080/ext/awesome/hello
# http://localhost:8080/extensions
# http://localhost:8080/tools
```

## Environment Variables

- `ORDINAUT_EXT_PATHS` — external extension paths (colon-separated). Each path is a directory containing `extension.json` + `extension.py`, or a single Python file.
- `ORDINAUT_EXT_ENTRY_GRANTS` — JSON dict of grants for entry point plugins: `{ "pkg_id": ["ROUTES","TOOLS"] }`
- `ORDINAUT_EXT_ENTRY_EAGER` — JSON dict of eager flags for entry point plugins: `{ "pkg_id": true }`
- `ORDINAUT_REQUIRE_SCOPES` — when true, require `X-Scopes: ext:{id}:routes` for extension routes.

## Migration Notes (be blunt)

- Top-level `extensions/` is dead. The loader never scans it. If you have old content there, move it under `ordinaut/extensions/` (for built-ins) or point `ORDINAUT_EXT_PATHS` to the new location.
- Do not invent new capability names; use `Capability` enum values exactly.
- Do not register tools outside your namespace; the registrar will reject it.

## Verification Checklist

1) `GET /extensions` lists: webui, mcp_http, observability, events_demo.
2) `GET /ext/webui/` returns the static index page (lazy-load OK).
3) `GET /tools` shows any tools registered by extensions (may be empty if none register).
4) Add a toy external extension via `ORDINAUT_EXT_PATHS` and hit its route; verify it appears in `/extensions`.

That’s it. This reflects the implementation in `ordinaut/plugins/loader.py` and is the only extension documentation you should trust.
