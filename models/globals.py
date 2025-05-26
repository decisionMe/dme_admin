# models/globals.py

"""
GlobalConfig model for storing application-wide settings.

IMPORTANT: Database migrations for this model are managed in the d-me project.
DO NOT create or run Alembic migrations in this project (dme_admin).
The dme_admin and d-me projects share the same database.

To add new fields to this model:
1. Add the fields here in dme_admin/models/globals.py
2. Create and run the migration from the d-me project:
   cd ../d-me
   alembic revision --autogenerate -m "add subscription validation fields to global_config"
   alembic upgrade head
"""

from sqlalchemy import Boolean, Column, String, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class GlobalConfig(Base):
    __tablename__ = 'global_config'

    id = Column(Boolean, primary_key=True, default=True)
    current_ai = Column(String)
    current_model = Column(String)

    # Subscription validation settings
    # NOTE: These fields must be added via migration in the d-me project
    subscription_validation_enabled = Column(Boolean, default=False)
    subscription_landing_page_url = Column(String, nullable=True)

    # Enforce single row
    __table_args__ = (
        CheckConstraint('id IS TRUE', name='ensure_only_one_row'),
    )

    @classmethod
    def get(cls, session):
        """Helper method to get the singleton instance"""
        return session.query(cls).first()