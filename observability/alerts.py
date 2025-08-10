"""
Alert rule definitions and management for Ordinaut.

Implements alerting rules from plan.md section 11 requirements:
- task_run.success=false ratio > 0.2 over 10 minutes
- Oldest due_work run_at lag > 30 seconds (scheduler stalled)
- Worker heartbeats missing (emit worker.heartbeat every 10s)
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any, Callable, Union
from sqlalchemy import create_engine, text
import os

from .logging import StructuredLogger, set_request_context
from .metrics import OrchestrationMetrics


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertState(Enum):
    """Alert state enumeration."""
    OK = "ok"
    PENDING = "pending"
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    description: str
    severity: AlertSeverity
    query: str  # SQL query or metric expression
    threshold: Union[float, int]
    duration_seconds: int  # How long condition must be true
    comparison: str = ">"  # >, <, >=, <=, ==, !=
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None
    enabled: bool = True
    
    def __post_init__(self):
        if self.labels is None:
            self.labels = {}
        if self.annotations is None:
            self.annotations = {}


@dataclass
class Alert:
    """Active alert instance."""
    rule_name: str
    severity: AlertSeverity
    state: AlertState
    value: float
    threshold: Union[float, int]
    started_at: datetime
    last_updated: datetime
    resolved_at: Optional[datetime] = None
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None
    
    def __post_init__(self):
        if self.labels is None:
            self.labels = {}
        if self.annotations is None:
            self.annotations = {}


class AlertRuleManager:
    """Manages alert rules and evaluates conditions."""
    
    def __init__(self, database_url: str = None, metrics: OrchestrationMetrics = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self.metrics = metrics
        self.logger = StructuredLogger("orchestrator.alerts")
        
        # Alert state tracking
        self.active_alerts: Dict[str, Alert] = {}
        self.rule_last_evaluated: Dict[str, datetime] = {}
        
        # Database connection for alert queries
        if self.database_url:
            self.db_engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                future=True,
                pool_size=2,
                max_overflow=0
            )
        else:
            self.db_engine = None
        
        # Initialize core alert rules from plan.md
        self.rules = self._create_core_rules()
        
        self.logger.info(f"Alert rule manager initialized with {len(self.rules)} rules")
    
    def _create_core_rules(self) -> List[AlertRule]:
        """Create core alert rules per plan.md section 11 requirements."""
        
        rules = [
            # Task failure rate alert (plan.md requirement)
            AlertRule(
                name="HighTaskFailureRate",
                description="Task failure rate exceeds 20% over 10 minutes",
                severity=AlertSeverity.ERROR,
                query="""
                    SELECT 
                        COALESCE(
                            (COUNT(*) FILTER (WHERE NOT success))::float / 
                            NULLIF(COUNT(*), 0), 
                            0
                        ) as failure_rate
                    FROM task_run 
                    WHERE started_at > now() - interval '10 minutes'
                """,
                threshold=0.2,
                duration_seconds=300,  # 5 minutes of sustained high failure
                comparison=">",
                labels={"alert_type": "task_failure"},
                annotations={
                    "summary": "High task failure rate detected",
                    "description": "More than 20% of task executions are failing over the last 10 minutes",
                    "runbook_url": "https://docs.orchestrator.example.com/runbooks/high-failure-rate"
                }
            ),
            
            # Scheduler lag alert (plan.md requirement)
            AlertRule(
                name="SchedulerLagHigh",
                description="Oldest due work is more than 30 seconds overdue",
                severity=AlertSeverity.WARNING,
                query="""
                    SELECT COALESCE(
                        EXTRACT(EPOCH FROM (now() - MIN(run_at))), 
                        0
                    ) as lag_seconds
                    FROM due_work 
                    WHERE run_at <= now()
                """,
                threshold=30,
                duration_seconds=60,  # 1 minute of sustained lag
                comparison=">",
                labels={"alert_type": "scheduler_lag"},
                annotations={
                    "summary": "Scheduler lag detected",
                    "description": "Work items are not being processed within expected timeframes",
                    "runbook_url": "https://docs.orchestrator.example.com/runbooks/scheduler-lag"
                }
            ),
            
            # Critical scheduler lag alert
            AlertRule(
                name="SchedulerLagCritical", 
                description="Oldest due work is more than 5 minutes overdue",
                severity=AlertSeverity.CRITICAL,
                query="""
                    SELECT COALESCE(
                        EXTRACT(EPOCH FROM (now() - MIN(run_at))), 
                        0
                    ) as lag_seconds
                    FROM due_work 
                    WHERE run_at <= now()
                """,
                threshold=300,  # 5 minutes
                duration_seconds=60,
                comparison=">",
                labels={"alert_type": "scheduler_lag_critical"},
                annotations={
                    "summary": "Critical scheduler lag detected",
                    "description": "Work items are severely delayed - immediate attention required",
                    "runbook_url": "https://docs.orchestrator.example.com/runbooks/scheduler-lag"
                }
            ),
            
            # Worker heartbeat missing alert (plan.md requirement)
            AlertRule(
                name="WorkerHeartbeatMissing",
                description="No worker heartbeats received in last 30 seconds",
                severity=AlertSeverity.ERROR,
                query="""
                    SELECT COUNT(DISTINCT worker_id) as active_workers
                    FROM worker_heartbeat 
                    WHERE last_heartbeat > now() - interval '30 seconds'
                """,
                threshold=1,
                duration_seconds=120,  # 2 minutes without workers
                comparison="<",
                labels={"alert_type": "worker_missing"},
                annotations={
                    "summary": "No active workers detected",
                    "description": "No worker processes are sending heartbeats - task processing may be stalled",
                    "runbook_url": "https://docs.orchestrator.example.com/runbooks/worker-missing"
                }
            ),
            
            # Queue depth alert
            AlertRule(
                name="HighQueueDepth",
                description="Due work queue depth is very high",
                severity=AlertSeverity.WARNING,
                query="""
                    SELECT COUNT(*) as queue_depth
                    FROM due_work 
                    WHERE run_at <= now()
                """,
                threshold=100,
                duration_seconds=300,  # 5 minutes
                comparison=">",
                labels={"alert_type": "high_queue_depth"},
                annotations={
                    "summary": "High work queue depth",
                    "description": "Work queue has grown very large - may indicate processing issues",
                    "runbook_url": "https://docs.orchestrator.example.com/runbooks/high-queue-depth"
                }
            ),
            
            # Database connection alert
            AlertRule(
                name="DatabaseConnectionsHigh",
                description="Database connection count is very high",
                severity=AlertSeverity.WARNING,
                query="""
                    SELECT numbackends as connection_count
                    FROM pg_stat_database 
                    WHERE datname = current_database()
                """,
                threshold=50,
                duration_seconds=300,
                comparison=">",
                labels={"alert_type": "database_connections"},
                annotations={
                    "summary": "High database connection count",
                    "description": "Database connection pool may be exhausted",
                    "runbook_url": "https://docs.orchestrator.example.com/runbooks/database-connections"
                }
            ),
            
            # Long-running tasks alert
            AlertRule(
                name="LongRunningTasks", 
                description="Tasks running for more than 10 minutes",
                severity=AlertSeverity.WARNING,
                query="""
                    SELECT COUNT(*) as long_running_count
                    FROM due_work 
                    WHERE locked_until > now() 
                      AND locked_until - now() < interval '50 minutes'
                      AND run_at < now() - interval '10 minutes'
                """,
                threshold=5,
                duration_seconds=300,
                comparison=">",
                labels={"alert_type": "long_running_tasks"},
                annotations={
                    "summary": "Long-running tasks detected",
                    "description": "Multiple tasks have been running for more than 10 minutes",
                    "runbook_url": "https://docs.orchestrator.example.com/runbooks/long-running-tasks"
                }
            ),
            
            # Failed pipeline steps alert
            AlertRule(
                name="HighPipelineStepFailures",
                description="High rate of pipeline step failures",
                severity=AlertSeverity.WARNING,
                query="""
                    SELECT 
                        COALESCE(
                            (COUNT(*) FILTER (WHERE NOT success))::float / 
                            NULLIF(COUNT(*), 0), 
                            0
                        ) as step_failure_rate
                    FROM task_run 
                    WHERE started_at > now() - interval '15 minutes'
                      AND output::text LIKE '%"success": false%'
                """,
                threshold=0.15,  # 15% step failure rate
                duration_seconds=300,
                comparison=">",
                labels={"alert_type": "pipeline_step_failures"},
                annotations={
                    "summary": "High pipeline step failure rate",
                    "description": "Many pipeline steps are failing - check external tool connectivity",
                    "runbook_url": "https://docs.orchestrator.example.com/runbooks/pipeline-failures"
                }
            )
        ]
        
        return rules
    
    def add_rule(self, rule: AlertRule):
        """Add a new alert rule."""
        self.rules.append(rule)
        self.logger.info(f"Added alert rule: {rule.name}", rule_name=rule.name)
    
    def remove_rule(self, rule_name: str):
        """Remove an alert rule."""
        self.rules = [r for r in self.rules if r.name != rule_name]
        
        # Clean up any active alerts for this rule
        if rule_name in self.active_alerts:
            del self.active_alerts[rule_name]
        
        self.logger.info(f"Removed alert rule: {rule_name}", rule_name=rule_name)
    
    def enable_rule(self, rule_name: str):
        """Enable an alert rule."""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = True
                self.logger.info(f"Enabled alert rule: {rule_name}", rule_name=rule_name)
                break
    
    def disable_rule(self, rule_name: str):
        """Disable an alert rule."""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = False
                
                # Resolve any active alerts for disabled rule
                if rule_name in self.active_alerts:
                    alert = self.active_alerts[rule_name]
                    alert.state = AlertState.RESOLVED
                    alert.resolved_at = datetime.now(timezone.utc)
                
                self.logger.info(f"Disabled alert rule: {rule_name}", rule_name=rule_name)
                break
    
    async def evaluate_rule(self, rule: AlertRule) -> Optional[float]:
        """Evaluate a single alert rule and return the current value."""
        if not rule.enabled or not self.db_engine:
            return None
        
        try:
            with self.db_engine.begin() as conn:
                result = conn.execute(text(rule.query)).fetchone()
                
                if result is None:
                    return None
                
                # Get the first column value
                value = list(result)[0]
                return float(value) if value is not None else 0.0
                
        except Exception as e:
            self.logger.error(
                f"Failed to evaluate alert rule {rule.name}: {e}",
                rule_name=rule.name,
                exception=str(e)
            )
            return None
    
    def _should_fire_alert(self, rule: AlertRule, value: float) -> bool:
        """Determine if alert condition is met."""
        comparisons = {
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b, 
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b
        }
        
        compare_func = comparisons.get(rule.comparison)
        if not compare_func:
            self.logger.error(f"Invalid comparison operator: {rule.comparison}", rule_name=rule.name)
            return False
        
        return compare_func(value, rule.threshold)
    
    def _update_alert_state(self, rule: AlertRule, value: float, should_fire: bool):
        """Update alert state based on current evaluation."""
        now = datetime.now(timezone.utc)
        rule_name = rule.name
        
        current_alert = self.active_alerts.get(rule_name)
        
        if should_fire:
            if current_alert is None:
                # New alert condition - start pending
                self.active_alerts[rule_name] = Alert(
                    rule_name=rule_name,
                    severity=rule.severity,
                    state=AlertState.PENDING,
                    value=value,
                    threshold=rule.threshold,
                    started_at=now,
                    last_updated=now,
                    labels=rule.labels.copy(),
                    annotations=rule.annotations.copy()
                )
                
                self.logger.warning(
                    f"Alert condition detected: {rule_name}",
                    rule_name=rule_name,
                    value=value,
                    threshold=rule.threshold,
                    state="pending"
                )
                
            elif current_alert.state == AlertState.PENDING:
                # Check if condition has been true long enough to fire
                duration = (now - current_alert.started_at).total_seconds()
                
                if duration >= rule.duration_seconds:
                    current_alert.state = AlertState.FIRING
                    current_alert.last_updated = now
                    
                    self.logger.error(
                        f"Alert FIRING: {rule_name}",
                        rule_name=rule_name,
                        value=value,
                        threshold=rule.threshold,
                        duration_seconds=duration,
                        severity=rule.severity.value
                    )
                    
                    # Trigger alert notification
                    self._trigger_alert_notification(current_alert, rule)
                else:
                    # Still pending
                    current_alert.value = value
                    current_alert.last_updated = now
                
            elif current_alert.state == AlertState.FIRING:
                # Continue firing - update value
                current_alert.value = value
                current_alert.last_updated = now
                
        else:
            # Condition not met
            if current_alert and current_alert.state in [AlertState.PENDING, AlertState.FIRING]:
                # Resolve the alert
                current_alert.state = AlertState.RESOLVED
                current_alert.resolved_at = now
                current_alert.last_updated = now
                
                was_firing = current_alert.state == AlertState.FIRING
                
                self.logger.info(
                    f"Alert resolved: {rule_name}",
                    rule_name=rule_name,
                    was_firing=was_firing,
                    duration_seconds=(now - current_alert.started_at).total_seconds()
                )
                
                if was_firing:
                    # Trigger resolved notification
                    self._trigger_resolved_notification(current_alert, rule)
                
                # Remove from active alerts after a delay
                # Keep resolved alerts for a bit for observability
                # Could be moved to a separate resolved_alerts dict
    
    def _trigger_alert_notification(self, alert: Alert, rule: AlertRule):
        """Trigger alert notification (placeholder for integration points)."""
        # This is where you would integrate with:
        # - Slack/Discord notifications
        # - Email alerts
        # - PagerDuty/OpsGenie
        # - Webhook notifications
        
        notification_data = {
            "alert_name": alert.rule_name,
            "severity": alert.severity.value,
            "state": alert.state.value,
            "value": alert.value,
            "threshold": alert.threshold,
            "started_at": alert.started_at.isoformat(),
            "description": rule.description,
            "labels": alert.labels,
            "annotations": alert.annotations
        }
        
        self.logger.critical(
            "ALERT NOTIFICATION",
            alert_name=alert.rule_name,
            notification_data=notification_data,
            event_type="alert_notification"
        )
    
    def _trigger_resolved_notification(self, alert: Alert, rule: AlertRule):
        """Trigger resolved notification."""
        duration_seconds = (alert.resolved_at - alert.started_at).total_seconds()
        
        self.logger.info(
            "ALERT RESOLVED NOTIFICATION",
            alert_name=alert.rule_name,
            duration_seconds=duration_seconds,
            event_type="alert_resolved_notification"
        )
    
    async def evaluate_all_rules(self):
        """Evaluate all enabled alert rules."""
        now = datetime.now(timezone.utc)
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            try:
                value = await self.evaluate_rule(rule)
                if value is not None:
                    should_fire = self._should_fire_alert(rule, value)
                    self._update_alert_state(rule, value, should_fire)
                    
                    # Update metrics if available
                    if self.metrics:
                        # Record alert evaluation metrics here
                        pass
                
                self.rule_last_evaluated[rule.name] = now
                
            except Exception as e:
                self.logger.error(
                    f"Failed to evaluate rule {rule.name}: {e}",
                    rule_name=rule.name,
                    exception=str(e)
                )
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all currently active alerts."""
        return [
            alert for alert in self.active_alerts.values()
            if alert.state in [AlertState.PENDING, AlertState.FIRING]
        ]
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get summary of alert system status."""
        active_alerts = self.get_active_alerts()
        
        return {
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules if r.enabled]),
            "active_alerts": len(active_alerts),
            "firing_alerts": len([a for a in active_alerts if a.state == AlertState.FIRING]),
            "pending_alerts": len([a for a in active_alerts if a.state == AlertState.PENDING]),
            "last_evaluation": max(self.rule_last_evaluated.values()) if self.rule_last_evaluated else None,
            "alert_details": [
                {
                    "rule_name": alert.rule_name,
                    "severity": alert.severity.value,
                    "state": alert.state.value,
                    "value": alert.value,
                    "threshold": alert.threshold,
                    "started_at": alert.started_at.isoformat() + 'Z'
                }
                for alert in active_alerts
            ]
        }
    
    async def start_monitoring(self, interval_seconds: int = 30):
        """Start continuous alert monitoring loop."""
        self.logger.info(
            f"Starting alert monitoring with {interval_seconds}s interval",
            interval_seconds=interval_seconds,
            total_rules=len(self.rules)
        )
        
        while True:
            try:
                await self.evaluate_all_rules()
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                self.logger.error(f"Alert monitoring loop error: {e}", exception=str(e))
                await asyncio.sleep(interval_seconds)  # Continue despite errors