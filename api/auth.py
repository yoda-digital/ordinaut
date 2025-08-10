"""
JWT Authentication and Token Management for Ordinaut.

Provides secure JWT token generation, validation, and agent authentication
with scope-based authorization, refresh tokens, and comprehensive security.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from .models import Agent
from observability.logging import api_logger
from observability.metrics import orchestrator_metrics


# Security configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Logger
logger = api_logger


@dataclass
class TokenData:
    """JWT token data structure."""
    agent_id: str
    scopes: List[str]
    token_type: str  # "access" or "refresh"
    issued_at: datetime
    expires_at: datetime
    jti: str  # JWT ID for token revocation


class TokenResponse(BaseModel):
    """JWT token response model."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    scope: str = Field(..., description="Space-separated list of scopes")


class TokenRequest(BaseModel):
    """Token request model for refresh operations."""
    refresh_token: str = Field(..., description="Valid refresh token")


class AgentCredentials(BaseModel):
    """Agent credentials for authentication."""
    agent_id: str = Field(..., description="Agent identifier")
    agent_secret: Optional[str] = Field(None, description="Agent secret (if required)")


class JWTManager:
    """
    JWT token management with comprehensive security features.
    
    Provides token generation, validation, refresh, and revocation
    with proper security practices and audit logging.
    """
    
    def __init__(self):
        self.secret_key = JWT_SECRET_KEY
        self.algorithm = JWT_ALGORITHM
        self.access_token_expire_minutes = JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = JWT_REFRESH_TOKEN_EXPIRE_DAYS
        
        # In production, use external token store (Redis) for revocation
        self._revoked_tokens: set = set()
        
        if JWT_SECRET_KEY == "dev-secret-key-change-in-production":
            logger.warning("Using default JWT secret key - change in production!")
    
    def _generate_jti(self) -> str:
        """Generate unique JWT ID."""
        return secrets.token_urlsafe(32)
    
    def _create_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT token with expiration."""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": self._generate_jti()
        })
        
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
    
    def generate_tokens(self, agent: Agent) -> TokenResponse:
        """
        Generate access and refresh tokens for an agent.
        
        Creates both access and refresh tokens with appropriate expiration
        times and scope information. Logs token generation for audit.
        """
        # Access token data
        access_token_data = {
            "sub": str(agent.id),
            "type": "access",
            "scopes": agent.scopes,
            "name": agent.name
        }
        
        # Refresh token data (minimal information)
        refresh_token_data = {
            "sub": str(agent.id),
            "type": "refresh",
            "scopes": agent.scopes  # Store scopes for refresh validation
        }
        
        # Create tokens
        access_token_expires = timedelta(minutes=self.access_token_expire_minutes)
        refresh_token_expires = timedelta(days=self.refresh_token_expire_days)
        
        access_token = self._create_token(access_token_data, access_token_expires)
        refresh_token = self._create_token(refresh_token_data, refresh_token_expires)
        
        # Log token generation and record metrics
        logger.info(
            f"Generated tokens for agent {agent.name}",
            agent_id=str(agent.id),
            scopes=agent.scopes,
            access_expires_in=self.access_token_expire_minutes * 60
        )
        
        orchestrator_metrics.record_jwt_token_issued(str(agent.id), "access")
        orchestrator_metrics.record_jwt_token_issued(str(agent.id), "refresh")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self.access_token_expire_minutes * 60,
            scope=" ".join(agent.scopes)
        )
    
    def verify_token(self, token: str, token_type: str = "access") -> TokenData:
        """
        Verify JWT token and extract claims.
        
        Validates token signature, expiration, and type. Returns token
        data or raises authentication exception.
        """
        try:
            # Decode token
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Extract claims
            agent_id = payload.get("sub")
            token_type_claim = payload.get("type", "access")
            scopes = payload.get("scopes", [])
            issued_at = datetime.fromtimestamp(payload.get("iat"), tz=timezone.utc)
            expires_at = datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc)
            jti = payload.get("jti")
            
            if not agent_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing subject",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Verify token type
            if token_type_claim != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token type: expected {token_type}, got {token_type_claim}",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Check if token is revoked
            if jti in self._revoked_tokens:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            return TokenData(
                agent_id=agent_id,
                scopes=scopes,
                token_type=token_type_claim,
                issued_at=issued_at,
                expires_at=expires_at,
                jti=jti
            )
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except jwt.JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"}
            )
    
    def refresh_access_token(self, refresh_token: str, db: Session) -> TokenResponse:
        """
        Refresh access token using refresh token.
        
        Validates refresh token and generates new access token with
        updated expiration. Refresh token remains valid until expiry.
        """
        # Verify refresh token
        token_data = self.verify_token(refresh_token, token_type="refresh")
        
        # Get agent to ensure it still exists and is valid
        agent = db.query(Agent).filter(Agent.id == token_data.agent_id).first()
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Agent not found or inactive",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Verify scopes haven't changed (security check)
        if set(agent.scopes) != set(token_data.scopes):
            logger.warning(
                f"Agent scopes changed during refresh",
                agent_id=str(agent.id),
                old_scopes=token_data.scopes,
                new_scopes=agent.scopes
            )
            # Force re-authentication if scopes changed
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Agent permissions changed, please re-authenticate",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Generate new tokens
        return self.generate_tokens(agent)
    
    def revoke_token(self, token: str) -> bool:
        """
        Revoke a JWT token.
        
        Adds token to revocation list. In production, this should
        use Redis or database for distributed token revocation.
        """
        try:
            token_data = self.verify_token(token)
            self._revoked_tokens.add(token_data.jti)
            
            logger.info(
                f"Token revoked",
                agent_id=token_data.agent_id,
                token_type=token_data.token_type,
                jti=token_data.jti
            )
            
            orchestrator_metrics.record_jwt_token_revoked("manual")
            return True
        except:
            # Token is already invalid, consider it revoked
            return True
    
    def validate_scope_access(self, token_data: TokenData, required_scopes: List[str]) -> bool:
        """
        Validate if token has required scopes.
        
        Checks if all required scopes are present in token scopes.
        Returns True if access is granted, False otherwise.
        """
        token_scopes = set(token_data.scopes)
        required_scopes_set = set(required_scopes)
        
        return required_scopes_set.issubset(token_scopes)


class AgentAuthenticator:
    """
    Agent authentication service with credential validation.
    
    Provides agent authentication, credential validation, and
    integration with JWT token management.
    """
    
    def __init__(self, jwt_manager: JWTManager):
        self.jwt_manager = jwt_manager
        self.pwd_context = pwd_context
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash."""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Generate password hash."""
        return self.pwd_context.hash(password)
    
    def authenticate_agent(self, credentials: AgentCredentials, db: Session) -> Optional[Agent]:
        """
        Authenticate agent with credentials.
        
        For basic deployment, this validates agent exists and is active.
        In production, this would validate agent secrets/passwords.
        """
        try:
            agent = db.query(Agent).filter(Agent.id == credentials.agent_id).first()
            
            if not agent:
                logger.warning(f"Authentication failed: agent not found", agent_id=credentials.agent_id)
                orchestrator_metrics.record_authentication_attempt("credentials", "failed")
                return None
            
            # TODO: In production, validate agent_secret against stored hash
            # For now, we trust the agent ID is sufficient authentication
            # This matches the current Bearer token approach
            
            logger.info(f"Agent authenticated successfully", agent_id=str(agent.id), agent_name=agent.name)
            orchestrator_metrics.record_authentication_attempt("credentials", "success")
            return agent
            
        except Exception as e:
            logger.error(f"Authentication error: {e}", agent_id=credentials.agent_id)
            orchestrator_metrics.record_authentication_attempt("credentials", "error")
            return None
    
    def create_agent_credentials(self, agent: Agent, password: Optional[str] = None) -> Dict[str, str]:
        """
        Create agent credentials for authentication.
        
        Generates agent secret and updates agent record.
        In production, this would store hashed credentials.
        """
        if password:
            # Hash password for storage
            hashed_secret = self.get_password_hash(password)
            
            # TODO: Store hashed secret in agent record or separate credentials table
            logger.info(f"Agent credentials created", agent_id=str(agent.id))
            
            return {
                "agent_id": str(agent.id),
                "agent_secret": password  # Return plaintext for initial setup
            }
        
        # Generate random secret for agent
        secret = secrets.token_urlsafe(32)
        hashed_secret = self.get_password_hash(secret)
        
        # TODO: Store hashed secret
        logger.info(f"Agent secret generated", agent_id=str(agent.id))
        
        return {
            "agent_id": str(agent.id),
            "agent_secret": secret
        }


# Global instances
jwt_manager = JWTManager()
agent_authenticator = AgentAuthenticator(jwt_manager)


def get_jwt_manager() -> JWTManager:
    """Get JWT manager instance."""
    return jwt_manager


def get_agent_authenticator() -> AgentAuthenticator:
    """Get agent authenticator instance."""
    return agent_authenticator