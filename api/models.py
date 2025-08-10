"""
SQLAlchemy ORM models matching the database schema from plan.md section 2.

These models provide the complete data layer for the Ordinaut,
including agents, tasks, task runs, work queuing, and audit logging.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Text, 
    ARRAY, BigInteger, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class ScheduleKind(enum.Enum):
    """Schedule types supported by the orchestrator."""
    cron = "cron"
    rrule = "rrule" 
    once = "once"
    event = "event"
    condition = "condition"


class Agent(Base):
    """
    Agents that can create and manage tasks.
    Each agent has scopes that determine which tools they can access.
    """
    __tablename__ = "agent"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name = Column(Text, nullable=False, unique=True)
    scopes = Column(ARRAY(Text), nullable=False)
    webhook_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    tasks = relationship("Task", back_populates="creator", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="actor_agent")

    def __repr__(self):
        return f"<Agent(id={self.id}, name='{self.name}', scopes={self.scopes})>"


class Task(Base):
    """
    Scheduled tasks with declarative pipeline payloads.
    Tasks define WHAT to do, WHEN to do it, and HOW to handle failures.
    """
    __tablename__ = "task"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=False)
    schedule_kind = Column(SQLEnum(ScheduleKind), nullable=False)
    schedule_expr = Column(Text, nullable=True)  # cron/rrule/ISO timestamp/event topic
    timezone = Column(Text, nullable=False, default="Europe/Chisinau")
    payload = Column(JSONB, nullable=False)  # declarative pipeline
    status = Column(Text, nullable=False, default="active")  # active|paused|canceled
    priority = Column(Integer, nullable=False, default=5)  # 1..9
    dedupe_key = Column(Text, nullable=True)
    dedupe_window_seconds = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    backoff_strategy = Column(Text, nullable=False, default="exponential_jitter")
    concurrency_key = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    creator = relationship("Agent", back_populates="tasks")
    runs = relationship("TaskRun", back_populates="task", cascade="all, delete-orphan")
    due_work_items = relationship("DueWork", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Task(id={self.id}, title='{self.title}', status='{self.status}')>"


class TaskRun(Base):
    """
    Execution records for task runs.
    Tracks success/failure, timing, output, and retry attempts.
    """
    __tablename__ = "task_run"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    task_id = Column(UUID(as_uuid=True), ForeignKey("task.id"), nullable=False)
    lease_owner = Column(Text, nullable=True)
    leased_until = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    success = Column(Boolean, nullable=True)
    error = Column(Text, nullable=True)
    attempt = Column(Integer, nullable=False, default=1)
    output = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    task = relationship("Task", back_populates="runs")

    def __repr__(self):
        return f"<TaskRun(id={self.id}, task_id={self.task_id}, success={self.success}, attempt={self.attempt})>"


class DueWork(Base):
    """
    Work items to decouple scheduling from execution.
    Workers lease items safely using SELECT ... FOR UPDATE SKIP LOCKED.
    """
    __tablename__ = "due_work"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(UUID(as_uuid=True), ForeignKey("task.id"), nullable=False)
    run_at = Column(DateTime(timezone=True), nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    task = relationship("Task", back_populates="due_work_items")

    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_due_work_run_at", "run_at"),
        Index("ix_due_work_task_id", "task_id"),
    )

    def __repr__(self):
        return f"<DueWork(id={self.id}, task_id={self.task_id}, run_at={self.run_at}, locked_by='{self.locked_by}')>"


class AuditLog(Base):
    """
    Immutable audit trail for all orchestrator operations.
    Provides complete accountability and debugging capabilities.
    """
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    actor_agent_id = Column(UUID(as_uuid=True), ForeignKey("agent.id"), nullable=True)
    action = Column(Text, nullable=False)
    subject_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(JSONB, nullable=True)
    at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    actor_agent = relationship("Agent", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', actor_agent_id={self.actor_agent_id})>"