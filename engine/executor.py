# engine/executor.py
import json
import logging
import time
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from jsonschema import validate, ValidationError
import jmespath

from engine.template import render_templates, TemplateRenderError
# TODO: Tool calling removed - will be implemented as extensions
# from engine.registry import load_catalog, get_tool
# from engine.mcp_client import call_tool

# Import observability components
from observability.metrics import orchestrator_metrics, track_step_execution
from observability.logging import (
    pipeline_logger, set_request_context, generate_step_id,
    log_function_call
)

logger = logging.getLogger(__name__)
structured_logger = pipeline_logger

class PipelineExecutionError(Exception):
    """Exception raised during pipeline execution."""
    def __init__(self, message: str, step_id: Optional[str] = None, step_index: Optional[int] = None, cause: Optional[Exception] = None):
        self.step_id = step_id
        self.step_index = step_index
        self.cause = cause
        super().__init__(message)

class StepValidationError(PipelineExecutionError):
    """Exception raised when step input/output validation fails."""
    pass

class ConditionEvaluationError(PipelineExecutionError):
    """Exception raised when step condition evaluation fails."""
    pass

def _eval_condition(expr: str, ctx: dict) -> bool:
    """
    Evaluate JMESPath boolean expression for step conditions.
    
    Args:
        expr: JMESPath expression that should evaluate to boolean
        ctx: Context dictionary containing steps, params, and now
        
    Returns:
        Boolean result of expression evaluation
        
    Raises:
        ConditionEvaluationError: If expression evaluation fails
    """
    try:
        result = jmespath.search(expr, ctx)
        if result is None:
            logger.warning(f"Condition expression '{expr}' returned None, treating as False")
            return False
        return bool(result)
    except Exception as e:
        raise ConditionEvaluationError(
            f"Failed to evaluate condition '{expr}': {e}",
            cause=e
        )

def _validate_step(step: dict, step_index: int) -> None:
    """
    Validate step structure before execution.
    
    Args:
        step: Step dictionary to validate
        step_index: Index of step in pipeline
        
    Raises:
        PipelineExecutionError: If step structure is invalid
    """
    if not isinstance(step, dict):
        raise PipelineExecutionError(
            f"Step {step_index} must be a dictionary, got {type(step).__name__}",
            step_index=step_index
        )
    
    if "uses" not in step:
        raise PipelineExecutionError(
            f"Step {step_index} missing required 'uses' field",
            step_id=step.get("id"),
            step_index=step_index
        )
    
    if not isinstance(step["uses"], str) or not step["uses"].strip():
        raise PipelineExecutionError(
            f"Step {step_index} 'uses' field must be a non-empty string",
            step_id=step.get("id"),
            step_index=step_index
        )

def _validate_pipeline_structure(pipeline: Any) -> None:
    """
    Validate overall pipeline structure.
    
    Args:
        pipeline: Pipeline structure to validate
        
    Raises:
        PipelineExecutionError: If pipeline structure is invalid
    """
    if not isinstance(pipeline, list):
        raise PipelineExecutionError(
            f"Pipeline must be a list, got {type(pipeline).__name__}"
        )
    
    if len(pipeline) == 0:
        logger.warning("Pipeline is empty - no steps to execute")
        return
    
    # Check for duplicate step IDs
    step_ids = [step.get("id") for step in pipeline if step.get("id")]
    if len(step_ids) != len(set(step_ids)):
        duplicates = [sid for sid in set(step_ids) if step_ids.count(sid) > 1]
        raise PipelineExecutionError(
            f"Duplicate step IDs found: {duplicates}"
        )

def _build_execution_context(task: dict) -> dict:
    """
    Build initial execution context from task data.
    
    Args:
        task: Task dictionary containing payload and metadata
        
    Returns:
        Initial execution context dictionary
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = task.get("payload", {})
    params = payload.get("params", {})
    
    # Add task metadata to context for debugging
    context = {
        "now": now_iso,
        "params": params,
        "steps": {},
        "_task_id": task.get("id"),
        "_task_title": task.get("title"),
        "_execution_start": now_iso
    }
    
    logger.debug(f"Built execution context with {len(params)} params")
    return context

def _execute_step(step: dict, step_index: int, catalog: List[Dict], ctx: dict) -> Optional[Any]:
    """
    Execute a single pipeline step.
    
    Args:
        step: Step dictionary to execute
        step_index: Index of step in pipeline  
        catalog: Tool catalog
        ctx: Execution context
        
    Returns:
        Step execution result or None if step was skipped
        
    Raises:
        PipelineExecutionError: If step execution fails
    """
    step_id = step.get("id", f"step_{step_index}")
    step_unique_id = generate_step_id(step_id)
    step_start_time = time.time()
    
    # Set logging context for step execution
    set_request_context(step_id=step_unique_id)
    
    # Get tool address for metrics
    tool_addr = step['uses']
    task_id = ctx.get('_task_id', 'unknown')
    
    logger.info(f"Executing step '{step_id}' ({step_index + 1}) - {tool_addr}")
    
    # Log step start with structured logging
    structured_logger.pipeline_step_started(
        step_id=step_unique_id,
        tool_address=tool_addr
    )
    
    success = False
    error_type = None
    
    try:
        # Evaluate condition if present
        if "if" in step:
            condition_result = _eval_condition(step["if"], ctx)
            if not condition_result:
                logger.info(f"Step '{step_id}' skipped due to condition: {step['if']}")
                return None
        
        # Get tool address for simulation
        addr = step["uses"]
        
        # Render input templates (keep template processing)
        step_input = step.get("with", {})
        try:
            rendered_args = render_templates(step_input, ctx)
        except TemplateRenderError as e:
            error_type = "TemplateRenderError"
            raise PipelineExecutionError(
                f"Step '{step_id}' template rendering failed: {e}",
                step_id=step_id,
                step_index=step_index,
                cause=e
            )
        
        # SIMULATE tool execution (tools removed from core system)
        timeout = step.get("timeout_seconds", 30)
        tool_start_time = time.time()
        
        # Log what would be called
        logger.info(f"SIMULATED tool call: {addr} with args: {rendered_args}")
        
        # Create mock result for pipeline processing
        result = {
            "status": "simulated",
            "tool_address": addr,
            "input_args": rendered_args,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": f"Tool execution simulated - tools will be implemented as extensions"
        }
        
        # Record simulated tool call metrics
        tool_duration = time.time() - tool_start_time
        orchestrator_metrics.record_external_tool_call(
            tool_address=addr,
            method='simulated',
            status_code=200,  # Success
            duration=tool_duration
        )
        
        # Log simulated tool call
        structured_logger.external_tool_call(
            tool_address=addr,
            method='simulated',
            status_code=200,
            duration_ms=tool_duration * 1000
        )
        
        # Save result if requested
        if "save_as" in step:
            save_key = step["save_as"]
            if not isinstance(save_key, str) or not save_key.strip():
                raise PipelineExecutionError(
                    f"Step '{step_id}' save_as must be a non-empty string",
                    step_id=step_id,
                    step_index=step_index
                )
            
            ctx["steps"][save_key] = result
            logger.debug(f"Step '{step_id}' result saved as '{save_key}'")
        
        execution_time = time.time() - step_start_time
        success = True
        
        # Record step metrics
        orchestrator_metrics.record_step_execution(
            tool_addr=tool_addr,
            step_id=step_unique_id,
            task_id=task_id,
            duration=execution_time,
            success=True
        )
        
        # Log step completion
        structured_logger.pipeline_step_completed(
            step_id=step_unique_id,
            tool_address=tool_addr,
            success=True,
            duration_ms=execution_time * 1000
        )
        
        logger.info(f"Step '{step_id}' completed successfully in {execution_time:.2f}s")
        
        return result
        
    except PipelineExecutionError:
        # Re-raise pipeline errors as-is (already have proper error_type)
        raise
    except Exception as e:
        # Wrap unexpected errors
        error_type = e.__class__.__name__
        raise PipelineExecutionError(
            f"Step '{step_id}' failed with unexpected error: {e}",
            step_id=step_id,
            step_index=step_index,
            cause=e
        )
        
    finally:
        # Always record step metrics, even on failure
        if not success:
            execution_time = time.time() - step_start_time
            orchestrator_metrics.record_step_execution(
                tool_addr=tool_addr,
                step_id=step_unique_id,
                task_id=task_id,
                duration=execution_time,
                success=False,
                error_type=error_type
            )
            
            # Log step failure
            structured_logger.pipeline_step_completed(
                step_id=step_unique_id,
                tool_address=tool_addr,
                success=False,
                duration_ms=execution_time * 1000
            )

@log_function_call(pipeline_logger, level=logging.INFO)
def run_pipeline(task: dict) -> dict:
    """
    Execute a declarative pipeline with strict validation and error handling.
    
    This is the main entry point for pipeline execution, called by workers.
    Implements deterministic execution with comprehensive error handling,
    template rendering, and JSON schema validation.
    
    Args:
        task: Task dictionary containing:
            - payload.pipeline: List of step dictionaries
            - payload.params: Parameters for template rendering
            - id, title: Task metadata (optional)
    
    Returns:
        Execution context containing:
            - now: ISO timestamp of execution start
            - params: Original parameters
            - steps: Results from executed steps (keyed by save_as)
            - _task_id, _task_title, _execution_start: Metadata
            - _execution_summary: Summary of execution
    
    Raises:
        PipelineExecutionError: If pipeline execution fails
        StepValidationError: If step input/output validation fails
        ConditionEvaluationError: If condition evaluation fails
    
    Example:
        task = {
            "id": "abc-123",
            "title": "Morning Briefing",
            "payload": {
                "params": {"date": "2025-08-08"},
                "pipeline": [
                    {
                        "id": "weather",
                        "uses": "weather-mcp.forecast",
                        "with": {"date": "${params.date}"},
                        "save_as": "forecast"
                    },
                    {
                        "id": "notify",
                        "uses": "telegram-mcp.send_message",
                        "with": {"text": "Weather: ${steps.forecast.summary}"}
                    }
                ]
            }
        }
        
        result = run_pipeline(task)
        print(result["steps"]["forecast"])  # Weather forecast data
    """
    execution_start = time.time()
    
    # Extract task metadata
    task_id = task.get('id', 'unknown')
    task_title = task.get('title', 'Unnamed Task')
    
    # Set logging context
    set_request_context(task_id=task_id)
    
    # Extract and validate payload
    if not isinstance(task, dict):
        raise PipelineExecutionError(f"Task must be a dictionary, got {type(task).__name__}")
    
    payload = task.get("payload")
    if not isinstance(payload, dict):
        raise PipelineExecutionError("Task payload must be a dictionary")
    
    pipeline = payload.get("pipeline")
    if pipeline is None:
        raise PipelineExecutionError("Task payload missing 'pipeline' field")
    
    # Validate pipeline structure
    _validate_pipeline_structure(pipeline)
    
    # Build execution context
    ctx = _build_execution_context(task)
    
    # TODO: Tool catalog loading removed - tools will be implemented as extensions
    catalog = []  # Empty catalog - no tools available in core system
    
    logger.info(f"Starting pipeline execution for task '{task_id}' ({task_title}) with {len(pipeline)} steps")
    
    # Record pipeline execution start
    orchestrator_metrics.record_pipeline_execution(task_id, "started")
    
    executed_steps = 0
    skipped_steps = 0
    pipeline_success = False
    
    try:
        # Execute pipeline steps
        for step_index, step in enumerate(pipeline):
            try:
                # Validate step structure
                _validate_step(step, step_index)
                
                # Execute step
                result = _execute_step(step, step_index, catalog, ctx)
                
                if result is not None:
                    executed_steps += 1
                else:
                    skipped_steps += 1
                    
            except Exception as e:
                # Add execution summary to context for debugging
                execution_time = time.time() - execution_start
                ctx["_execution_summary"] = {
                    "success": False,
                    "total_steps": len(pipeline),
                    "executed_steps": executed_steps,
                    "skipped_steps": skipped_steps,
                    "failed_step_index": step_index,
                    "execution_time_seconds": execution_time,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
                
                # Record failed pipeline execution
                orchestrator_metrics.record_pipeline_execution(task_id, "failed")
                
                # Log pipeline failure with structured logging
                structured_logger.error(
                    f"Pipeline execution failed for task {task_id} at step {step_index + 1}/{len(pipeline)}",
                    task_id=task_id,
                    failed_step_index=step_index,
                    executed_steps=executed_steps,
                    total_steps=len(pipeline),
                    execution_time_seconds=execution_time,
                    error=str(e)
                )
                
                logger.error(f"Pipeline execution failed at step {step_index + 1}/{len(pipeline)}: {e}")
                raise
        
        # Add successful execution summary
        execution_time = time.time() - execution_start
        ctx["_execution_summary"] = {
            "success": True,
            "total_steps": len(pipeline),
            "executed_steps": executed_steps,
            "skipped_steps": skipped_steps,
            "execution_time_seconds": execution_time
        }
        
        pipeline_success = True
        
        # Record successful pipeline execution
        orchestrator_metrics.record_pipeline_execution(task_id, "success")
        
        # Log successful pipeline completion
        structured_logger.info(
            f"Pipeline execution completed successfully for task {task_id}",
            task_id=task_id,
            task_title=task_title,
            executed_steps=executed_steps,
            skipped_steps=skipped_steps,
            total_steps=len(pipeline),
            execution_time_seconds=execution_time
        )
        
        logger.info(f"Pipeline execution completed successfully: {executed_steps} executed, {skipped_steps} skipped, {execution_time:.2f}s")
        
        return ctx
        
    finally:
        # Always record final metrics
        if not pipeline_success:
            # Record failed pipeline if we haven't already
            try:
                orchestrator_metrics.record_pipeline_execution(task_id, "failed")
            except:
                pass  # Don't let metrics recording errors mask the original error

def validate_pipeline(pipeline_definition: dict) -> List[str]:
    """
    Validate a pipeline definition without executing it.
    
    Args:
        pipeline_definition: Pipeline definition to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    try:
        # Check payload structure
        if not isinstance(pipeline_definition, dict):
            errors.append("Pipeline definition must be a dictionary")
            return errors
        
        payload = pipeline_definition.get("payload", {})
        pipeline = payload.get("pipeline")
        
        if pipeline is None:
            errors.append("Pipeline definition missing 'payload.pipeline' field")
            return errors
        
        # Validate pipeline structure
        _validate_pipeline_structure(pipeline)
        
        # Validate each step
        for step_index, step in enumerate(pipeline):
            try:
                _validate_step(step, step_index)
            except PipelineExecutionError as e:
                errors.append(str(e))
        
        # TODO: Tool availability checking removed - tools will be implemented as extensions
        # All pipeline steps with "uses" will be simulated during execution
        for step_index, step in enumerate(pipeline):
            addr = step.get("uses")
            if addr:
                logger.debug(f"Step {step_index} will simulate tool '{addr}' during execution")
    
    except Exception as e:
        errors.append(f"Unexpected validation error: {e}")
    
    return errors

def get_pipeline_metrics(execution_context: dict) -> dict:
    """
    Extract execution metrics from pipeline execution context.
    
    Args:
        execution_context: Result of run_pipeline() call
        
    Returns:
        Dictionary containing execution metrics
    """
    summary = execution_context.get("_execution_summary", {})
    
    return {
        "success": summary.get("success", False),
        "total_steps": summary.get("total_steps", 0),
        "executed_steps": summary.get("executed_steps", 0),
        "skipped_steps": summary.get("skipped_steps", 0),
        "execution_time_seconds": summary.get("execution_time_seconds", 0),
        "steps_per_second": (
            summary.get("executed_steps", 0) / max(summary.get("execution_time_seconds", 1), 0.001)
        ),
        "error": summary.get("error"),
        "failed_step_index": summary.get("failed_step_index"),
        "task_id": execution_context.get("_task_id"),
        "task_title": execution_context.get("_task_title")
    }