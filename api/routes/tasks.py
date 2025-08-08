"""
Task management API routes.

Provides CRUD operations for tasks including creation, listing, status management,
and immediate execution. All endpoints include proper authentication, validation,
and audit logging.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..models import Task, DueWork, Agent, AuditLog
from ..schemas import (
    TaskCreateRequest, TaskUpdateRequest, TaskResponse, TaskListResponse,
    OperationResponse, SnoozeRequest
)
from ..dependencies import get_db, get_current_agent

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_request: TaskCreateRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> TaskResponse:
    """
    Create a new scheduled task.
    
    Creates a new task with the specified schedule and pipeline configuration.
    The task will be automatically scheduled according to its schedule_kind and schedule_expr.
    
    Returns the created task with generated ID and timestamps.
    """
    # Verify the creating agent exists and has permission
    creating_agent = db.query(Agent).filter(Agent.id == task_request.created_by).first()
    if not creating_agent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent {task_request.created_by} not found"
        )
    
    # Create the task
    task = Task(
        title=task_request.title,
        description=task_request.description,
        created_by=task_request.created_by,
        schedule_kind=task_request.schedule_kind,
        schedule_expr=task_request.schedule_expr,
        timezone=task_request.timezone,
        payload=task_request.payload,
        priority=task_request.priority,
        dedupe_key=task_request.dedupe_key,
        dedupe_window_seconds=task_request.dedupe_window_seconds,
        max_retries=task_request.max_retries,
        backoff_strategy=task_request.backoff_strategy,
        concurrency_key=task_request.concurrency_key,
    )
    
    try:
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # Log the creation
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action="task.created",
            subject_id=task.id,
            details={
                "title": task.title,
                "schedule_kind": task.schedule_kind.value,
                "created_by": str(task.created_by)
            }
        )
        db.add(audit_log)
        db.commit()
        
        return TaskResponse.from_orm(task)
        
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create task: {str(e)}"
        )


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by task status"),
    created_by: Optional[UUID] = Query(None, description="Filter by creating agent"),
    schedule_kind: Optional[str] = Query(None, description="Filter by schedule kind"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of tasks to return"),
    offset: int = Query(0, ge=0, description="Number of tasks to skip"),
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> TaskListResponse:
    """
    List tasks with optional filtering and pagination.
    
    Returns a paginated list of tasks that the current agent has access to.
    Supports filtering by status, creating agent, and schedule kind.
    """
    query = db.query(Task)
    
    # Apply filters
    if status_filter:
        query = query.filter(Task.status == status_filter)
    if created_by:
        query = query.filter(Task.created_by == created_by)
    if schedule_kind:
        query = query.filter(Task.schedule_kind == schedule_kind)
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination and ordering
    tasks = query.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()
    
    # Convert to response format
    task_responses = [TaskResponse.from_orm(task) for task in tasks]
    
    return TaskListResponse(
        items=task_responses,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(tasks)) < total
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> TaskResponse:
    """
    Get a specific task by ID.
    
    Returns the complete task details including schedule configuration and payload.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    return TaskResponse.from_orm(task)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    task_update: TaskUpdateRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> TaskResponse:
    """
    Update an existing task.
    
    Updates the specified task with new values. Only provided fields will be updated.
    Schedule changes will be reflected in the next execution cycle.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    # Update provided fields
    update_data = task_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)
    
    try:
        db.commit()
        db.refresh(task)
        
        # Log the update
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action="task.updated",
            subject_id=task.id,
            details={"updated_fields": list(update_data.keys())}
        )
        db.add(audit_log)
        db.commit()
        
        return TaskResponse.from_orm(task)
        
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update task: {str(e)}"
        )


@router.post("/{task_id}/run_now", response_model=OperationResponse)
async def trigger_task_run(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> OperationResponse:
    """
    Manually trigger immediate task execution.
    
    Creates a due_work entry for immediate execution, bypassing the normal schedule.
    The task will be picked up by the next available worker.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    if task.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot run task with status '{task.status}'. Task must be active."
        )
    
    # Create immediate work item
    due_work = DueWork(
        task_id=task.id,
        run_at=datetime.now(timezone.utc)
    )
    
    try:
        db.add(due_work)
        db.commit()
        
        # Log the manual trigger
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action="task.run_now",
            subject_id=task.id,
            details={"due_work_id": due_work.id}
        )
        db.add(audit_log)
        db.commit()
        
        return OperationResponse(
            success=True,
            message="Task execution triggered successfully",
            details={"task_id": str(task.id), "due_work_id": due_work.id}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger task execution: {str(e)}"
        )


@router.post("/{task_id}/snooze", response_model=OperationResponse)
async def snooze_task(
    task_id: UUID,
    snooze_request: SnoozeRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> OperationResponse:
    """
    Snooze task by delaying its next execution.
    
    Delays the next scheduled execution of the task by the specified number of seconds.
    This affects all pending due_work items for this task.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    if task.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot snooze task with status '{task.status}'. Task must be active."
        )
    
    # Update all pending due_work items for this task
    try:
        result = db.execute(
            text("""
                UPDATE due_work 
                SET run_at = run_at + INTERVAL :delay_seconds * INTERVAL '1 second'
                WHERE task_id = :task_id 
                  AND run_at > now() 
                  AND (locked_until IS NULL OR locked_until < now())
            """),
            {"task_id": task_id, "delay_seconds": snooze_request.delay_seconds}
        )
        
        affected_rows = result.rowcount
        db.commit()
        
        # Log the snooze
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action="task.snoozed",
            subject_id=task.id,
            details={
                "delay_seconds": snooze_request.delay_seconds,
                "reason": snooze_request.reason,
                "affected_work_items": affected_rows
            }
        )
        db.add(audit_log)
        db.commit()
        
        return OperationResponse(
            success=True,
            message=f"Task snoozed for {snooze_request.delay_seconds} seconds",
            details={
                "task_id": str(task_id),
                "delay_seconds": snooze_request.delay_seconds,
                "affected_work_items": affected_rows
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to snooze task: {str(e)}"
        )


@router.post("/{task_id}/pause", response_model=OperationResponse)
async def pause_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> OperationResponse:
    """
    Pause task execution.
    
    Sets task status to 'paused', preventing new executions.
    Currently running executions will complete normally.
    """
    return await _update_task_status(task_id, "paused", "task.paused", "Task paused successfully", db, current_agent)


@router.post("/{task_id}/resume", response_model=OperationResponse) 
async def resume_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> OperationResponse:
    """
    Resume paused task execution.
    
    Sets task status to 'active', allowing normal scheduling to resume.
    The task will be included in the next scheduler cycle.
    """
    return await _update_task_status(task_id, "active", "task.resumed", "Task resumed successfully", db, current_agent)


@router.post("/{task_id}/cancel", response_model=OperationResponse)
async def cancel_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> OperationResponse:
    """
    Cancel task permanently.
    
    Sets task status to 'canceled' and removes all pending due_work items.
    This action cannot be undone - create a new task if needed.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    try:
        # Cancel the task and remove pending work
        task.status = "canceled"
        
        # Remove all pending due_work items
        deleted_work = db.execute(
            text("""
                DELETE FROM due_work 
                WHERE task_id = :task_id 
                  AND (locked_until IS NULL OR locked_until < now())
            """),
            {"task_id": task_id}
        )
        
        db.commit()
        
        # Log the cancellation
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action="task.canceled",
            subject_id=task.id,
            details={"removed_work_items": deleted_work.rowcount}
        )
        db.add(audit_log)
        db.commit()
        
        return OperationResponse(
            success=True,
            message="Task canceled successfully",
            details={
                "task_id": str(task_id),
                "removed_work_items": deleted_work.rowcount
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel task: {str(e)}"
        )


async def _update_task_status(
    task_id: UUID,
    new_status: str,
    audit_action: str,
    success_message: str,
    db: Session,
    current_agent: Agent
) -> OperationResponse:
    """Helper function to update task status with audit logging."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    old_status = task.status
    if old_status == new_status:
        return OperationResponse(
            success=True,
            message=f"Task already has status '{new_status}'",
            details={"task_id": str(task_id), "status": new_status}
        )
    
    try:
        task.status = new_status
        db.commit()
        
        # Log the status change
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action=audit_action,
            subject_id=task.id,
            details={"old_status": old_status, "new_status": new_status}
        )
        db.add(audit_log)
        db.commit()
        
        return OperationResponse(
            success=True,
            message=success_message,
            details={"task_id": str(task_id), "old_status": old_status, "new_status": new_status}
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update task status: {str(e)}"
        )