# engine/template.py
import re
import json
import logging
from typing import Any, Dict, List, Union

import jmespath

logger = logging.getLogger(__name__)

class TemplateRenderError(Exception):
    """Exception raised when template rendering fails."""
    def __init__(self, message: str, expression: str = None, cause: Exception = None):
        self.expression = expression
        self.cause = cause
        super().__init__(message)

# Pattern for variable substitution: ${variable.path}
_TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")

def _safe_jmespath_search(expression: str, data: dict) -> Any:
    """
    Safely evaluate JMESPath expression with detailed error handling.
    
    Args:
        expression: JMESPath expression to evaluate
        data: Data dictionary to search
        
    Returns:
        Result of JMESPath search or None if expression is invalid/not found
        
    Raises:
        TemplateRenderError: If expression evaluation fails
    """
    try:
        result = jmespath.search(expression, data)
        return result
    except Exception as e:
        raise TemplateRenderError(
            f"Failed to evaluate JMESPath expression '{expression}': {e}",
            expression=expression,
            cause=e
        )

def _render_string_template(template_str: str, context: dict) -> str:
    """
    Render template variables in a string.
    
    Args:
        template_str: String containing ${variable} expressions
        context: Context dictionary for variable resolution
        
    Returns:
        String with all variables resolved
        
    Raises:
        TemplateRenderError: If template rendering fails
    """
    if not isinstance(template_str, str):
        return template_str
    
    def replace_variable(match):
        expression = match.group(1).strip()
        
        if not expression:
            raise TemplateRenderError(
                "Empty variable expression found: ${}",
                expression=""
            )
        
        try:
            result = _safe_jmespath_search(expression, context)
            
            if result is None:
                # Check if this was a valid path that just returned null
                # vs an invalid path that doesn't exist
                logger.warning(f"Variable expression '${{{expression}}}' resolved to None")
                return "null"
            
            # Convert result to string, handling different types appropriately
            if isinstance(result, bool):
                return "true" if result else "false"
            elif isinstance(result, (dict, list)):
                return json.dumps(result)
            else:
                return str(result)
                
        except TemplateRenderError:
            # Re-raise template errors as-is
            raise
        except Exception as e:
            raise TemplateRenderError(
                f"Failed to render variable '${{{expression}}}': {e}",
                expression=expression,
                cause=e
            )
    
    try:
        return _TEMPLATE_PATTERN.sub(replace_variable, template_str)
    except Exception as e:
        if isinstance(e, TemplateRenderError):
            raise
        raise TemplateRenderError(
            f"Template rendering failed for string '{template_str[:100]}...': {e}",
            cause=e
        )

def render_templates(obj: Any, ctx: dict) -> Any:
    """
    Recursively render template variables in nested data structures.
    
    This function traverses dictionaries, lists, and strings, replacing
    ${variable.path} expressions with values from the context dictionary
    using JMESPath syntax.
    
    Args:
        obj: Object to render (dict, list, string, or other)
        ctx: Context dictionary containing variables for substitution
        
    Returns:
        Object with all template variables resolved
        
    Raises:
        TemplateRenderError: If template rendering fails
        
    Examples:
        >>> ctx = {
        ...     "params": {"name": "John", "age": 30},
        ...     "steps": {"weather": {"temp": 25, "units": "C"}}
        ... }
        >>> 
        >>> # Simple variable substitution
        >>> render_templates("Hello ${params.name}", ctx)
        "Hello John"
        >>> 
        >>> # Nested object access
        >>> render_templates("Temperature: ${steps.weather.temp}°${steps.weather.units}", ctx)
        "Temperature: 25°C"
        >>> 
        >>> # Complex nested structure
        >>> template = {
        ...     "message": "Hello ${params.name}, you are ${params.age} years old",
        ...     "conditions": ["${steps.weather.temp > `20`}", "${params.age >= `18`}"]
        ... }
        >>> render_templates(template, ctx)
        {
            "message": "Hello John, you are 30 years old",
            "conditions": ["true", "true"]
        }
    """
    if ctx is None:
        logger.warning("Template rendering called with None context, using empty dict")
        ctx = {}
    
    if not isinstance(ctx, dict):
        raise TemplateRenderError(f"Context must be a dictionary, got {type(ctx).__name__}")
    
    try:
        if isinstance(obj, dict):
            return {key: render_templates(value, ctx) for key, value in obj.items()}
        
        elif isinstance(obj, list):
            return [render_templates(item, ctx) for item in obj]
        
        elif isinstance(obj, str):
            return _render_string_template(obj, ctx)
        
        else:
            # Return non-template types as-is (numbers, booleans, None, etc.)
            return obj
            
    except TemplateRenderError:
        # Re-raise template errors as-is
        raise
    except Exception as e:
        raise TemplateRenderError(
            f"Unexpected error during template rendering: {e}",
            cause=e
        )

def extract_template_variables(obj: Any) -> List[str]:
    """
    Extract all template variable expressions from a data structure.
    
    Args:
        obj: Object to scan for template variables
        
    Returns:
        List of unique variable expressions found (without ${} delimiters)
        
    Examples:
        >>> template = {
        ...     "name": "${params.user_name}",
        ...     "message": "Weather is ${steps.weather.condition} (${steps.weather.temp}°F)",
        ...     "nested": ["${params.location}", "${steps.calendar.events[0].title}"]
        ... }
        >>> extract_template_variables(template)
        ['params.user_name', 'steps.weather.condition', 'steps.weather.temp', 
         'params.location', 'steps.calendar.events[0].title']
    """
    variables = set()
    
    def _scan_object(obj):
        if isinstance(obj, dict):
            for value in obj.values():
                _scan_object(value)
        elif isinstance(obj, list):
            for item in obj:
                _scan_object(item)
        elif isinstance(obj, str):
            matches = _TEMPLATE_PATTERN.findall(obj)
            for match in matches:
                variables.add(match.strip())
    
    _scan_object(obj)
    return sorted(list(variables))

def validate_template_variables(variables: Union[List[str], Any], context: dict) -> List[str]:
    """
    Validate that template variables can be resolved in context.
    
    Args:
        variables: List of variable expressions, or object containing template variables
        context: Context dictionary for variable resolution
        
    Returns:
        List of missing/invalid variable expressions (empty if all valid)
    """
    if isinstance(variables, list):
        # Called with list of variable expressions
        var_list = variables
    else:
        # Called with object containing template variables
        var_list = extract_template_variables(variables)
    
    missing = []
    
    for var_expr in var_list:
        try:
            result = _safe_jmespath_search(var_expr, context)
            # Check if the path exists in the context
            if result is None:
                # Need to check if this is a missing path or a valid path that's null
                if _is_path_missing(var_expr, context):
                    missing.append(var_expr)
        except Exception:
            # Any exception means the variable is invalid/missing
            missing.append(var_expr)
    
    return missing

def _is_path_missing(path: str, context: dict) -> bool:
    """
    Check if a JMESPath expression refers to a missing path in the context.
    
    Args:
        path: JMESPath expression to check
        context: Context dictionary
        
    Returns:
        True if path is missing, False if path exists but is null/empty
    """
    try:
        # Split the path into components
        parts = path.replace('[', '.').replace(']', '').split('.')
        current = context
        
        for part in parts:
            if not part:  # Empty part from splitting
                continue
            
            # Handle array indices
            if part.isdigit():
                idx = int(part)
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return True  # Index out of bounds or not a list
            else:
                # Handle object keys
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return True  # Key doesn't exist
        
        return False  # Path exists (even if value is None)
        
    except Exception:
        return True  # Any error means the path is invalid

def preview_template_rendering(obj: Any, context: dict) -> Dict[str, Any]:
    """
    Preview template rendering without actually performing it.
    
    Args:
        obj: Object to preview rendering for
        context: Context dictionary for variable resolution
        
    Returns:
        Dictionary containing:
            - variables: List of template variables found
            - resolutions: Dict mapping variables to their resolved values
            - errors: List of resolution errors
            - would_succeed: Boolean indicating if rendering would succeed
    """
    variables = extract_template_variables(obj)
    resolutions = {}
    errors = []
    
    for var_expr in variables:
        try:
            result = _safe_jmespath_search(var_expr, context)
            resolutions[var_expr] = result
        except TemplateRenderError as e:
            errors.append(f"Variable '{var_expr}': {e}")
        except Exception as e:
            errors.append(f"Variable '{var_expr}': Unexpected error - {e}")
    
    return {
        "variables": variables,
        "resolutions": resolutions,
        "errors": errors,
        "would_succeed": len(errors) == 0
    }