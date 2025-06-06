# models/subscription.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id"))
    user_id = Column(String, ForeignKey("subscription_users.subscription_id", onupdate="CASCADE"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    start_date = Column(DateTime(timezone=True), server_default=func.now())
    end_date = Column(DateTime(timezone=True))
    status = Column(String)  # active, canceled, expired, etc.
    payment_status = Column(String)
    payment_method = Column(String)
    last_payment_date = Column(DateTime(timezone=True))
    next_payment_date = Column(DateTime(timezone=True))
    auto_renew = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Note: Relationships are commented out since we don't have these models in dme_admin
    # plan = relationship("Plan", back_populates="subscriptions")
    # user = relationship("User", back_populates="subscriptions")
    # company = relationship("Company", back_populates="subscriptions")