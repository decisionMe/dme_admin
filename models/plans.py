# models/plan.py
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from py_db.db import Base

class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    price = Column(Float)
    billing_cycle = Column(String)  # monthly, annually, etc.
    max_decisions = Column(Integer)
    max_team_members = Column(Integer)
    has_ai_features = Column(Boolean, default=False)
    has_analytics = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")
