# Справочник API Расширений

API Расширений предоставляет конечные точки для управления и взаимодействия с расширениями Ordinaut. Это включает обнаружение расширений, мониторинг здоровья и доступ к специфической функциональности расширений.

## Основные Конечные Точки Расширений

### Статус Расширений

Получить информацию о всех обнаруженных расширениях.

**Конечная Точка**: `GET /ext/status`  
**Аутентификация**: Не требуется  
**Области**: Никаких

**Ответ**:
```json
{
  "extensions": {
    "observability": {
      "state": "загружено",
      "info": {
        "id": "observability", 
        "name": "Observability",
        "version": "0.1.0",
        "description": "Метрики Prometheus и мониторинг"
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

**Пример**:
```bash
curl http://localhost:8080/ext/status
```

## Встроенные Расширения

### Расширение Observability

Предоставляет совместимые с Prometheus метрики для системного мониторинга.

#### Получить Метрики
**Конечная Точка**: `GET /ext/observability/metrics`  
**Аутентификация**: Не требуется  
**Content-Type**: `text/plain; version=0.0.4`

Возвращает метрики в формате Prometheus включая:
- Метрики HTTP запросов/ответов
- Статистику выполнения задач
- Метрики производительности расширений  
- Использование системных ресурсов

**Пример**:
```bash
curl http://localhost:8080/ext/observability/metrics
```

**Пример Ответа**:
```
# HELP http_requests_total Общее количество HTTP запросов
# TYPE http_requests_total counter
http_requests_total{method="GET",endpoint="/health"} 45.0

# HELP task_executions_total Общее количество выполнений задач
# TYPE task_executions_total counter
task_executions_total{status="success"} 123.0
task_executions_total{status="failed"} 5.0

# HELP extension_requests_total Количество запросов расширений
# TYPE extension_requests_total counter
extension_requests_total{extension="webui"} 89.0
```

### Расширение Web UI

Предоставляет веб-интерфейс для управления задачами и системного мониторинга.

#### Получить Веб Интерфейс
**Конечная Точка**: `GET /ext/webui/`  
**Аутентификация**: Не требуется (настраиваемая)  
**Content-Type**: `text/html`

Возвращает главную HTML страницу веб интерфейса.

**Пример**:
```bash
curl http://localhost:8080/ext/webui/
```

#### Конечные Точки API

**Получить Задачи**: `GET /ext/webui/api/tasks`
```json
{
  "tasks": [
    {
      "id": "uuid-1234",
      "title": "Утренний Брифинг", 
      "status": "активная",
      "next_run": "2025-08-26T08:30:00Z"
    }
  ]
}
```

**Создать Задачу**: `POST /ext/webui/api/tasks`
```json
{
  "title": "Новая Задача",
  "schedule_kind": "cron",
  "schedule_expr": "0 9 * * *",
  "payload": {
    "pipeline": []
  }
}
```

### Расширение MCP HTTP

Model Context Protocol через HTTP для интеграции AI ассистентов.

#### MCP Метаданные
**Конечная Точка**: `GET /ext/mcp_http/meta`  
**Аутентификация**: Не требуется

```json
{
  "server": "ordinaut-mcp-http",
  "version": "0.2.0", 
  "capabilities": ["handshake", "list_tools", "invoke", "schema", "sse"]
}
```

#### MCP Рукопожатие
**Конечная Точка**: `POST /ext/mcp_http/handshake`  
**Content-Type**: `application/json`

**Запрос**:
```json
{
  "client": {
    "name": "ChatGPT",
    "version": "1.0"
  }
}
```

**Ответ**:
```json
{
  "server": {
    "name": "ordinaut-mcp-http",
    "version": "0.2.0"
  },
  "session_id": "sess-uuid-5678"
}
```

#### Список Доступных Инструментов
**Конечная Точка**: `GET /ext/mcp_http/tools`

```json
{
  "tools": [
    {
      "name": "create_task",
      "description": "Создать новую запланированную задачу",
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

#### Вызов Инструмента
**Конечная Точка**: `POST /ext/mcp_http/invoke`

**Запрос**:
```json
{
  "tool": "create_task",
  "parameters": {
    "title": "Ежедневный Отчет",
    "schedule": "0 18 * * *"
  }
}
```

**Ответ**:
```json
{
  "success": true,
  "result": {
    "task_id": "uuid-9876",
    "message": "Задача создана успешно"
  }
}
```

### Расширение Demo События

Демонстрирует систему событий Redis Streams.

#### Опубликовать Событие
**Конечная Точка**: `POST /ext/events_demo/publish/{stream}`  
**Content-Type**: `application/json`

**Пример**:
```bash
curl -X POST http://localhost:8080/ext/events_demo/publish/test \\
  -H "Content-Type: application/json" \\
  -d '{"сообщение": "Привет События", "timestamp": "2025-08-26T10:00:00Z"}'
```

**Ответ**:
```json
{
  "success": true,
  "stream": "test",
  "event_id": "1692873600000-0",
  "message": "Событие опубликовано успешно"
}
```

#### Подписка на События (Server-Sent Events)
**Конечная Точка**: `GET /ext/events_demo/subscribe/{stream}`  
**Content-Type**: `text/event-stream`

Устанавливает SSE соединение для получения событий в реальном времени.

**Пример**:
```bash
curl -N http://localhost:8080/ext/events_demo/subscribe/test
```

**Поток Ответа**:
```
data: {"stream": "test", "id": "1692873600000-0", "data": {"сообщение": "Привет События"}}

data: {"stream": "test", "id": "1692873600001-0", "data": {"сообщение": "Другое событие"}}
```

## API Разработки Расширений

### Регистрация Расширений

Расширения обнаруживаются и регистрируются автоматически. Ручной API регистрации не требуется.

**Источники Обнаружения**:
1. Встроенные: директория `ordinaut/extensions/`
2. Окружение: переменная окружения `ORDINAUT_EXT_PATHS`  
3. Entry points: группа Python entry points `ordinaut.plugins`

### Возможности Расширений

Расширения могут запрашивать следующие возможности:

| Возможность | Описание | Доступ API |
|-------------|-----------|------------|
| `ROUTES` | Создание HTTP конечных точек | Монтирование маршрутизатора FastAPI |
| `TOOLS` | Доступ к реестру инструментов | `tool_registry.register_tool()` |
| `EVENTS_PUB` | Публикация событий | `events.publish()` |
| `EVENTS_SUB` | Подписка на события | `events.subscribe()` |
| `BACKGROUND_TASKS` | Долгоработающие процессы | `background.start_task()` |
| `STATIC` | Обслуживание статичных файлов | Автоматическая маршрутизация статичных файлов |

### Объекты Контекста

Расширения получают объекты контекста на основе предоставленных возможностей:

#### Контекст Реестра Инструментов
```python
# Доступно когда предоставлена возможность TOOLS
tool_registry.register_tool(name: str, func: Callable, schema: dict)
tool_registry.list_tools() -> List[ToolInfo]
tool_registry.get_tool(name: str) -> ToolInfo
```

#### Контекст Событий  
```python
# Доступно когда предоставлены EVENTS_PUB или EVENTS_SUB
await events.publish(stream: str, data: dict) -> str
await events.subscribe(pattern: str, handler: Callable) -> None
await events.unsubscribe(pattern: str) -> None
```

#### Контекст Фоновых Задач
```python
# Доступно когда предоставлена возможность BACKGROUND_TASKS  
await background.start_task(name: str, coro: Coroutine) -> None
await background.stop_task(name: str) -> None
background.list_tasks() -> List[TaskInfo]
```

## Аутентификация и Авторизация

### Контроль Доступа на Основе Областей

Расширения могут быть защищены авторизацией на основе областей:

**Конфигурация**:
```bash
export ORDINAUT_REQUIRE_SCOPES=true
```

**Заголовки Запроса**:
```bash
curl -H "X-Scopes: ext:мое_расширение:routes" \\
     http://localhost:8080/ext/мое_расширение/защищенный
```

**Шаблон Требуемой Области**: `ext:{extension_id}:routes`

### Аутентификация JWT Токена

Когда аутентификация JWT включена, расширения наследуют те же требования аутентификации что и основной API.

**Заголовки Запроса**:
```bash
curl -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \\
     http://localhost:8080/ext/мое_расширение/безопасный
```

## Ответы Ошибок

Все конечные точки расширений следуют согласованным форматам ответов ошибок:

### 400 Неверный Запрос
```json
{
  "error": "bad_request",
  "message": "Неверные параметры запроса",
  "details": {
    "field": "schedule_expr", 
    "issue": "Неверное cron выражение"
  }
}
```

### 401 Неавторизован
```json
{
  "error": "unauthorized",
  "message": "Требуется аутентификация",
  "details": {
    "required_scopes": ["ext:мое_расширение:routes"]
  }
}
```

### 403 Запрещено  
```json
{
  "error": "forbidden",
  "message": "Недостаточно разрешений",
  "details": {
    "required_capability": "TOOLS",
    "granted_capabilities": ["ROUTES"]
  }
}
```

### 404 Не Найдено
```json
{
  "error": "not_found",
  "message": "Расширение не найдено",
  "details": {
    "extension_id": "несуществующее_расширение"
  }
}
```

### 500 Внутренняя Ошибка Сервера
```json
{
  "error": "internal_error",
  "message": "Выполнение расширения не удалось",
  "details": {
    "extension_id": "мое_расширение",
    "error_type": "ImportError",
    "traceback": "..."
  }
}
```

## Ограничение Скорости

Конечные точки расширений соблюдают ту же конфигурацию ограничения скорости что и основной API:

**Заголовки**:
- `X-RateLimit-Limit`: Лимит запросов на окно
- `X-RateLimit-Remaining`: Оставшиеся запросы в текущем окне
- `X-RateLimit-Reset`: Время сброса окна

**429 Слишком Много Запросов**:
```json
{
  "error": "rate_limit_exceeded",
  "message": "Превышен лимит скорости", 
  "details": {
    "limit": 100,
    "window": "60s",
    "reset_at": "2025-08-26T10:01:00Z"
  }
}
```

## Проверки Здоровья

Расширения могут реализовать конечные точки проверки здоровья для мониторинга:

**Соглашение**: `GET /ext/{extension_id}/health`

**Стандартный Ответ**:
```json
{
  "status": "здоровый",
  "timestamp": "2025-08-26T10:00:00Z", 
  "version": "1.0.0",
  "checks": {
    "database": "здоровый",
    "external_api": "здоровый", 
    "background_tasks": "здоровый"
  }
}
```

## Поддержка WebSocket

Расширения могут реализовать WebSocket конечные точки для общения в реальном времени:

**Шаблон Конечной Точки**: `WS /ext/{extension_id}/ws/{path}`

**Пример Реализации**:
```python
from fastapi import WebSocket

@router.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Обработка WebSocket общения
            data = await websocket.receive_json()
            response = await обработать_websocket_данные(data)
            await websocket.send_json(response)
    except WebSocketDisconnect:
        # Обработка отключения клиента
        pass
```

## Метрики Расширений

Все расширения автоматически получают базовый сбор метрик:

**Доступные Метрики**:
- `extension_requests_total{extension, endpoint, method, status}`
- `extension_request_duration_seconds{extension, endpoint, method}`
- `extension_errors_total{extension, endpoint, error_type}`
- `extension_active_connections{extension, endpoint}`

**Доступ через Расширение Observability**:
```bash
curl http://localhost:8080/ext/observability/metrics | grep extension
```

Данный справочник API предоставляет полную документацию для взаимодействия с системой расширений Ordinaut, позволяя разработчикам создавать мощные расширения и эффективно интегрировать внешние системы.