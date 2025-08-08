"""
Task run history API routes.

Provides access to task execution history, including success/failure status,
timing information, error details, and output data.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..models import TaskRun, Task, Agent
from ..schemas import TaskRunResponse, TaskRunListResponse
from ..dependencies import get_db, get_current_agent

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/", response_model=TaskRunListResponse)
async def list_runs(
    task_id: Optional[UUID] = Query(None, description="Filter by specific task ID"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    include_errors: bool = Query(False, description="Include error details in response"),
    start_time: Optional[datetime] = Query(None, description="Filter runs after this timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter runs before this timestamp"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of runs to return"),
    offset: int = Query(0, ge=0, description="Number of runs to skip"),
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> TaskRunListResponse:
    """
    List task execution runs with filtering and pagination.
    
    Returns a paginated list of task runs, optionally filtered by task ID,
    success status, and time range. Useful for debugging and monitoring.
    """
    query = db.query(TaskRun).join(Task)
    
    # Apply filters
    if task_id:
        query = query.filter(TaskRun.task_id == task_id)
    if success is not None:
        query = query.filter(TaskRun.success == success)
    if start_time:
        query = query.filter(TaskRun.created_at >= start_time)
    if end_time:
        query = query.filter(TaskRun.created_at <= end_time)
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination and ordering (most recent first)
    runs = query.order_by(TaskRun.created_at.desc()).offset(offset).limit(limit).all()
    
    # Convert to response format
    run_responses = []
    for run in runs:
        run_data = TaskRunResponse.from_orm(run)
        # Optionally exclude error details for cleaner responses
        if not include_errors and run_data.error:
            run_data.error = "[Error details hidden - use include_errors=true]"
        run_responses.append(run_data)
    
    return TaskRunListResponse(
        items=run_responses,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(runs)) < total
    )


@router.get("/{run_id}", response_model=TaskRunResponse)
async def get_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> TaskRunResponse:
    """
    Get detailed information about a specific task run.
    
    Returns complete run details including timing, output data, and error information.
    Useful for debugging failed executions and analyzing performance.
    """
    run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task run {run_id} not found"
        )
    
    return TaskRunResponse.from_orm(run)


@router.get("/task/{task_id}/latest", response_model=Optional[TaskRunResponse])
async def get_latest_run(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> Optional[TaskRunResponse]:
    """
    Get the most recent run for a specific task.
    
    Returns the latest execution attempt for the specified task,
    or null if the task has never been executed.
    """
    # Verify task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    # Get the most recent run
    latest_run = (
        db.query(TaskRun)
        .filter(TaskRun.task_id == task_id)
        .order_by(TaskRun.created_at.desc())
        .first()
    )
    
    if not latest_run:
        return None
    
    return TaskRunResponse.from_orm(latest_run)


@router.get("/task/{task_id}/stats")
async def get_task_run_stats(
    task_id: UUID,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> dict:
    """
    Get execution statistics for a specific task.
    
    Returns success/failure rates, average execution time, and other metrics
    for the specified task over the given time period.
    """
    # Verify task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    # Calculate cutoff time
    cutoff_time = datetime.now(timezone.utc) - timezone.utc.localize(datetime.now()).replace(
        tzinfo=None
    ).replace(day=days)
    
    # Query for statistics
    runs = db.query(TaskRun).filter(
        TaskRun.task_id == task_id,
        TaskRun.created_at >= cutoff_time
    ).all()
    
    if not runs:
        return {
            "task_id": str(task_id),
            "period_days": days,
            "total_runs": 0,
            "success_rate": 0.0,
            "failure_rate": 0.0,
            "avg_execution_time_seconds": 0.0,
            "last_run": None,
            "last_success": None,
            "last_failure": None
        }
    
    # Calculate statistics
    total_runs = len(runs)
    successful_runs = [r for r in runs if r.success is True]
    failed_runs = [r for r in runs if r.success is False]
    
    success_rate = len(successful_runs) / total_runs if total_runs > 0 else 0.0
    failure_rate = len(failed_runs) / total_runs if total_runs > 0 else 0.0
    
    # Calculate average execution time (only for completed runs)
    completed_runs = [r for r in runs if r.started_at and r.finished_at]
    avg_execution_time = 0.0
    if completed_runs:
        total_time = sum(
            (r.finished_at - r.started_at).total_seconds() 
            for r in completed_runs
        )
        avg_execution_time = total_time / len(completed_runs)
    
    # Find last run times
    sorted_runs = sorted(runs, key=lambda r: r.created_at, reverse=True)
    last_run = sorted_runs[0].created_at if sorted_runs else None
    
    last_success = None
    last_failure = None
    for run in sorted_runs:
        if run.success is True and last_success is None:
            last_success = run.created_at
        elif run.success is False and last_failure is None:
            last_failure = run.created_at
        if last_success and last_failure:
            break
    
    return {
        "task_id": str(task_id),
        "period_days": days,
        "total_runs": total_runs,
        "successful_runs": len(successful_runs),
        "failed_runs": len(failed_runs),
        "success_rate": round(success_rate, 3),
        "failure_rate": round(failure_rate, 3),
        "avg_execution_time_seconds": round(avg_execution_time, 2),
        "last_run": last_run,
        "last_success": last_success,
        "last_failure": last_failure
    }


@router.get("/stats/summary")
async def get_overall_stats(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> dict:
    """
    Get overall execution statistics across all tasks.
    
    Returns system-wide metrics including total runs, success rates,
    and performance statistics over the specified time period.
    """
    # Calculate cutoff time
    cutoff_time = datetime.now(timezone.utc) - timezone.utc.localize(datetime.now()).replace(
        tzinfo=None
    ).replace(day=days)
    
    # Query for all recent runs
    runs = db.query(TaskRun).filter(TaskRun.created_at >= cutoff_time).all()
    
    if not runs:
        return {
            "period_days": days,
            "total_runs": 0,
            "total_tasks_executed": 0,
            "success_rate": 0.0,
            "failure_rate": 0.0,
            "avg_execution_time_seconds": 0.0,
            "runs_per_day": 0.0
        }
    
    # Calculate statistics
    total_runs = len(runs)
    unique_tasks = len(set(r.task_id for r in runs))
    successful_runs = [r for r in runs if r.success is True]
    failed_runs = [r for r in runs if r.success is False]
    
    success_rate = len(successful_runs) / total_runs if total_runs > 0 else 0.0
    failure_rate = len(failed_runs) / total_runs if total_runs > 0 else 0.0
    
    # Calculate average execution time (only for completed runs)
    completed_runs = [r for r in runs if r.started_at and r.finished_at]
    avg_execution_time = 0.0
    if completed_runs:
        total_time = sum(
            (r.finished_at - r.started_at).total_seconds() 
            for r in completed_runs
        )
        avg_execution_time = total_time / len(completed_runs)
    
    # Calculate runs per day
    runs_per_day = total_runs / days if days > 0 else 0.0
    
    return {
        "period_days": days,
        "total_runs": total_runs,
        "total_tasks_executed": unique_tasks,
        "successful_runs": len(successful_runs),
        "failed_runs": len(failed_runs),
        "success_rate": round(success_rate, 3),
        "failure_rate": round(failure_rate, 3),
        "avg_execution_time_seconds": round(avg_execution_time, 2),
        "runs_per_day": round(runs_per_day, 1)
    }