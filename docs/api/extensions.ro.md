# Referință API Extensii

API-ul Extensiilor oferă puncte finale pentru gestionarea și interacțiunea cu extensiile Ordinaut. Aceasta include descoperirea extensiilor, monitorizarea sănătății și accesul la funcționalitatea specifică extensiilor.

## Puncte Finale Centrale Extensii

### Status Extensii

Obține informații despre toate extensiile descoperite.

**Punct Final**: `GET /ext/status`  
**Autentificare**: Nu este necesară  
**Scope-uri**: Niciunul

**Răspuns**:
```json
{
  "extensions": {
    "observability": {
      "state": "încărcat",
      "info": {
        "id": "observability", 
        "name": "Observability",
        "version": "0.1.0",
        "description": "Metrici Prometheus și monitorizare"
      },
      "capabilities": ["ROUTES"],
      "loaded_ms": 45,
      "metrics": {
        "requests_total": 150.0,
        "errors_total": 2.0,
        "latency_ms_sum": 1250.5
      }
    }
  },
  "discovery_sources": ["builtin", "env_dir"],
  "total_extensions": 4,
  "loaded_extensions": 3,
  "failed_extensions": 0
}
```

**Exemplu**:
```bash
curl http://localhost:8080/ext/status
```

## Extensii Integrate

### Extensia Observability

Oferă metrici compatibile Prometheus pentru monitorizarea sistemului.

#### Obține Metrici
**Punct Final**: `GET /ext/observability/metrics`  
**Autentificare**: Nu este necesară  
**Content-Type**: `text/plain; version=0.0.4`

Returnează metrici în format Prometheus incluzând:
- Metrici cerere/răspuns HTTP
- Statistici execuție sarcini
- Metrici performanță extensii  
- Utilizarea resurselor sistemului

**Exemplu**:
```bash
curl http://localhost:8080/ext/observability/metrics
```

**Răspuns Eșantion**:
```
# HELP http_requests_total Numărul total de cereri HTTP
# TYPE http_requests_total counter
http_requests_total{method="GET",endpoint="/health"} 45.0

# HELP task_executions_total Numărul total de execuții sarcini
# TYPE task_executions_total counter
task_executions_total{status="success"} 123.0
task_executions_total{status="failed"} 5.0

# HELP extension_requests_total Numărul de cereri extensii
# TYPE extension_requests_total counter
extension_requests_total{extension="webui"} 89.0
```

### Extensia Web UI

Oferă o interfață web pentru gestionarea sarcinilor și monitorizarea sistemului.

#### Obține Interfața Web
**Punct Final**: `GET /ext/webui/`  
**Autentificare**: Nu este necesară (configurabilă)  
**Content-Type**: `text/html`

Returnează pagina HTML principală a interfeței web.

**Exemplu**:
```bash
curl http://localhost:8080/ext/webui/
```

#### Puncte Finale API

**Obține Sarcini**: `GET /ext/webui/api/tasks`
```json
{
  "tasks": [
    {
      "id": "uuid-1234",
      "title": "Briefing Matinal", 
      "status": "activ",
      "next_run": "2025-08-26T08:30:00Z"
    }
  ]
}
```

**Creează Sarcină**: `POST /ext/webui/api/tasks`
```json
{
  "title": "Sarcină Nouă",
  "schedule_kind": "cron",
  "schedule_expr": "0 9 * * *",
  "payload": {
    "pipeline": []
  }
}
```

### Extensia MCP HTTP

Model Context Protocol peste HTTP pentru integrarea asistenților AI.

#### Metadata MCP
**Punct Final**: `GET /ext/mcp_http/meta`  
**Autentificare**: Nu este necesară

```json
{
  "server": "ordinaut-mcp-http",
  "version": "0.2.0", 
  "capabilities": ["handshake", "list_tools", "invoke", "schema", "sse"]
}
```

#### Handshake MCP
**Punct Final**: `POST /ext/mcp_http/handshake`  
**Content-Type**: `application/json`

**Cerere**:
```json
{
  "client": {
    "name": "ChatGPT",
    "version": "1.0"
  }
}
```

**Răspuns**:
```json
{
  "server": {
    "name": "ordinaut-mcp-http",
    "version": "0.2.0"
  },
  "session_id": "sess-uuid-5678"
}
```

#### Listează Instrumentele Disponibile
**Punct Final**: `GET /ext/mcp_http/tools`

```json
{
  "tools": [
    {
      "name": "create_task",
      "description": "Creează o sarcină programată nouă",
      "parameters": {
        "type": "object", 
        "properties": {
          "title": {"type": "string"},
          "schedule": {"type": "string"}
        }
      }
    }
  ]
}
```

#### Invocă Instrument
**Punct Final**: `POST /ext/mcp_http/invoke`

**Cerere**:
```json
{
  "tool": "create_task",
  "parameters": {
    "title": "Raport Zilnic",
    "schedule": "0 18 * * *"
  }
}
```

**Răspuns**:
```json
{
  "success": true,
  "result": {
    "task_id": "uuid-9876",
    "message": "Sarcină creată cu succes"
  }
}
```

### Extensia Demo Evenimente

Demonstrează sistemul de evenimente Redis Streams.

#### Publică Eveniment
**Punct Final**: `POST /ext/events_demo/publish/{stream}`  
**Content-Type**: `application/json`

**Exemplu**:
```bash
curl -X POST http://localhost:8080/ext/events_demo/publish/test \\
  -H "Content-Type: application/json" \\
  -d '{"mesaj": "Salut Evenimente", "timestamp": "2025-08-26T10:00:00Z"}'
```

**Răspuns**:
```json
{
  "success": true,
  "stream": "test",
  "event_id": "1692873600000-0",
  "message": "Eveniment publicat cu succes"
}
```

#### Abonează-te la Evenimente (Server-Sent Events)
**Punct Final**: `GET /ext/events_demo/subscribe/{stream}`  
**Content-Type**: `text/event-stream`

Stabilește o conexiune SSE pentru a primi evenimente în timp real.

**Exemplu**:
```bash
curl -N http://localhost:8080/ext/events_demo/subscribe/test
```

**Stream Răspuns**:
```
data: {"stream": "test", "id": "1692873600000-0", "data": {"mesaj": "Salut Evenimente"}}

data: {"stream": "test", "id": "1692873600001-0", "data": {"mesaj": "Alt eveniment"}}
```

## API Dezvoltare Extensii

### Înregistrarea Extensiilor

Extensiile sunt descoperite și înregistrate automat. Nu este necesară un API de înregistrare manuală.

**Surse de Descoperire**:
1. Integrate: directorul `ordinaut/extensions/`
2. Mediu: variabila de mediu `ORDINAUT_EXT_PATHS`  
3. Puncte de intrare: grupul de puncte de intrare Python `ordinaut.plugins`

### Capabilitățile Extensiilor

Extensiile pot solicita următoarele capabilități:

| Capabilitate | Descriere | Acces API |
|-------------|-----------|-----------|
| `ROUTES` | Crearea punctelor finale HTTP | Montarea router-ului FastAPI |
| `TOOLS` | Acces registru instrumente | `tool_registry.register_tool()` |
| `EVENTS_PUB` | Publicarea evenimentelor | `events.publish()` |
| `EVENTS_SUB` | Abonarea la evenimente | `events.subscribe()` |
| `BACKGROUND_TASKS` | Procese de lungă durată | `background.start_task()` |
| `STATIC` | Servirea fișierelor statice | Rutare automată fișiere statice |

### Obiecte Context

Extensiile primesc obiecte context bazate pe capabilitățile acordate:

#### Context Registru Instrumente
```python
# Disponibil când capabilitatea TOOLS este acordată
tool_registry.register_tool(name: str, func: Callable, schema: dict)
tool_registry.list_tools() -> List[ToolInfo]
tool_registry.get_tool(name: str) -> ToolInfo
```

#### Context Evenimente  
```python
# Disponibil când EVENTS_PUB sau EVENTS_SUB sunt acordate
await events.publish(stream: str, data: dict) -> str
await events.subscribe(pattern: str, handler: Callable) -> None
await events.unsubscribe(pattern: str) -> None
```

#### Context Sarcini de Fond
```python
# Disponibil când capabilitatea BACKGROUND_TASKS este acordată  
await background.start_task(name: str, coro: Coroutine) -> None
await background.stop_task(name: str) -> None
background.list_tasks() -> List[TaskInfo]
```

## Autentificare și Autorizare

### Controlul Accesului Bazat pe Scope-uri

Extensiile pot fi protejate cu autorizare bazată pe scope-uri:

**Configurație**:
```bash
export ORDINAUT_REQUIRE_SCOPES=true
```

**Anteturi Cerere**:
```bash
curl -H "X-Scopes: ext:extensia_mea:routes" \\
     http://localhost:8080/ext/extensia_mea/protejat
```

**Șablon Scope Necesar**: `ext:{extension_id}:routes`

### Autentificare Token JWT

Când autentificarea JWT este activată, extensiile moștenesc aceleași cerințe de autentificare ca API-ul central.

**Anteturi Cerere**:
```bash
curl -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \\
     http://localhost:8080/ext/extensia_mea/securizat
```

## Răspunsuri de Eroare

Toate punctele finale ale extensiilor urmează formate consistente de răspuns de eroare:

### 400 Cerere Invalidă
```json
{
  "error": "bad_request",
  "message": "Parametri de cerere invalizi",
  "details": {
    "field": "schedule_expr", 
    "issue": "Expresie cron invalidă"
  }
}
```

### 401 Neautorizat
```json
{
  "error": "unauthorized",
  "message": "Autentificare necesară",
  "details": {
    "required_scopes": ["ext:extensia_mea:routes"]
  }
}
```

### 403 Interzis  
```json
{
  "error": "forbidden",
  "message": "Permisiuni insuficiente",
  "details": {
    "required_capability": "TOOLS",
    "granted_capabilities": ["ROUTES"]
  }
}
```

### 404 Nu a fost găsit
```json
{
  "error": "not_found",
  "message": "Extensia nu a fost găsită",
  "details": {
    "extension_id": "extensie_inexistenta"
  }
}
```

### 500 Eroare Internă de Server
```json
{
  "error": "internal_error",
  "message": "Execuția extensiei a eșuat",
  "details": {
    "extension_id": "extensia_mea",
    "error_type": "ImportError",
    "traceback": "..."
  }
}
```

## Limitarea Ratei

Punctele finale ale extensiilor respectă aceeași configurație de limitare a ratei ca API-ul central:

**Anteturi**:
- `X-RateLimit-Limit`: Limita de cereri per fereastră
- `X-RateLimit-Remaining`: Cererile rămase în fereastra curentă
- `X-RateLimit-Reset`: Timestamp resetare fereastră

**429 Prea Multe Cereri**:
```json
{
  "error": "rate_limit_exceeded",
  "message": "Limita de rată depășită", 
  "details": {
    "limit": 100,
    "window": "60s",
    "reset_at": "2025-08-26T10:01:00Z"
  }
}
```

## Verificări de Sănătate

Extensiile pot implementa puncte finale de verificare a sănătății pentru monitorizare:

**Convenție**: `GET /ext/{extension_id}/health`

**Răspuns Standard**:
```json
{
  "status": "sănătos",
  "timestamp": "2025-08-26T10:00:00Z", 
  "version": "1.0.0",
  "checks": {
    "database": "sănătos",
    "external_api": "sănătos", 
    "background_tasks": "sănătos"
  }
}
```

## Suport WebSocket

Extensiile pot implementa puncte finale WebSocket pentru comunicare în timp real:

**Șablon Punct Final**: `WS /ext/{extension_id}/ws/{path}`

**Exemplu Implementare**:
```python
from fastapi import WebSocket

@router.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Gestionează comunicarea WebSocket
            data = await websocket.receive_json()
            response = await proceseaza_date_websocket(data)
            await websocket.send_json(response)
    except WebSocketDisconnect:
        # Gestionează deconectarea clientului
        pass
```

## Metrici Extensii

Toate extensiile primesc automat colectare de metrici de bază:

**Metrici Disponibile**:
- `extension_requests_total{extension, endpoint, method, status}`
- `extension_request_duration_seconds{extension, endpoint, method}`
- `extension_errors_total{extension, endpoint, error_type}`
- `extension_active_connections{extension, endpoint}`

**Acces prin Extensia Observability**:
```bash
curl http://localhost:8080/ext/observability/metrics | grep extension
```

Această referință API oferă documentația completă pentru interacțiunea cu sistemul de extensii Ordinaut, permițând dezvoltatorilor să construiască extensii puternice și să integreze eficient sisteme externe.