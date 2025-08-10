#!/usr/bin/env python3
"""
Security Fixes Demonstration for Ordinaut.

This script demonstrates the critical security vulnerabilities found in the audit
and provides example fixes for production deployment.
"""

import os
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any

def generate_secure_jwt_secret() -> str:
    """Generate a cryptographically secure JWT secret key."""
    # Generate 32 random bytes and encode as hex (64 character string)
    secret = secrets.token_hex(32)
    print(f"Generated secure JWT secret: {secret}")
    print(f"Add to environment: export JWT_SECRET_KEY='{secret}'")
    return secret

def demonstrate_authentication_vulnerability():
    """Demonstrate the current authentication bypass vulnerability."""
    print("\n=== CRITICAL VULNERABILITY DEMONSTRATION ===")
    print("Current authentication implementation:")
    
    code_snippet = '''
def authenticate_agent(self, credentials: AgentCredentials, db: Session) -> Optional[Agent]:
    agent = db.query(Agent).filter(Agent.id == credentials.agent_id).first()
    if not agent:
        return None
    
    # TODO: In production, validate agent_secret against stored hash
    # For now, we trust the agent ID is sufficient authentication
    return agent  # ❌ CRITICAL: Returns agent without credential verification
'''
    
    print(code_snippet)
    print("❌ ISSUE: Anyone with a known agent ID can authenticate without credentials!")
    print("❌ IMPACT: Complete authentication bypass")

def demonstrate_secure_authentication():
    """Show how to implement secure authentication."""
    print("\n=== SECURE AUTHENTICATION FIX ===")
    
    secure_code = '''
def authenticate_agent(self, credentials: AgentCredentials, db: Session) -> Optional[Agent]:
    """Secure authentication with credential verification."""
    
    # 1. Get agent by ID
    agent = db.query(Agent).filter(Agent.id == credentials.agent_id).first()
    if not agent:
        # Log failed attempt
        logger.warning("Authentication failed: agent not found", agent_id=credentials.agent_id)
        return None
    
    # 2. Verify agent has stored credentials
    if not agent.secret_hash:
        logger.warning("Authentication failed: no credentials set", agent_id=str(agent.id))
        return None
    
    # 3. Verify provided secret against stored hash
    if not credentials.agent_secret:
        logger.warning("Authentication failed: no secret provided", agent_id=str(agent.id))
        return None
    
    # 4. Use bcrypt to verify password
    if not self.verify_password(credentials.agent_secret, agent.secret_hash):
        logger.warning("Authentication failed: invalid secret", agent_id=str(agent.id))
        return None
    
    # 5. Authentication successful
    logger.info("Authentication successful", agent_id=str(agent.id), agent_name=agent.name)
    return agent
'''
    
    print(secure_code)
    print("✅ SECURE: Proper credential verification with bcrypt")
    print("✅ SECURE: Audit logging for all attempts")
    print("✅ SECURE: No information leakage in error messages")

def demonstrate_database_migration():
    """Show database migration to add agent credentials."""
    print("\n=== DATABASE MIGRATION FOR CREDENTIALS ===")
    
    migration_sql = '''
-- Migration: Add agent credentials support
-- File: migrations/version_0002_agent_credentials.sql

BEGIN;

-- Add secret_hash column for secure credential storage
ALTER TABLE agent 
ADD COLUMN secret_hash TEXT NULL;

-- Add index for efficient lookups
CREATE INDEX CONCURRENTLY ix_agent_secret_hash ON agent(secret_hash) 
WHERE secret_hash IS NOT NULL;

-- Add credential creation/update timestamp
ALTER TABLE agent 
ADD COLUMN credentials_updated_at TIMESTAMP WITH TIME ZONE NULL;

-- Add comment for documentation
COMMENT ON COLUMN agent.secret_hash IS 'Bcrypt hash of agent secret for authentication';
COMMENT ON COLUMN agent.credentials_updated_at IS 'Timestamp of last credential update';

COMMIT;
'''
    
    print(migration_sql)
    print("✅ MIGRATION: Adds secure credential storage")
    print("✅ MIGRATION: Includes proper indexing")
    print("✅ MIGRATION: Maintains backward compatibility")

def demonstrate_secure_cors_config():
    """Show secure CORS configuration."""
    print("\n=== SECURE CORS CONFIGURATION ===")
    
    secure_cors = '''
# Environment-based CORS configuration
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

# Secure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS if CORS_ALLOWED_ORIGINS != [""] else [],
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Only required methods
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],  # Only required headers
    expose_headers=["X-Request-ID"],  # Headers that clients can access
    max_age=3600,  # Cache preflight requests
)

# Example environment configuration:
# export CORS_ALLOWED_ORIGINS="https://your-app.com,https://api.your-app.com"
# export CORS_ALLOW_CREDENTIALS="true"
'''
    
    print(secure_cors)
    print("✅ SECURE: Environment-configurable origins")
    print("✅ SECURE: Restricted methods and headers")
    print("✅ SECURE: Proper credential handling")

def demonstrate_production_environment():
    """Show complete production environment configuration."""
    print("\n=== PRODUCTION ENVIRONMENT CONFIGURATION ===")
    
    env_config = '''
# Critical Security Environment Variables
export JWT_SECRET_KEY="$(openssl rand -hex 32)"           # 64-char hex string
export JWT_ACCESS_TOKEN_EXPIRE_MINUTES="30"               # 30 minutes
export JWT_REFRESH_TOKEN_EXPIRE_DAYS="7"                  # 7 days

# Rate Limiting
export RATE_LIMIT_ENABLED="true"
export MAX_REQUESTS_PER_MINUTE="30"                       # Tighter limits
export MAX_REQUESTS_PER_HOUR="500"                        # Production limits

# Security Headers
export HTTPS_ONLY="true"
export ENVIRONMENT="production"

# CORS Configuration  
export CORS_ALLOWED_ORIGINS="https://your-app.com,https://admin.your-app.com"
export CORS_ALLOW_CREDENTIALS="true"

# Redis for Rate Limiting and Token Revocation
export REDIS_URL="redis://redis:6379/1"

# Request Limits
export MAX_REQUEST_SIZE="5242880"                         # 5MB instead of 10MB

# Database Connection
export DATABASE_URL="postgresql://user:pass@postgres:5432/orchestrator"
'''
    
    print(env_config)
    print("✅ PRODUCTION: All security settings configured")
    print("✅ PRODUCTION: Appropriate timeouts and limits")
    print("✅ PRODUCTION: Secure secret generation")

def create_secure_agent_example():
    """Demonstrate secure agent creation with credentials."""
    print("\n=== SECURE AGENT CREATION EXAMPLE ===")
    
    example_code = '''
# Example: Secure agent creation with credentials
import secrets
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_agent_with_credentials(name: str, scopes: List[str], db: Session) -> Dict[str, str]:
    """Create agent with secure credentials."""
    
    # 1. Generate secure random secret
    agent_secret = secrets.token_urlsafe(32)  # 43-character URL-safe string
    
    # 2. Hash the secret for storage
    secret_hash = pwd_context.hash(agent_secret)
    
    # 3. Create agent with hashed credentials
    agent = Agent(
        name=name,
        scopes=scopes,
        secret_hash=secret_hash,
        credentials_updated_at=datetime.now(timezone.utc)
    )
    
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    # 4. Return credentials (only time they're visible)
    return {
        "agent_id": str(agent.id),
        "agent_secret": agent_secret,  # Show once, then never again
        "message": "Store these credentials securely - they cannot be retrieved later"
    }

# Usage example:
credentials = create_agent_with_credentials(
    name="production-assistant",
    scopes=["tasks:create", "tasks:read", "events:publish"],
    db=db_session
)

print(f"Agent ID: {credentials['agent_id']}")
print(f"Agent Secret: {credentials['agent_secret']}")  # Store securely!
'''
    
    print(example_code)
    print("✅ SECURE: Cryptographically random secrets")
    print("✅ SECURE: Proper bcrypt hashing")
    print("✅ SECURE: One-time secret revelation")

def main():
    """Run security fixes demonstration."""
    print("🔒 PERSONAL AGENT ORCHESTRATOR - SECURITY FIXES DEMO")
    print("=" * 65)
    
    print("This script demonstrates critical security vulnerabilities")
    print("found during the audit and shows how to fix them properly.")
    print("=" * 65)
    
    # 1. Generate secure JWT secret
    print("\n1. GENERATING SECURE JWT SECRET")
    jwt_secret = generate_secure_jwt_secret()
    
    # 2. Show authentication vulnerability
    demonstrate_authentication_vulnerability()
    
    # 3. Show secure authentication fix
    demonstrate_secure_authentication()
    
    # 4. Show database migration
    demonstrate_database_migration()
    
    # 5. Show secure CORS config
    demonstrate_secure_cors_config()
    
    # 6. Show production environment
    demonstrate_production_environment()
    
    # 7. Show secure agent creation
    create_secure_agent_example()
    
    print("\n" + "=" * 65)
    print("🎯 NEXT STEPS FOR PRODUCTION DEPLOYMENT:")
    print("=" * 65)
    print("1. Set JWT_SECRET_KEY environment variable")
    print("2. Run database migration to add secret_hash column")
    print("3. Update authentication code to verify credentials")
    print("4. Configure CORS origins for your domain")
    print("5. Set production rate limits and security settings")
    print("6. Test authentication with real credentials")
    print("7. Deploy with monitoring and alerting")
    print("\n✅ After these fixes: PRODUCTION READY")

if __name__ == "__main__":
    main()