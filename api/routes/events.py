"""
External event publishing API routes.

Provides endpoints for publishing external events that can trigger event-based tasks.
Events are published to Redis Streams for durable, ordered processing.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import json
import redis

from ..models import Task, DueWork, Agent, AuditLog
from ..schemas import EventPublishRequest, OperationResponse
from ..dependencies import get_db, get_current_agent, get_redis

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def publish_event(
    event_request: EventPublishRequest,
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
    current_agent: Agent = Depends(get_current_agent)
) -> OperationResponse:
    """
    Publish an external event to trigger event-based tasks.
    
    Events are published to Redis Streams and will trigger any tasks with
    matching event topics. The event payload is made available to the
    task pipeline for processing.
    
    Returns immediately with event ID - processing is asynchronous.
    """
    # Verify source agent exists
    source_agent = db.query(Agent).filter(Agent.id == event_request.source_agent_id).first()
    if not source_agent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source agent {event_request.source_agent_id} not found"
        )
    
    # Generate unique event ID
    event_id = str(uuid4())
    timestamp = datetime.now(timezone.utc)
    
    # Prepare event payload for Redis Stream
    stream_data = {
        "event_id": event_id,
        "topic": event_request.topic,
        "payload": json.dumps(event_request.payload),
        "source_agent_id": str(event_request.source_agent_id),
        "published_at": timestamp.isoformat(),
        "published_by": str(current_agent.id)
    }
    
    try:
        # Publish to Redis Stream
        stream_id = redis_client.xadd("events", stream_data)
        
        # Find and trigger event-based tasks
        event_tasks = db.query(Task).filter(
            Task.schedule_kind == "event",
            Task.schedule_expr == event_request.topic,
            Task.status == "active"
        ).all()
        
        triggered_tasks = []
        for task in event_tasks:
            # Create due work item with event context
            due_work = DueWork(
                task_id=task.id,
                run_at=timestamp
            )
            db.add(due_work)
            triggered_tasks.append(str(task.id))
        
        db.commit()
        
        # Log the event publication
        audit_log = AuditLog(
            actor_agent_id=current_agent.id,
            action="event.published",
            subject_id=event_request.source_agent_id,
            details={
                "event_id": event_id,
                "topic": event_request.topic,
                "stream_id": stream_id.decode() if isinstance(stream_id, bytes) else stream_id,
                "triggered_tasks": triggered_tasks,
                "payload_size": len(json.dumps(event_request.payload))
            }
        )
        db.add(audit_log)
        db.commit()
        
        return OperationResponse(
            success=True,
            message=f"Event published successfully to topic '{event_request.topic}'",
            details={
                "event_id": event_id,
                "stream_id": stream_id.decode() if isinstance(stream_id, bytes) else stream_id,
                "topic": event_request.topic,
                "triggered_tasks": triggered_tasks,
                "published_at": timestamp.isoformat()
            }
        )
        
    except redis.RedisError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish event to Redis: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish event: {str(e)}"
        )


@router.get("/topics")
async def list_event_topics(
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
) -> dict:
    """
    List all active event topics and their associated tasks.
    
    Returns a summary of event topics currently being monitored
    and the number of tasks listening to each topic.
    """
    # Query for all event-based tasks
    event_tasks = db.query(Task).filter(
        Task.schedule_kind == "event",
        Task.status == "active"
    ).all()
    
    # Group by topic
    topics = {}
    for task in event_tasks:
        topic = task.schedule_expr
        if topic not in topics:
            topics[topic] = {
                "topic": topic,
                "active_tasks": 0,
                "task_ids": []
            }
        topics[topic]["active_tasks"] += 1
        topics[topic]["task_ids"].append(str(task.id))
    
    return {
        "total_topics": len(topics),
        "topics": list(topics.values())
    }


@router.get("/stream/recent")
async def get_recent_events(
    count: int = 50,
    redis_client: redis.Redis = Depends(get_redis),
    current_agent: Agent = Depends(get_current_agent)
) -> dict:
    """
    Get recent events from the event stream.
    
    Returns the most recent events from Redis Streams for monitoring
    and debugging purposes. Useful for verifying event publication.
    """
    try:
        # Read recent events from Redis Stream
        # XREVRANGE returns entries in reverse chronological order
        events = redis_client.xrevrange("events", count=count)
        
        parsed_events = []
        for stream_id, fields in events:
            # Parse fields from Redis (bytes to strings)
            event_data = {}
            for key, value in fields.items():
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                if isinstance(value, bytes):
                    value = value.decode('utf-8')
                
                # Parse JSON payload back to dict
                if key == "payload":
                    try:
                        event_data[key] = json.loads(value)
                    except json.JSONDecodeError:
                        event_data[key] = value
                else:
                    event_data[key] = value
            
            # Add stream ID
            stream_id_str = stream_id.decode() if isinstance(stream_id, bytes) else stream_id
            event_data["stream_id"] = stream_id_str
            
            parsed_events.append(event_data)
        
        return {
            "total_events": len(parsed_events),
            "events": parsed_events
        }
        
    except redis.RedisError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read from event stream: {str(e)}"
        )


@router.delete("/stream/cleanup")
async def cleanup_old_events(
    max_age_hours: int = 24,
    redis_client: redis.Redis = Depends(get_redis),
    current_agent: Agent = Depends(get_current_agent)
) -> OperationResponse:
    """
    Clean up old events from the Redis Stream.
    
    Removes events older than the specified age to prevent unbounded growth.
    Use with caution - this permanently deletes event history.
    """
    try:
        # Calculate timestamp cutoff (Redis stream IDs are timestamp-based)
        cutoff_timestamp = int((datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)) * 1000)
        cutoff_id = f"{cutoff_timestamp}-0"
        
        # Get count of events that will be deleted
        events_to_delete = redis_client.xrange("events", min="-", max=cutoff_id, count=1000)
        count_to_delete = len(events_to_delete)
        
        if count_to_delete == 0:
            return OperationResponse(
                success=True,
                message="No old events found to cleanup",
                details={"deleted_count": 0, "max_age_hours": max_age_hours}
            )
        
        # Use XTRIM to remove old events
        deleted_count = redis_client.xtrim("events", maxlen=None, approximate=False, minid=cutoff_id)
        
        return OperationResponse(
            success=True,
            message=f"Cleaned up {deleted_count} old events",
            details={
                "deleted_count": deleted_count,
                "max_age_hours": max_age_hours,
                "cutoff_timestamp": cutoff_timestamp
            }
        )
        
    except redis.RedisError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup event stream: {str(e)}"
        )