# Authentication

!!! danger "Critical Security Warning"
    The authentication system is currently **NOT SECURE** for production use. A security audit identified two critical vulnerabilities:

    1.  **Authentication Bypass:** The system currently authenticates agents based on their ID alone, without validating any secret or password. This means anyone who knows an agent's ID can impersonate them.
    2.  **Default JWT Secret:** The system uses a default, hardcoded JWT secret key if a secure one is not provided via the `JWT_SECRET_KEY` environment variable. This allows attackers to forge valid authentication tokens.

    **Do not deploy this system in a production environment until these issues are fixed.**

All API endpoints (except for public health checks) require Agent-based authentication using a **Bearer Token**.

## Bearer Token Authentication

The intended authentication mechanism is via JWT (JSON Web Tokens). You must include an `Authorization` header with your agent's token in every request. The token should be prefixed with `Bearer `.

```bash
curl -H "Authorization: Bearer <your-jwt-access-token>" \
     https://api.ordinaut.example.com/v1/tasks
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
