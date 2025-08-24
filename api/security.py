"""
Security Middleware and Validation for Ordinaut.

Provides comprehensive security middleware including rate limiting,
request validation, threat protection, and security headers.
"""

import os
import re
import time
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque

from fastapi import Request, Response, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import redis
from pydantic import BaseModel, Field, validator

from .auth import jwt_manager, TokenData
from .models import Agent
from observability.logging import api_logger
from observability.metrics import orchestrator_metrics


# Security configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")
MAX_REQUEST_SIZE = int(os.getenv("MAX_REQUEST_SIZE", "10485760"))  # 10MB
MAX_REQUESTS_PER_MINUTE = int(os.getenv("MAX_REQUESTS_PER_MINUTE", "60"))
MAX_REQUESTS_PER_HOUR = int(os.getenv("MAX_REQUESTS_PER_HOUR", "1000"))

# Security patterns
SUSPICIOUS_PATTERNS = [
    re.compile(r'<script[^>]*>', re.IGNORECASE),
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),
    re.compile(r'union\s+select', re.IGNORECASE),
    re.compile(r'drop\s+table', re.IGNORECASE),
    re.compile(r'insert\s+into', re.IGNORECASE),
    re.compile(r'delete\s+from', re.IGNORECASE),
    re.compile(r'\.\./|\.\.\%2f', re.IGNORECASE),
    re.compile(r'%00', re.IGNORECASE),
]

# Logger
logger = api_logger


@dataclass
class SecurityEvent:
    """Security event for logging and monitoring."""
    event_type: str
    severity: str  # "low", "medium", "high", "critical"
    source_ip: str
    user_agent: Optional[str]
    request_path: str
    request_method: str
    agent_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SecurityConfig(BaseModel):
    """Security configuration model."""
    rate_limiting_enabled: bool = Field(default=True)
    max_request_size: int = Field(default=10485760)  # 10MB
    max_requests_per_minute: int = Field(default=60)
    max_requests_per_hour: int = Field(default=1000)
    block_suspicious_patterns: bool = Field(default=True)
    require_user_agent: bool = Field(default=False)
    allowed_origins: List[str] = Field(default_factory=list)
    
    @validator('max_request_size')
    def validate_request_size(cls, v):
        if v < 1024 or v > 100 * 1024 * 1024:  # 1KB to 100MB
            raise ValueError('Request size must be between 1KB and 100MB')
        return v


class ThreatDetector:
    """
    Advanced threat detection and prevention system.
    
    Analyzes requests for malicious patterns, suspicious behavior,
    and potential security threats with automatic blocking.
    """
    
    def __init__(self):
        self.suspicious_ips: Dict[str, List[datetime]] = defaultdict(list)
        self.blocked_ips: Dict[str, datetime] = {}
        self.block_duration = timedelta(hours=1)
        
    def is_suspicious_request(self, request: Request) -> tuple[bool, str]:
        """
        Analyze request for suspicious patterns.
        
        Returns (is_suspicious, reason) tuple for threat assessment.
        """
        # Check URL path
        path = str(request.url.path)
        for pattern in SUSPICIOUS_PATTERNS:
            if pattern.search(path):
                return True, f"Suspicious pattern in URL: {pattern.pattern}"
        
        # Check query parameters
        query_params = str(request.url.query)
        for pattern in SUSPICIOUS_PATTERNS:
            if pattern.search(query_params):
                return True, f"Suspicious pattern in query: {pattern.pattern}"
        
        # Check headers
        user_agent = request.headers.get("user-agent", "").lower()
        if not user_agent:
            return True, "Missing User-Agent header"
        
        # Common bot/scanner patterns
        suspicious_agents = ['sqlmap', 'nikto', 'nmap', 'masscan', 'zgrab']
        if any(agent in user_agent for agent in suspicious_agents):
            return True, f"Suspicious User-Agent: {user_agent}"
        
        # Check for unusual header combinations
        if request.headers.get("x-real-ip") and request.headers.get("x-forwarded-for"):
            # Potential IP spoofing attempt
            return True, "Potential IP spoofing detected"
        
        return False, ""
    
    def is_ip_blocked(self, ip: str) -> bool:
        """Check if IP is currently blocked."""
        if ip in self.blocked_ips:
            if datetime.now(timezone.utc) < self.blocked_ips[ip]:
                return True
            else:
                # Block expired, remove it
                del self.blocked_ips[ip]
        return False
    
    def record_suspicious_activity(self, ip: str, reason: str):
        """Record suspicious activity and potentially block IP."""
        now = datetime.now(timezone.utc)
        
        # Clean old records (older than 1 hour)
        cutoff = now - timedelta(hours=1)
        self.suspicious_ips[ip] = [
            ts for ts in self.suspicious_ips[ip] if ts > cutoff
        ]
        
        # Add new suspicious activity
        self.suspicious_ips[ip].append(now)
        
        # Block IP if too many suspicious activities
        if len(self.suspicious_ips[ip]) >= 5:  # 5 suspicious activities in 1 hour
            self.blocked_ips[ip] = now + self.block_duration
            logger.warning(f"IP blocked due to suspicious activity", ip=ip, reason=reason)
            
            # Record security event
            self._log_security_event(SecurityEvent(
                event_type="ip_blocked",
                severity="high",
                source_ip=ip,
                user_agent=None,
                request_path="",
                request_method="",
                details={"reason": reason, "activity_count": len(self.suspicious_ips[ip])}
            ))
    
    def _log_security_event(self, event: SecurityEvent):
        """Log security event for monitoring and alerting."""
        logger.warning(
            f"Security event: {event.event_type}",
            event_type=event.event_type,
            severity=event.severity,
            source_ip=event.source_ip,
            user_agent=event.user_agent,
            request_path=event.request_path,
            agent_id=event.agent_id,
            details=event.details
        )
        
        # Record security metric
        orchestrator_metrics.record_security_event(
            event_type=event.event_type,
            severity=event.severity
        )


class RequestValidator:
    """
    Comprehensive request validation and sanitization.
    
    Validates request size, content type, structure, and content
    with automatic sanitization and threat detection.
    """
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.threat_detector = ThreatDetector()
    
    async def validate_request(self, request: Request) -> tuple[bool, Optional[str]]:
        """
        Comprehensive request validation.
        
        Returns (is_valid, error_message) for request assessment.
        """
        # Get client IP
        client_ip = get_remote_address(request)
        
        # Check if IP is blocked
        if self.threat_detector.is_ip_blocked(client_ip):
            return False, "IP address is temporarily blocked due to suspicious activity"
        
        # Check request size
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.config.max_request_size:
                    return False, f"Request too large: {size} bytes > {self.config.max_request_size} bytes"
            except ValueError:
                return False, "Invalid Content-Length header"
        
        # Check for suspicious patterns
        if self.config.block_suspicious_patterns:
            is_suspicious, reason = self.threat_detector.is_suspicious_request(request)
            if is_suspicious:
                self.threat_detector.record_suspicious_activity(client_ip, reason)
                return False, f"Request blocked: {reason}"
        
        # Validate content type for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            if content_type and not self._is_allowed_content_type(content_type):
                return False, f"Unsupported content type: {content_type}"
        
        return True, None
    
    def _is_allowed_content_type(self, content_type: str) -> bool:
        """Check if content type is allowed."""
        allowed_types = [
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
            "text/plain"
        ]
        
        content_type_lower = content_type.lower().split(';')[0].strip()
        return content_type_lower in allowed_types


class SecurityHeaders:
    """
    Security headers middleware for enhanced protection.
    
    Adds comprehensive security headers to prevent common
    web vulnerabilities and enhance client security.
    """
    
    @staticmethod
    def add_security_headers(response: Response) -> Response:
        """Add security headers to response."""
        security_headers = {
            # Prevent XSS attacks
            "X-XSS-Protection": "1; mode=block",
            
            # Prevent content type sniffing
            "X-Content-Type-Options": "nosniff",
            
            # Prevent clickjacking
            "X-Frame-Options": "DENY",
            
            # Force HTTPS (in production)
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            
            # Referrer policy
            "Referrer-Policy": "strict-origin-when-cross-origin",
            
            # Content Security Policy - Allow Swagger UI CDN resources
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net; "
                "connect-src 'self'"
            ),
            
            # Permissions policy
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            
            # Server identification
            "Server": "Personal-Agent-Orchestrator/1.0"
        }
        
        for header, value in security_headers.items():
            response.headers[header] = value
        
        return response


# Rate limiter setup
def get_limiter():
    """Create rate limiter instance."""
    if RATE_LIMIT_ENABLED:
        try:
            # Use Redis for distributed rate limiting
            redis_client = redis.from_url(RATE_LIMIT_REDIS_URL)
            return Limiter(
                key_func=get_remote_address,
                storage_uri=RATE_LIMIT_REDIS_URL,
                default_limits=[f"{MAX_REQUESTS_PER_MINUTE}/minute", f"{MAX_REQUESTS_PER_HOUR}/hour"]
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Redis rate limiter: {e}")
            # Fallback to in-memory rate limiting
            return Limiter(
                key_func=get_remote_address,
                default_limits=[f"{MAX_REQUESTS_PER_MINUTE}/minute", f"{MAX_REQUESTS_PER_HOUR}/hour"]
            )
    return None


# Enhanced Bearer token security
security_scheme = HTTPBearer(
    scheme_name="AgentJWT",
    description="JWT token for agent authentication (format: Bearer <jwt-token>)"
)


async def get_current_agent_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
) -> Agent:
    """
    JWT-based agent authentication dependency.
    
    Validates JWT token and returns authenticated agent with
    comprehensive security logging and monitoring.
    """
    from .dependencies import get_db
    
    token = credentials.credentials
    
    try:
        # Verify JWT token
        token_data = jwt_manager.verify_token(token, token_type="access")
        
        # Get database session
        db = next(get_db())
        
        try:
            # Get agent from database
            agent = db.query(Agent).filter(Agent.id == token_data.agent_id).first()
            
            if not agent:
                logger.warning(f"JWT authentication failed: agent not found", agent_id=token_data.agent_id)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Agent not found or inactive",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Log successful authentication
            logger.info(
                f"JWT authentication successful",
                agent_id=str(agent.id),
                agent_name=agent.name,
                scopes=agent.scopes,
                token_expires=token_data.expires_at.isoformat()
            )
            
            return agent
            
        finally:
            db.close()
            
    except HTTPException:
        # Re-raise HTTP exceptions (already logged in jwt_manager)
        raise
    except Exception as e:
        logger.error(f"JWT authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )


def require_scopes_jwt(*required_scopes: str):
    """
    JWT-based scope requirement decorator.
    
    Creates a dependency that validates JWT token and required scopes
    with comprehensive security logging.
    """
    async def scope_checker(
        credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
    ) -> Agent:
        # First authenticate the agent
        agent = await get_current_agent_jwt(credentials)
        
        # Verify token and get scope data
        token_data = jwt_manager.verify_token(credentials.credentials, token_type="access")
        
        # Check required scopes
        if not jwt_manager.validate_scope_access(token_data, list(required_scopes)):
            missing_scopes = set(required_scopes) - set(token_data.scopes)
            
            logger.warning(
                f"Scope access denied",
                agent_id=str(agent.id),
                required_scopes=list(required_scopes),
                agent_scopes=token_data.scopes,
                missing_scopes=list(missing_scopes)
            )
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Missing scopes: {', '.join(missing_scopes)}"
            )
        
        logger.debug(
            f"Scope access granted",
            agent_id=str(agent.id),
            required_scopes=list(required_scopes),
            agent_scopes=token_data.scopes
        )
        
        return agent
    
    return scope_checker


# Security middleware components
security_config = SecurityConfig(
    rate_limiting_enabled=RATE_LIMIT_ENABLED,
    max_request_size=MAX_REQUEST_SIZE,
    max_requests_per_minute=MAX_REQUESTS_PER_MINUTE,
    max_requests_per_hour=MAX_REQUESTS_PER_HOUR
)

request_validator = RequestValidator(security_config)
security_headers = SecurityHeaders()
limiter = get_limiter()


async def security_middleware(request: Request, call_next: Callable) -> Response:
    """
    Comprehensive security middleware.
    
    Performs request validation, threat detection, and security
    header injection with detailed logging and monitoring.
    """
    start_time = time.time()
    client_ip = get_remote_address(request)
    user_agent = request.headers.get("user-agent", "")
    
    # Validate request
    is_valid, error_message = await request_validator.validate_request(request)
    if not is_valid:
        logger.warning(
            f"Request blocked by security middleware",
            client_ip=client_ip,
            user_agent=user_agent,
            path=request.url.path,
            method=request.method,
            reason=error_message
        )
        
        # Record security event
        orchestrator_metrics.record_security_event(
            event_type="request_blocked",
            severity="medium"
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )
    
    # Process request
    try:
        response = await call_next(request)
        
        # Add security headers
        response = security_headers.add_security_headers(response)
        
        # Log successful request
        duration = time.time() - start_time
        logger.debug(
            f"Security middleware: request processed",
            client_ip=client_ip,
            path=request.url.path,
            method=request.method,
            status_code=getattr(response, 'status_code', 200),
            duration_ms=duration * 1000
        )
        
        return response
        
    except Exception as e:
        # Log security-related errors
        duration = time.time() - start_time
        logger.error(
            f"Security middleware: request failed",
            client_ip=client_ip,
            path=request.url.path,
            method=request.method,
            duration_ms=duration * 1000,
            error=str(e)
        )
        raise


# Rate limit handler
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Custom rate limit exceeded handler."""
    client_ip = get_remote_address(request)
    
    logger.warning(
        f"Rate limit exceeded",
        client_ip=client_ip,
        path=request.url.path,
        method=request.method,
        limit=str(exc.detail)
    )
    
    # Record security event
    orchestrator_metrics.record_security_event(
        event_type="rate_limit_exceeded",
        severity="medium"
    )
    
    response = JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "RateLimitExceeded",
            "message": "Too many requests",
            "details": {"limit": str(exc.detail)},
            "retry_after": getattr(exc, 'retry_after', 60)
        }
    )
    
    return security_headers.add_security_headers(response)