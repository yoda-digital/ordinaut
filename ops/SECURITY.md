# Ordinaut - Security Implementation

## Overview

The Ordinaut includes comprehensive security infrastructure designed for production deployment with JWT authentication, rate limiting, threat detection, and audit logging.

## Security Features

### 1. JWT Authentication System

**Components:**
- JWT token generation with configurable expiration
- Access tokens (short-lived) and refresh tokens (long-lived)
- Token revocation support with blacklist management
- Scope-based authorization with fine-grained permissions

**Configuration:**
```bash
JWT_SECRET_KEY=your-256-bit-secret-key-here
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
```

**Usage Example:**
```bash
# 1. Authenticate agent and get tokens
curl -X POST http://localhost:8080/agents/auth/token \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "your-agent-uuid"}'

# 2. Use access token for API calls
curl -H "Authorization: Bearer <access-token>" \
  http://localhost:8080/tasks

# 3. Refresh tokens when needed
curl -X POST http://localhost:8080/agents/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh-token>"}'
```

### 2. Rate Limiting

**Features:**
- Redis-based distributed rate limiting
- Per-IP and per-endpoint limits
- Configurable rate windows and thresholds
- Automatic blocking of abusive clients

**Configuration:**
```bash
RATE_LIMIT_ENABLED=true
MAX_REQUESTS_PER_MINUTE=60
MAX_REQUESTS_PER_HOUR=1000
REDIS_URL=redis://redis:6379/1
```

**Default Limits:**
- 60 requests per minute per IP
- 1000 requests per hour per IP
- Custom limits for sensitive endpoints

### 3. Request Validation & Threat Detection

**Security Middleware:**
- Request size validation (default 10MB limit)
- Content type validation
- Suspicious pattern detection (XSS, SQL injection, path traversal)
- User-Agent validation
- IP-based threat detection and blocking

**Threat Detection Patterns:**
- Script injection attempts (`<script>`, `javascript:`)
- SQL injection patterns (`UNION SELECT`, `DROP TABLE`)
- Path traversal attempts (`../`, `%2f`)
- Known scanner signatures (sqlmap, nikto, etc.)

**Configuration:**
```bash
MAX_REQUEST_SIZE=10485760  # 10MB
BLOCK_SUSPICIOUS_PATTERNS=true
```

### 4. Security Headers

**Automatic Security Headers:**
```http
X-XSS-Protection: 1; mode=block
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Strict-Transport-Security: max-age=31536000; includeSubDomains
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### 5. Audit Logging

**Security Events Logged:**
- Authentication attempts (success/failure)
- Token generation and revocation
- Rate limit violations
- Blocked requests and threats detected
- Administrative actions (agent creation, deletion)

**Log Format:**
```json
{
  "timestamp": "2024-01-10T10:00:00Z",
  "level": "WARNING",
  "event_type": "authentication_failed",
  "agent_id": "uuid",
  "client_ip": "192.168.1.100",
  "user_agent": "curl/7.81.0",
  "details": {"reason": "invalid_credentials"}
}
```

### 6. Metrics & Monitoring

**Security Metrics (Prometheus):**
- `orchestrator_security_events_total` - Security events by type/severity
- `orchestrator_authentication_attempts_total` - Auth attempts by result
- `orchestrator_jwt_tokens_issued_total` - Token issuance by agent/type
- `orchestrator_jwt_tokens_revoked_total` - Token revocations by reason
- `orchestrator_rate_limit_violations_total` - Rate limit violations
- `orchestrator_blocked_requests_total` - Blocked requests by reason

## Production Security Checklist

### Required Environment Variables

```bash
# CRITICAL: Change default JWT secret
JWT_SECRET_KEY=<256-bit-random-key>

# Database credentials (use strong passwords)
POSTGRES_PASSWORD=<strong-password>

# Redis authentication (if enabled)
REDIS_URL=redis://:password@redis:6379/0

# Rate limiting configuration
RATE_LIMIT_ENABLED=true
MAX_REQUESTS_PER_MINUTE=60
MAX_REQUESTS_PER_HOUR=1000

# Request size limits
MAX_REQUEST_SIZE=10485760
```

### Network Security

1. **Use HTTPS Only:**
   ```yaml
   # docker-compose.yml
   environment:
     - FORCE_HTTPS=true
   ```

2. **Restrict Network Access:**
   ```yaml
   # Only expose API port publicly
   ports:
     - "443:8080"  # HTTPS only
   # Keep PostgreSQL and Redis internal
   ```

3. **Use Docker Secrets:**
   ```yaml
   secrets:
     jwt_secret:
       file: ./secrets/jwt_secret.txt
   ```

### Monitoring & Alerting

1. **Security Event Alerts:**
   ```yaml
   # Grafana alerts
   - alert: HighAuthenticationFailures
     expr: rate(orchestrator_authentication_attempts_total{result="failed"}[5m]) > 10
     
   - alert: SuspiciousActivity
     expr: rate(orchestrator_security_events_total{severity="high"}[1m]) > 1
   ```

2. **Log Analysis:**
   ```bash
   # Monitor failed authentication attempts
   grep "authentication_failed" /var/log/orchestrator/*.log
   
   # Check for blocked requests
   grep "request_blocked" /var/log/orchestrator/*.log
   ```

### Backup & Recovery

1. **Token Revocation List:**
   - Backup revoked tokens list from Redis
   - Restore during disaster recovery

2. **Agent Credentials:**
   - Secure storage of agent credential hashes
   - Regular rotation procedures

## Security Best Practices

### Agent Management

1. **Principle of Least Privilege:**
   ```python
   # Create agents with minimal required scopes
   {
     "name": "email-agent",
     "scopes": ["email.read", "email.send"]  # Not "admin"
   }
   ```

2. **Regular Credential Rotation:**
   ```bash
   # Generate new credentials periodically
   curl -X POST http://localhost:8080/agents/{agent_id}/credentials \
     -H "Authorization: Bearer <admin-token>"
   ```

3. **Monitor Agent Activity:**
   - Track which agents create tasks
   - Monitor unusual scope usage patterns
   - Alert on dormant agent sudden activity

### API Security

1. **Input Validation:**
   - All inputs validated at API boundary
   - JSON Schema validation for payloads
   - Sanitization of user-provided data

2. **Error Handling:**
   - Generic error messages to prevent information leakage
   - Detailed logging for debugging (server-side only)
   - Rate limit error responses

3. **CORS Configuration:**
   ```python
   # Restrict origins in production
   allow_origins=["https://yourdomain.com"]
   allow_credentials=True
   ```

### Database Security

1. **Connection Security:**
   ```bash
   # Use SSL/TLS connections
   DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require
   ```

2. **Query Safety:**
   - All database queries use parameterized statements
   - SKIP LOCKED prevents race conditions
   - Regular security updates for PostgreSQL

### Infrastructure Security

1. **Container Security:**
   ```dockerfile
   # Run as non-root user
   USER orchestrator:orchestrator
   
   # Read-only filesystem where possible
   --read-only
   ```

2. **Network Isolation:**
   ```yaml
   networks:
     frontend:
       # API only
     backend:
       # Database, Redis, internal services
   ```

## Incident Response

### Security Event Response

1. **High Authentication Failures:**
   - Investigate source IPs
   - Temporarily block suspicious sources
   - Review agent credential security

2. **Blocked Malicious Requests:**
   - Analyze attack patterns
   - Update threat detection rules
   - Consider permanent IP blocks

3. **Unauthorized Access:**
   - Revoke compromised tokens immediately
   - Audit affected resources
   - Reset credentials for compromised agents

### Security Updates

1. **Dependency Updates:**
   ```bash
   # Regular security updates
   pip-audit  # Check for known vulnerabilities
   docker scan  # Container vulnerability scanning
   ```

2. **Configuration Reviews:**
   - Monthly security configuration reviews
   - Update threat detection patterns
   - Review and rotate secrets

## Testing Security

### Penetration Testing

1. **Authentication Testing:**
   ```bash
   # Test token validation
   curl -H "Authorization: Bearer invalid-token" http://localhost:8080/tasks
   
   # Test rate limiting
   for i in {1..100}; do curl http://localhost:8080/health; done
   ```

2. **Input Validation Testing:**
   ```bash
   # Test XSS protection
   curl -X POST http://localhost:8080/tasks \
     -d '{"title": "<script>alert(1)</script>"}'
   
   # Test SQL injection protection
   curl -X GET "http://localhost:8080/tasks?filter='; DROP TABLE tasks; --"
   ```

### Security Automation

1. **Automated Security Tests:**
   ```python
   # Include in CI/CD pipeline
   def test_authentication_required():
       response = client.get("/tasks")
       assert response.status_code == 401
   
   def test_rate_limiting():
       # Rapid requests should be limited
       responses = [client.get("/health") for _ in range(100)]
       assert any(r.status_code == 429 for r in responses)
   ```

2. **Security Monitoring:**
   ```bash
   # Automated threat detection
   docker run --name security-monitor \
     -e ORCHESTRATOR_API=http://api:8080 \
     security-monitor:latest
   ```

## Compliance & Standards

### Data Protection

1. **Personal Data Handling:**
   - No personal data stored without encryption
   - Agent credentials hashed with bcrypt
   - Audit logs retention policy (90 days)

2. **Access Control:**
   - Role-based access with scopes
   - Audit trail for all administrative actions
   - Regular access reviews

### Security Standards Compliance

- **OWASP Top 10:** All major vulnerabilities addressed
- **REST API Security:** Authentication, authorization, input validation
- **Container Security:** CIS Docker Benchmark compliance
- **Network Security:** TLS 1.3, secure headers, CORS

## Conclusion

The Ordinaut provides enterprise-grade security suitable for production deployment. Regular monitoring, updates, and security reviews ensure continued protection against evolving threats.

For security questions or incident reporting, review logs and metrics through the monitoring stack deployed with the system.