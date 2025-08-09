#!/usr/bin/env python3
"""
Personal Agent Orchestrator - APScheduler Service
Scheduler that reads task definitions and creates due_work rows for worker processing.

This is the temporal brain of the orchestrator:
- Reads active tasks from PostgreSQL
- Schedules jobs using APScheduler with SQLAlchemyJobStore 
- Supports cron, RRULE, once, event, and condition scheduling
- Creates due_work rows for safe concurrent worker processing
- Handles timezone-aware scheduling with Europe/Chisinau default
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from dateutil.parser import parse as parse_date

from engine.rruler import next_occurrence, RRuleProcessingError, RRuleValidationError
from engine.registry import load_active_tasks

# Import observability components
from observability.metrics import orchestrator_metrics
from observability.logging import scheduler_logger, set_request_context, generate_request_id

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
structured_logger = scheduler_logger

# Environment configuration
DEFAULT_TIMEZONE = os.environ.get("TZ", "Europe/Chisinau")

class SchedulerService:
    """APScheduler service for Personal Agent Orchestrator."""
    
    def __init__(self, database_url: str, timezone: str = DEFAULT_TIMEZONE):
        """Initialize scheduler service.
        
        Args:
            database_url: PostgreSQL connection string
            timezone: Default timezone for scheduling
        """
        self.database_url = database_url
        self.timezone = timezone
        self.scheduler = None
        self.engine = None
        self._shutdown = False
        
        # Set up database engine
        self._setup_database()
        
        # Set up APScheduler
        self._setup_scheduler()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _setup_database(self):
        """Set up database engine with connection pooling."""
        self.engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            future=True,
            pool_size=5,
            max_overflow=10
        )
        logger.info("Database engine initialized")
    
    def _setup_scheduler(self):
        """Set up APScheduler with SQLAlchemy job store."""
        
        # Configure job store
        jobstores = {
            'default': SQLAlchemyJobStore(url=self.database_url)
        }
        
        # Configure job defaults
        job_defaults = {
            'coalesce': True,           # Combine missed executions
            'max_instances': 1,         # Prevent concurrent job instances
            'misfire_grace_time': 30    # Grace period for late jobs
        }
        
        self.scheduler = BlockingScheduler(
            jobstores=jobstores,
            job_defaults=job_defaults,
            timezone=self.timezone
        )
        
        logger.info(f"APScheduler initialized with timezone: {self.timezone}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self._shutdown = True
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
    
    def enqueue_due_work(self, task_id: str, scheduled_time: datetime = None):
        """
        Create a due_work row for worker processing.
        
        This is the callback function executed by APScheduler when jobs fire.
        It creates work items in the due_work table that workers can lease safely
        using FOR UPDATE SKIP LOCKED.
        
        Args:
            task_id: UUID of the task to execute
            scheduled_time: When the task was scheduled to run (for logging)
        """
        enqueue_start_time = time.time()
        run_at = scheduled_time or datetime.now(timezone.utc)
        
        # Calculate scheduler lag (how late we are)
        if scheduled_time:
            lag_seconds = (datetime.now(timezone.utc) - scheduled_time).total_seconds()
            orchestrator_metrics.update_scheduler_lag(lag_seconds)
        
        try:
            with self.engine.begin() as conn:
                # Insert due work item with conflict handling
                result = conn.execute(text("""
                    INSERT INTO due_work (task_id, run_at)
                    VALUES (:task_id, :run_at)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                """), {
                    "task_id": task_id,
                    "run_at": run_at
                })
                
                work_created = result.fetchone() is not None
            
            if work_created:
                logger.info(f"Enqueued due work for task {task_id} at {run_at}")
                
                # Record scheduler job creation metrics
                orchestrator_metrics.record_scheduler_job_created("job_fired")
                
                # Log with structured logging
                structured_logger.info(
                    "Due work enqueued",
                    task_id=task_id,
                    scheduled_time=scheduled_time.isoformat() + 'Z' if scheduled_time else None,
                    run_at=run_at.isoformat() + 'Z',
                    lag_seconds=lag_seconds if scheduled_time else 0,
                    event_type="due_work_enqueued"
                )
            else:
                # Duplicate work item - already exists
                logger.debug(f"Due work for task {task_id} already exists, skipping")
            
            # For RRULE tasks, schedule the next occurrence
            self._reschedule_rrule_task_if_needed(task_id)
            
        except Exception as e:
            # Record scheduler error metrics
            orchestrator_metrics.record_scheduler_tick("error")
            
            # Log error with structured logging
            structured_logger.error(
                f"Failed to enqueue due work for task {task_id}",
                task_id=task_id,
                scheduled_time=scheduled_time.isoformat() + 'Z' if scheduled_time else None,
                error=str(e),
                event_type="enqueue_failed"
            )
            
            logger.error(f"Failed to enqueue due work for task {task_id}: {e}")
            raise
    
    def _reschedule_rrule_task_if_needed(self, task_id: str):
        """Reschedule RRULE task for its next occurrence."""
        try:
            with self.engine.begin() as conn:
                # Get task details
                task_row = conn.execute(text("""
                    SELECT schedule_kind, schedule_expr, timezone
                    FROM task 
                    WHERE id = :task_id AND status = 'active'
                """), {"task_id": task_id}).fetchone()
                
                if not task_row:
                    return
                
                if task_row.schedule_kind != 'rrule':
                    return
                
                # Calculate next occurrence
                next_time = next_occurrence(
                    task_row.schedule_expr,
                    task_row.timezone or self.timezone
                )
                
                if next_time:
                    # Schedule next occurrence
                    job_id = f"rrule-{task_id}"
                    
                    self.scheduler.add_job(
                        self.enqueue_due_work,
                        DateTrigger(run_date=next_time, timezone=next_time.tzinfo),
                        args=[task_id, next_time],
                        id=job_id,
                        replace_existing=True,
                        name=f"RRULE Task: {task_id}"
                    )
                    
                    logger.info(f"Rescheduled RRULE task {task_id} for {next_time}")
                
        except Exception as e:
            logger.error(f"Failed to reschedule RRULE task {task_id}: {e}")
    
    def schedule_task_job(self, task: Dict[str, Any]):
        """
        Schedule a job for a task based on its schedule_kind.
        
        Args:
            task: Task dictionary from database
        """
        task_id = task["id"]
        schedule_kind = task["schedule_kind"]
        schedule_expr = task["schedule_expr"]
        task_timezone = task.get("timezone", self.timezone)
        title = task.get('title', 'Unnamed Task')
        
        logger.info(f"Scheduling task {task_id} ({schedule_kind}): {title}")
        
        # Set request context for logging
        request_id = generate_request_id()
        set_request_context(request_id=request_id, task_id=task_id)
        
        schedule_start_time = time.time()
        
        try:
            if schedule_kind == "cron":
                self._schedule_cron_task(task_id, schedule_expr, task_timezone)
            
            elif schedule_kind == "once":
                self._schedule_once_task(task_id, schedule_expr, task_timezone)
            
            elif schedule_kind == "rrule":
                self._schedule_rrule_task(task_id, schedule_expr, task_timezone)
            
            elif schedule_kind in ("event", "condition"):
                # Event and condition tasks are handled by external systems
                # They enqueue work directly via API endpoints
                logger.info(f"Task {task_id} is {schedule_kind}-triggered, no scheduler job needed")
            
            else:
                logger.warning(f"Unknown schedule_kind '{schedule_kind}' for task {task_id}")
                raise ValueError(f"Unsupported schedule_kind: {schedule_kind}")
            
            # Record successful task scheduling
            orchestrator_metrics.record_scheduler_job_created(schedule_kind)
            
            schedule_duration = time.time() - schedule_start_time
            
            # Log successful scheduling
            structured_logger.info(
                f"Task scheduled successfully",
                task_id=task_id,
                title=title,
                schedule_kind=schedule_kind,
                schedule_expr=schedule_expr,
                timezone=task_timezone,
                schedule_duration_ms=schedule_duration * 1000,
                event_type="task_scheduled"
            )
        
        except Exception as e:
            schedule_duration = time.time() - schedule_start_time
            
            # Record failed scheduling metrics
            orchestrator_metrics.record_scheduler_tick("schedule_error")
            
            # Log scheduling failure
            structured_logger.error(
                f"Failed to schedule task {task_id}",
                task_id=task_id,
                title=title,
                schedule_kind=schedule_kind,
                schedule_expr=schedule_expr,
                timezone=task_timezone,
                schedule_duration_ms=schedule_duration * 1000,
                error=str(e),
                event_type="task_schedule_failed"
            )
            
            logger.error(f"Failed to schedule task {task_id}: {e}")
            raise
    
    def _schedule_cron_task(self, task_id: str, cron_expr: str, task_timezone: str):
        """Schedule a cron-based task."""
        try:
            # Parse cron expression (assuming 5-field format: minute hour day month day_of_week)
            fields = cron_expr.split()
            if len(fields) != 5:
                raise ValueError(f"Cron expression must have 5 fields, got {len(fields)}: {cron_expr}")
            
            minute, hour, day, month, day_of_week = fields
            
            # Create cron trigger
            trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone=task_timezone
            )
            
            job_id = f"cron-{task_id}"
            
            self.scheduler.add_job(
                self.enqueue_due_work,
                trigger,
                args=[task_id],
                id=job_id,
                replace_existing=True,
                name=f"Cron Task: {task_id}"
            )
            
            logger.info(f"Scheduled cron task {task_id}: {cron_expr} in {task_timezone}")
            
        except Exception as e:
            logger.error(f"Failed to schedule cron task {task_id}: {e}")
            raise
    
    def _schedule_once_task(self, task_id: str, date_expr: str, task_timezone: str):
        """Schedule a one-time task."""
        try:
            # Parse date expression
            run_date = parse_date(date_expr)
            
            # Ensure timezone awareness
            if run_date.tzinfo is None:
                import pytz
                tz = pytz.timezone(task_timezone)
                run_date = tz.localize(run_date)
            
            # Only schedule if in the future
            if run_date <= datetime.now(timezone.utc):
                logger.warning(f"Once task {task_id} scheduled for past date {run_date}, skipping")
                return
            
            trigger = DateTrigger(run_date=run_date, timezone=run_date.tzinfo)
            job_id = f"once-{task_id}"
            
            self.scheduler.add_job(
                self.enqueue_due_work,
                trigger,
                args=[task_id, run_date],
                id=job_id,
                replace_existing=True,
                name=f"Once Task: {task_id}"
            )
            
            logger.info(f"Scheduled once task {task_id} for {run_date}")
            
        except Exception as e:
            logger.error(f"Failed to schedule once task {task_id}: {e}")
            raise
    
    def _schedule_rrule_task(self, task_id: str, rrule_expr: str, task_timezone: str):
        """Schedule an RRULE-based task."""
        try:
            # Calculate next occurrence
            next_time = next_occurrence(rrule_expr, task_timezone)
            
            if not next_time:
                logger.warning(f"RRULE task {task_id} has no future occurrences: {rrule_expr}")
                return
            
            # Schedule as one-time job (will reschedule after execution)
            trigger = DateTrigger(run_date=next_time, timezone=next_time.tzinfo)
            job_id = f"rrule-{task_id}"
            
            self.scheduler.add_job(
                self.enqueue_due_work,
                trigger,
                args=[task_id, next_time],
                id=job_id,
                replace_existing=True,
                name=f"RRULE Task: {task_id}"
            )
            
            logger.info(f"Scheduled RRULE task {task_id} for {next_time} (expression: {rrule_expr})")
            
        except (RRuleValidationError, RRuleProcessingError) as e:
            logger.error(f"Invalid RRULE for task {task_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to schedule RRULE task {task_id}: {e}")
            raise
    
    def load_and_schedule_tasks(self):
        """Load active tasks from database and schedule them."""
        load_start_time = time.time()
        
        try:
            logger.info("Loading active tasks from database")
            
            # Load tasks using registry function
            tasks = load_active_tasks(self.database_url)
            
            logger.info(f"Found {len(tasks)} active tasks")
            
            # Schedule each task
            scheduled_count = 0
            failed_count = 0
            
            for task in tasks:
                try:
                    self.schedule_task_job(task)
                    scheduled_count += 1
                except Exception as e:
                    logger.error(f"Failed to schedule task {task['id']}: {e}")
                    failed_count += 1
            
            load_duration = time.time() - load_start_time
            
            # Record scheduler tick success
            orchestrator_metrics.record_scheduler_tick("success")
            
            # Log task loading summary
            structured_logger.info(
                f"Task loading completed",
                total_tasks=len(tasks),
                scheduled_count=scheduled_count,
                failed_count=failed_count,
                load_duration_seconds=load_duration,
                event_type="tasks_loaded"
            )
            
            logger.info(f"Scheduled {scheduled_count} tasks, {failed_count} failed in {load_duration:.2f}s")
            
        except Exception as e:
            load_duration = time.time() - load_start_time
            
            # Record scheduler error
            orchestrator_metrics.record_scheduler_tick("load_error")
            
            # Log loading failure
            structured_logger.error(
                f"Failed to load tasks from database",
                load_duration_seconds=load_duration,
                error=str(e),
                event_type="tasks_load_failed"
            )
            
            logger.error(f"Failed to load tasks from database: {e}")
            raise
    
    def run(self):
        """Run the scheduler service."""
        try:
            logger.info("Starting Personal Agent Orchestrator Scheduler")
            
            # Load and schedule existing tasks
            self.load_and_schedule_tasks()
            
            # Print scheduled jobs for debugging
            jobs = self.scheduler.get_jobs()
            logger.info(f"Active jobs: {len(jobs)}")
            for job in jobs[:10]:  # Log first 10 jobs
                logger.info(f"  - {job.name} (next: {job.next_run_time})")
            
            # Start scheduler (blocking)
            logger.info("Starting APScheduler")
            self.scheduler.start()
            
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            raise
        finally:
            if self.scheduler and self.scheduler.running:
                logger.info("Shutting down scheduler")
                self.scheduler.shutdown(wait=True)
            
            if self.engine:
                logger.info("Closing database connections")
                self.engine.dispose()


def main():
    """Main entry point for scheduler service."""
    try:
        # Get database URL from environment
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL environment variable is required")
            sys.exit(1)
        
        logger.info(f"Using database URL: {database_url}")
        
        # Create and run scheduler service
        service = SchedulerService(database_url, DEFAULT_TIMEZONE)
        service.run()
        
    except Exception as e:
        logger.error(f"Fatal error in scheduler service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()