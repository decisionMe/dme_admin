# models/subscription_event.py

"""
Model for tracking subscription validation events.

IMPORTANT: Database migrations for this model are managed in the d-me project.
DO NOT create or run Alembic migrations in this project (dme_admin).
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Enum, Float
from sqlalchemy.sql import func
from database import Base
import enum


class EventType(enum.Enum):
    """Types of subscription events"""
    VALIDATION_CHECK = "validation_check"
    STRIPE_API_CALL = "stripe_api_call"
    REDIRECT = "redirect"
    ERROR = "error"


class EventStatus(enum.Enum):
    """Status of events"""
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"


class SubscriptionEvent(Base):
    """Track subscription validation events for monitoring"""
    __tablename__ = 'subscription_events'
    
    id = Column(Integer, primary_key=True)
    event_type = Column(Enum(EventType), nullable=False)
    event_status = Column(Enum(EventStatus), nullable=False)
    user_id = Column(String, nullable=True)  # Auth0 user ID
    user_email = Column(String, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    
    # Event details
    details = Column(Text, nullable=True)  # JSON string for additional details
    error_message = Column(Text, nullable=True)
    
    # Performance metrics
    response_time_ms = Column(Float, nullable=True)  # For API calls
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Indexing for performance
    __table_args__ = (
        # Add indexes for common queries
        # These will be created via migration in d-me project
    )
    
    @classmethod
    def log_validation_check(cls, db_session, user_id, user_email, is_valid, details=None):
        """Log a subscription validation check"""
        event = cls(
            event_type=EventType.VALIDATION_CHECK,
            event_status=EventStatus.SUCCESS if is_valid else EventStatus.FAILURE,
            user_id=user_id,
            user_email=user_email,
            details=details
        )
        db_session.add(event)
        db_session.commit()
        return event
    
    @classmethod
    def log_stripe_api_call(cls, db_session, endpoint, success, response_time_ms, 
                           user_id=None, error_message=None, details=None):
        """Log a Stripe API call"""
        event = cls(
            event_type=EventType.STRIPE_API_CALL,
            event_status=EventStatus.SUCCESS if success else EventStatus.FAILURE,
            user_id=user_id,
            details=details,
            error_message=error_message,
            response_time_ms=response_time_ms
        )
        db_session.add(event)
        db_session.commit()
        return event
    
    @classmethod
    def log_redirect(cls, db_session, user_id, user_email, redirect_url):
        """Log when a user is redirected due to invalid subscription"""
        event = cls(
            event_type=EventType.REDIRECT,
            event_status=EventStatus.SUCCESS,
            user_id=user_id,
            user_email=user_email,
            details=f'{{"redirect_url": "{redirect_url}"}}'
        )
        db_session.add(event)
        db_session.commit()
        return event