"""
Ordinaut Scheduler Module

This module provides the APScheduler-based scheduling service for the
Ordinaut system.
"""

from .tick import SchedulerService

__version__ = "1.8.1"

__all__ = ['SchedulerService']