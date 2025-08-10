"""
Agent management API routes.

Provides basic CRUD operations for agents including creation, listing,
and scope management. These endpoints are primarily for administrative use.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field

from ..models import Agent, AuditLog
from ..schemas import AgentResponse, OperationResponse
from ..dependencies import get_db, require_scopes
from ..auth import (
    jwt_manager, agent_authenticator, AgentCredentials, 
    TokenResponse, TokenRequest, get_jwt_manager
)

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreateRequest(BaseModel):
    """Schema for creating new agents."""
    name: str = Field(..., min_length=1, max_length=100, description="Unique agent name")
    scopes: List[str] = Field(..., description="List of permission scopes for this agent")
    webhook_url: Optional[str] = Field(None, description="Optional webhook URL for notifications")
    
    class Config:
        schema_extra = {
            "example": {
                "name": "morning-assistant",
                "scopes": ["calendar.read", "notify", "weather.read"],
                "webhook_url": "https://webhook.example.com/agent-notifications"
            }
        }


class AgentUpdateRequest(BaseModel):
    """Schema for updating existing agents."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    scopes: Optional[List[str]] = None
    webhook_url: Optional[str] = None


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_request: AgentCreateRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(require_scopes("admin"))
) -> AgentResponse:
    """
    Create a new agent with specified scopes.
    
    Only agents with 'admin' scope can create new agents.
    The created agent will have the specified scopes and can be used
    for authentication in API requests.
    """
    # Create the agent
    agent = Agent(
        name=agent_request.name,
        scopes=agent_request.scopes,
        webhook_url=agent_request.webhook_url
    )
    
    try:
        db.add(agent)
        db.commit()
        db.refresh(agent)
        
        # Log the creation
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action="agent.created",
            subject_id=agent.id,
            details={
                "name": agent.name,
                "scopes": agent.scopes
            }
        )
        db.add(audit_log)
        db.commit()
        
        return AgentResponse.from_orm(agent)
        
    except IntegrityError as e:
        db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Agent with name '{agent_request.name}' already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create agent: {str(e)}"
        )


@router.get("/", response_model=List[AgentResponse])
async def list_agents(
    name_filter: Optional[str] = Query(None, description="Filter by agent name"),
    scope_filter: Optional[str] = Query(None, description="Filter by agents with this scope"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of agents to return"),
    offset: int = Query(0, ge=0, description="Number of agents to skip"),
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(require_scopes("admin"))
) -> List[AgentResponse]:
    """
    List all agents with optional filtering.
    
    Only agents with 'admin' scope can list agents.
    """
    query = db.query(Agent)
    
    # Apply filters
    if name_filter:
        query = query.filter(Agent.name.ilike(f"%{name_filter}%"))
    if scope_filter:
        query = query.filter(Agent.scopes.contains([scope_filter]))
    
    # Apply pagination and ordering
    agents = query.order_by(Agent.created_at.desc()).offset(offset).limit(limit).all()
    
    # Convert to response format
    return [AgentResponse.from_orm(agent) for agent in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(require_scopes("admin"))
) -> AgentResponse:
    """
    Get a specific agent by ID.
    
    Only agents with 'admin' scope can view agent details.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )
    
    return AgentResponse.from_orm(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    agent_update: AgentUpdateRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(require_scopes("admin"))
) -> AgentResponse:
    """
    Update an existing agent.
    
    Only agents with 'admin' scope can update agents.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )
    
    # Update provided fields
    update_data = agent_update.dict(exclude_unset=True)
    old_data = {
        "name": agent.name,
        "scopes": agent.scopes,
        "webhook_url": agent.webhook_url
    }
    
    for field, value in update_data.items():
        setattr(agent, field, value)
    
    try:
        db.commit()
        db.refresh(agent)
        
        # Log the update
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action="agent.updated",
            subject_id=agent.id,
            details={
                "updated_fields": list(update_data.keys()),
                "old_data": old_data,
                "new_data": {k: v for k, v in update_data.items()}
            }
        )
        db.add(audit_log)
        db.commit()
        
        return AgentResponse.from_orm(agent)
        
    except IntegrityError as e:
        db.rollback()
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Agent with name '{agent_update.name}' already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update agent: {str(e)}"
        )


@router.delete("/{agent_id}", response_model=OperationResponse)
async def delete_agent(
    agent_id: UUID,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(require_scopes("admin"))
) -> OperationResponse:
    """
    Delete an agent.
    
    Only agents with 'admin' scope can delete agents.
    This will also delete all tasks created by this agent.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )
    
    # Prevent deletion of system agent
    if agent.name == "system":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the system agent"
        )
    
    # Prevent self-deletion
    if agent.id == current_agent.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agents cannot delete themselves"
        )
    
    try:
        agent_name = agent.name
        db.delete(agent)
        db.commit()
        
        # Log the deletion
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action="agent.deleted",
            subject_id=agent_id,
            details={"deleted_agent_name": agent_name}
        )
        db.add(audit_log)
        db.commit()
        
        return OperationResponse(
            success=True,
            message="Agent deleted successfully",
            details={"agent_id": str(agent_id), "agent_name": agent_name}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete agent: {str(e)}"
        )


# Authentication endpoints
@router.post("/auth/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def authenticate_agent(
    credentials: AgentCredentials,
    db: Session = Depends(get_db)
) -> TokenResponse:
    """
    Authenticate agent and receive JWT tokens.
    
    Validates agent credentials and returns access and refresh tokens.
    The access token is used for API authentication, while the refresh
    token can be used to obtain new access tokens.
    
    **Note**: Currently uses agent ID for authentication. In production,
    implement proper password-based authentication with hashed credentials.
    """
    # Authenticate the agent
    agent = agent_authenticator.authenticate_agent(credentials, db)
    
    if not agent:
        # Log authentication attempt
        from observability.logging import api_logger
        api_logger.warning(
            f"Authentication failed for agent",
            agent_id=credentials.agent_id
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Generate JWT tokens
    tokens = jwt_manager.generate_tokens(agent)
    
    # Log successful authentication
    audit_log = AuditLog(
        actor_agent_id=agent.id,
        action="agent.authenticated",
        subject_id=agent.id,
        details={"method": "credentials"}
    )
    db.add(audit_log)
    db.commit()
    
    return tokens


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(
    token_request: TokenRequest,
    db: Session = Depends(get_db)
) -> TokenResponse:
    """
    Refresh access token using refresh token.
    
    Validates the provided refresh token and generates a new access token
    with updated expiration. The refresh token remains valid until its
    original expiration date.
    """
    try:
        # Refresh the tokens
        tokens = jwt_manager.refresh_access_token(token_request.refresh_token, db)
        
        return tokens
        
    except HTTPException:
        # Re-raise authentication errors
        raise
    except Exception as e:
        from observability.logging import api_logger
        api_logger.error(f"Token refresh failed: {e}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh service error"
        )


@router.post("/auth/revoke", response_model=OperationResponse)
async def revoke_token(
    token_request: TokenRequest,
    db: Session = Depends(get_db)
) -> OperationResponse:
    """
    Revoke a JWT token.
    
    Adds the token to the revocation list, making it invalid for future
    authentication. Both access and refresh tokens can be revoked.
    """
    try:
        # Revoke the token
        success = jwt_manager.revoke_token(token_request.refresh_token)
        
        if success:
            # Log token revocation
            try:
                token_data = jwt_manager.verify_token(token_request.refresh_token)
                audit_log = AuditLog(
                    actor_agent_id=token_data.agent_id,
                    action="token.revoked",
                    subject_id=token_data.agent_id,
                    details={"token_type": token_data.token_type}
                )
                db.add(audit_log)
                db.commit()
            except:
                # Token already invalid, but revocation succeeded
                pass
        
        return OperationResponse(
            success=success,
            message="Token revoked successfully" if success else "Token was already invalid"
        )
        
    except Exception as e:
        from observability.logging import api_logger
        api_logger.error(f"Token revocation failed: {e}")
        
        return OperationResponse(
            success=True,  # Consider invalid tokens as successfully revoked
            message="Token revocation completed"
        )


class AgentCredentialsResponse(BaseModel):
    """Response model for agent credentials creation."""
    agent_id: str = Field(..., description="Agent identifier")
    agent_secret: str = Field(..., description="Agent secret for authentication")
    message: str = Field(..., description="Success message")
    
    class Config:
        schema_extra = {
            "example": {
                "agent_id": "550e8400-e29b-41d4-a716-446655440000",
                "agent_secret": "secure-secret-key",
                "message": "Agent credentials created successfully"
            }
        }


@router.post("/{agent_id}/credentials", response_model=AgentCredentialsResponse)
async def create_agent_credentials(
    agent_id: UUID,
    password: Optional[str] = Body(None, description="Optional password for agent"),
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(require_scopes("admin"))
) -> AgentCredentialsResponse:
    """
    Create or reset agent credentials.
    
    Generates authentication credentials for an agent. If no password is
    provided, a random secret will be generated. Only agents with 'admin'
    scope can create credentials for other agents.
    
    **Security Note**: The generated secret is only shown once during creation.
    Store it securely as it cannot be retrieved later.
    """
    # Get the target agent
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )
    
    # Create credentials
    credentials = agent_authenticator.create_agent_credentials(agent, password)
    
    # Log credential creation
    audit_log = AuditLog(
        actor_agent_id=current_agent.id,
        action="agent.credentials_created",
        subject_id=agent.id,
        details={"created_by": current_agent.name}
    )
    db.add(audit_log)
    db.commit()
    
    return AgentCredentialsResponse(
        agent_id=credentials["agent_id"],
        agent_secret=credentials["agent_secret"],
        message="Agent credentials created successfully"
    )