# Authentication

All API endpoints (except for public health checks) require Agent-based authentication using a **Bearer Token**.

## Bearer Token Authentication

You must include an `Authorization` header with your agent's token in every request. The token should be prefixed with `Bearer `.

```bash
curl -H "Authorization: Bearer 00000000-0000-0000-0000-000000000001" \
     https://api.orchestrator.example.com/v1/tasks
```

## Agent Scopes & Permissions

Authentication is tied to a specific **Agent**, which has a set of **scopes** that grant it permission to perform certain actions. For example, an agent might have the scope `tasks:create` but not `tasks:cancel`.

If an agent attempts an action outside of its allowed scopes, the API will return a `403 Forbidden` error.

### Common Scopes

- `tasks:create`, `tasks:read`, `tasks:update`, `tasks:delete`
- `runs:read`
- `events:publish`
- `admin` (grants access to all operations)

## Error Responses

- `401 Unauthorized`: Returned if the `Authorization` header is missing or the token is invalid, malformed, or expired.
- `403 Forbidden`: Returned if the agent's token is valid but it lacks the required scopes for the requested operation.

```