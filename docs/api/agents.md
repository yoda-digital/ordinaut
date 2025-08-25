# Agents API

The Agents API is used to manage the agents that interact with the Ordinaut system. Most of these endpoints require `admin` scope for access.

!!! note
    Please review the [Authentication](./authentication.md) guide for critical information about the current state of the authentication system before use.

---

## `POST /agents`

Creates a new agent. Requires `admin` scope.

**Request Body:**

| Field         | Type         | Required | Description                               |
|:--------------|:-------------|:---------|:------------------------------------------|
| `name`        | string       | Yes      | A unique name for the agent.              |
| `scopes`      | array[string]| Yes      | A list of permission scopes for the agent.|
| `webhook_url` | string       | No       | An optional webhook URL for notifications.|

**Response (`201 Created`):**

Returns the newly created `AgentResponse` object.

---

## `GET /agents`

Lists all agents. Requires `admin` scope.

**Query Parameters:**
- `name_filter`: (Optional) Filter by agent name.
- `scope_filter`: (Optional) Filter by agents that have a specific scope.
- `limit`: (Optional) Number of results to return (default: 50).
- `offset`: (Optional) Pagination offset.

**Response:**

Returns a list of `AgentResponse` objects.

---

## `GET /agents/{agent_id}`

Retrieves a specific agent by its UUID. Requires `admin` scope.

**Response:**

Returns a single `AgentResponse` object.

---

## `PUT /agents/{agent_id}`

Updates an existing agent. Requires `admin` scope.

**Request Body:**

The request body can contain `name`, `scopes`, and `webhook_url`, all of which are optional.

---

## `DELETE /agents/{agent_id}`

Deletes an agent. Requires `admin` scope.

---

## Authentication Endpoints

These endpoints are used to authenticate an agent and manage its tokens.

### `POST /agents/auth/token`

Authenticates an agent using its credentials and returns JWT access and refresh tokens.

**Request Body:**

| Field          | Type   | Required | Description                         |
|:---------------|:-------|:---------|:------------------------------------|
| `agent_id`     | string | Yes      | The agent's unique identifier (UUID).|
| `agent_secret` | string | No       | The agent's secret or password.    |

**Response:**

Returns a `TokenResponse` object containing the `access_token` and `refresh_token`.

### `POST /agents/auth/refresh`

Refreshes an access token using a valid refresh token.

### `POST /agents/auth/revoke`

Revokes a token, making it invalid for future use.

### `POST /agents/{agent_id}/credentials`

Creates or resets the authentication credentials for an agent. Requires `admin` scope.
