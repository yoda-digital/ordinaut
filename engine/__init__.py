"""
Ordinaut Engine Module

This module provides the core execution engine, including:
- Pipeline execution with template rendering
- RRULE processing and validation
- Database registry functions
"""

from .rruler import next_occurrence, validate_rrule_syntax
from .registry import load_active_tasks

__version__ = "2.1.0"

__all__ = [
    'next_occurrence',
    'validate_rrule_syntax', 
    'load_active_tasks'
]