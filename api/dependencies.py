"""
FastAPI dependencies for database connections, authentication, and Redis.

Provides reusable dependencies that handle database sessions, agent authentication,
and Redis connections with proper cleanup and error handling.
"""

import os
import redis
from typing import Generator, Optional
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from .models import Agent

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://orchestrator:orchestrator_pw@localhost:5432/orchestrator")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create database engine with appropriate settings for database type
if DATABASE_URL.startswith("sqlite"):
    # SQLite-specific settings
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        future=True,
        connect_args={"check_same_thread": False}  # Allow SQLite across threads
    )
else:
    # PostgreSQL settings
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=3600,   # Recycle connections every hour
        pool_size=20,        # Connection pool size
        max_overflow=40,     # Max overflow connections
        future=True          # Use SQLAlchemy 2.0 style
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Redis client setup (optional for development)
redis_client = None
try:
    if REDIS_URL and REDIS_URL not in ("memory://", "disabled://"):
        redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=False,  # Keep binary responses for stream IDs
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
except Exception as e:
    print(f"Warning: Redis not available: {e}")
    redis_client = None


def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides database sessions with automatic cleanup.
    
    Yields a SQLAlchemy session and ensures proper cleanup on completion
    or exception. All database operations should use this dependency.
    """
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


def get_redis() -> redis.Redis:
    """
    Dependency that provides Redis client access.
    
    Returns the configured Redis client for event streaming and caching.
    Connection pooling and error handling are managed automatically.
    """
    return redis_client


async def get_current_agent(
    authorization: str = Header(..., description="Bearer token for agent authentication"),
    db: Session = Depends(get_db)
) -> Agent:
    """
    Dependency that extracts and validates the current agent from auth header.
    
    Expects Authorization header in format: "Bearer <agent-id>"
    Returns the authenticated Agent model or raises 401/403 errors.
    
    For production, this should be replaced with proper JWT validation
    or integration with an authentication service.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <agent-id>'",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        # Extract agent ID from Bearer token
        # In production, this would validate a JWT token instead
        agent_id = authorization[7:]  # Remove "Bearer " prefix
        
        # Look up agent
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Agent {agent_id} not found or invalid",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return agent
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid agent ID format: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error during authentication"
        )


async def check_agent_scope(
    required_scope: str,
    current_agent: Agent = Depends(get_current_agent)
) -> Agent:
    """
    Dependency that checks if the current agent has a required scope.
    
    Used for endpoints that need specific permissions like tool execution
    or administrative operations. Raises 403 if scope is missing.
    """
    if required_scope not in current_agent.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent '{current_agent.name}' lacks required scope: {required_scope}"
        )
    
    return current_agent


def require_scopes(*required_scopes: str):
    """
    Decorator factory for creating scope-checking dependencies.
    
    Usage:
        @router.get("/admin/endpoint")
        async def admin_endpoint(agent: Agent = Depends(require_scopes("admin", "read"))):
            # Endpoint logic here
    """
    async def scope_checker(current_agent: Agent = Depends(get_current_agent)) -> Agent:
        missing_scopes = [scope for scope in required_scopes if scope not in current_agent.scopes]
        
        if missing_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Agent '{current_agent.name}' lacks required scopes: {', '.join(missing_scopes)}"
            )
        
        return current_agent
    
    return scope_checker


# Health check dependencies
async def check_database_health() -> bool:
    """Check if database connection is healthy."""
    try:
        # For SQLite, just check if we can create an engine connection
        if DATABASE_URL.startswith("sqlite"):
            # For SQLite, check file existence and basic connection
            import sqlite3
            db_file = DATABASE_URL.replace("sqlite:///", "")
            conn = sqlite3.connect(db_file, timeout=5.0)
            conn.execute("SELECT 1")
            conn.close()
            return True
        else:
            # For PostgreSQL, use SQLAlchemy session
            db = SessionLocal()
            try:
                db.execute("SELECT 1")
                return True
            finally:
                db.close()
    except Exception as e:
        print(f"Database health check failed: {e}")
        return False


async def check_redis_health() -> bool:
    """Check if Redis connection is healthy."""
    try:
        if redis_client is None:
            return False  # Redis not configured
        redis_client.ping()
        return True
    except Exception:
        return False


# Utility functions for common operations
def get_agent_by_id(agent_id: str, db: Session) -> Optional[Agent]:
    """Get agent by ID with error handling."""
    try:
        return db.query(Agent).filter(Agent.id == agent_id).first()
    except SQLAlchemyError:
        return None


def validate_agent_access(agent: Agent, resource_owner_id: str) -> bool:
    """
    Validate if agent has access to a resource.
    
    This is a basic implementation - in production you'd have more
    sophisticated access control rules based on agent scopes and roles.
    """
    # For now, agents can access resources they created
    # Plus system-level agents can access everything
    return str(agent.id) == resource_owner_id or "admin" in agent.scopes