# engine/registry.py
"""
Database Registry for Ordinaut

Provides database query functions for the scheduler and other core components.
Tool catalog functionality has been removed - tools will be implemented as extensions.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def load_active_tasks(db_url: str) -> List[Dict[str, Any]]:
    """Load active tasks from database for scheduler."""
    from sqlalchemy import create_engine, text
    
    try:
        eng = create_engine(db_url, pool_pre_ping=True, future=True)
        with eng.begin() as cx:
            rows = cx.execute(text("SELECT * FROM task WHERE status = 'active'")).mappings().fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to load active tasks: {e}")
        return []