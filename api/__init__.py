"""
Ordinaut FastAPI Application.

This package provides the complete REST API for the Ordinaut,
including task management, execution monitoring, event publishing, and agent authentication.

Main components:
- main: FastAPI application with middleware and error handling
- models: SQLAlchemy ORM models for database entities
- schemas: Pydantic models for request/response validation
- routes: API route definitions organized by functionality
- dependencies: Reusable dependencies for database and authentication
"""

__version__ = "1.7.0"