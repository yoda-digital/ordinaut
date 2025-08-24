# Ordinaut Extension System (Simple, Modern, Effective)

This repo includes a tiny, pragmatic extension architecture focused on: simplicity, safety via declared capabilities, and first-class FastAPI integration. It lets you ship features like an MCP HTTP endpoint and a Web UI as separately developed extensions without changing core code.

## Concepts

- `Extension` (class): Minimal base with optional hooks.
- `Capabilities`: Declarative permission set (e.g., `ROUTES`, `TOOLS`, `STATIC`, `EVENTS_PUB`, `EVENTS_SUB`, `BACKGROUND_TASKS`).
- `Manifest` (`extension.json`): Declares id, name, version, module path, enabled flag, and granted capabilities.
- `Loader`: Discovers extensions in `extensions/` or via `ORDINAUT_EXT_PATHS` and mounts their routers under `/ext/{id}`.
- `ToolRegistry`: Simple registry for callable tools exposed to agents and optional MCP surfaces.

## Directory Layout

```
ordinaut/
  api/main.py                 # Creates FastAPI app, loads extensions
  engine/registry.py          # Minimal tool registry
  plugins/
    base.py                   # Extension base + capabilities (internal)
    loader.py                 # Discovery + lazy-loading dispatcher (internal)
    background.py             # Central background task supervisor (quotas)
    events.py                 # Redis Streams wiring (scoped pub/sub)
    schema.py                 # JSON Schema for extension.json
extensions/
  webui/
    extension.json            # Manifest
    extension.py              # Implements Extension
    static/index.html         # Example UI
  mcp_http/
    extension.json
    extension.py              # Skeleton MCP-over-HTTP surface
```

## Writing an Extension

1) Create a directory (e.g., `extensions/awesome_ext`) with two files:

`extension.json`
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

`extension.py`
```python
from fastapi import APIRouter, FastAPI
from ordinaut.plugins.base import Extension, ExtensionInfo, Capability

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

        def ping_tool():
            return {"pong": True}

        if Capability.TOOLS in grants:
            tool_registry.register("ext.awesome.ping", ping_tool, description="Ping tool from awesome ext")

        return router

def get_extension():
    return Awesome()
```

2) Run the API and visit:
```
uvicorn ordinaut.api.main:app --reload
# http://localhost:8000/ext/awesome/hello
# http://localhost:8000/extensions
# http://localhost:8000/tools
```

## Discovery & Lazy Loading

- Manifests in `extensions/*/extension.json` are validated and cached.
- Only extensions with `"eager": true` load at startup; others lazy-load on first request to `/ext/{id}`.
- A central dispatcher at `/ext/{id}/{...}` triggers load and redirects so mounted routes take over.

### Python Entry Points

- Plugins can be shipped via pip with entry points in group `ordinaut.plugins`.
- Each entry point name is used as the plugin id. The value should point to a factory function, e.g. `pkg.module:get_extension`.
- Host grants/eager can be configured with env vars:
  - `ORDINAUT_EXT_ENTRY_GRANTS` JSON, e.g.: `{ "myplugin": ["ROUTES", "TOOLS"] }`
  - `ORDINAUT_EXT_ENTRY_EAGER` JSON, e.g.: `{ "myplugin": true }`

## Discovery via Environment

Set `ORDINAUT_EXT_PATHS` to include external paths. Each path can be a directory containing `extension.py` + `extension.json`, or a single Python file (manifest implied with id from filename).

```
export ORDINAUT_EXT_PATHS="/path/to/your/ext1:/path/to/your/ext2/extension.py"
```

## Security & Permissions

Extensions declare what they need in `requested_capabilities()`. Deployment decides what to grant in the manifest (`grants`). The loader passes only the intersection of requested and granted capabilities.

Enforcement:
- Tools: if `TOOLS` is granted, a namespaced registrar is provided (prefix `ext.<id>.`). Otherwise a read-only view is provided for listing/getting tools.
- Background: if `BACKGROUND_TASKS` is granted, a central supervisor is passed via `context["background"]` to register small periodic tasks with quotas.
- Events: if `EVENTS_PUB`/`EVENTS_SUB` are granted, an events facade scoped to `ext.<id>` streams is passed via `context["events"]`.
- No global context leaks: extensions only receive handles that match their grants.

## MCP Server as an Extension

Use `ROUTES` to expose a small HTTP surface, e.g., `/ext/mcp_http`. The provided `extensions/mcp_http` is a skeleton that:
- Advertises simple meta info
- Lists tools registered in `ToolRegistry`
- Invokes tools via POST

For a full MCP implementation, map MCP handshake and protocol messages to HTTP routes or consider a standalone MCP process that talks to Ordinaut via REST; both patterns fit this extension system.

## Web UI as an Extension

The `webui` extension serves a modern, minimal static page at `/ext/webui/`. Replace `static/index.html` with your SPA assets or mount a router with server-rendered endpoints.

## Observability & Health

- A global middleware tracks per-plugin request counts, total latency, and errors.
- `/extensions` returns manifest details plus status and metrics for each plugin.

## Roadmap Hooks (kept simple)

- Events: wire `EVENTS_PUB`/`EVENTS_SUB` to Redis Streams consumer groups.
- Auth scopes: pass an auth gate to loader to filter router mounts by scope.
- Packaging: support Python entry points for pip-installed extensions.
