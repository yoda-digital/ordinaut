"""
Agent management API routes.

Provides basic CRUD operations for agents including creation, listing,
and scope management. These endpoints are primarily for administrative use.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field

from ..models import Agent, AuditLog
from ..schemas import AgentResponse, OperationResponse
from ..dependencies import get_db, require_scopes

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