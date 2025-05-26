# services/monitoring_service.py

"""
Service for logging subscription validation events and monitoring.
"""

from sqlalchemy.orm import Session
from models.subscription_event import SubscriptionEvent, EventType, EventStatus
import logging
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger("monitoring_service")


class MonitoringService:
    """Service for logging and monitoring subscription events"""
    
    @staticmethod
    def log_validation_check(
        db: Session,
        user_id: str,
        user_email: str,
        is_valid: bool,
        stripe_customer_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> SubscriptionEvent:
        """Log a subscription validation check"""
        try:
            event = SubscriptionEvent(
                event_type=EventType.VALIDATION_CHECK,
                event_status=EventStatus.SUCCESS if is_valid else EventStatus.FAILURE,
                user_id=user_id,
                user_email=user_email,
                stripe_customer_id=stripe_customer_id,
                details=json.dumps(details) if details else None
            )
            db.add(event)
            db.commit()
            
            logger.info(f"Logged validation check for user {user_email}: {'valid' if is_valid else 'invalid'}")
            return event
            
        except Exception as e:
            logger.error(f"Failed to log validation check: {e}")
            db.rollback()
            raise
    
    @staticmethod
    def log_stripe_api_call(
        db: Session,
        endpoint: str,
        success: bool,
        response_time_ms: float,
        user_id: Optional[str] = None,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> SubscriptionEvent:
        """Log a Stripe API call"""
        try:
            event = SubscriptionEvent(
                event_type=EventType.STRIPE_API_CALL,
                event_status=EventStatus.SUCCESS if success else EventStatus.FAILURE,
                user_id=user_id,
                details=json.dumps({
                    "endpoint": endpoint,
                    **(details or {})
                }),
                error_message=error_message,
                response_time_ms=response_time_ms
            )
            db.add(event)
            db.commit()
            
            logger.info(f"Logged Stripe API call to {endpoint}: {'success' if success else 'failure'} ({response_time_ms}ms)")
            return event
            
        except Exception as e:
            logger.error(f"Failed to log Stripe API call: {e}")
            db.rollback()
            raise
    
    @staticmethod
    def log_redirect(
        db: Session,
        user_id: str,
        user_email: str,
        redirect_url: str,
        reason: str = "subscription_invalid"
    ) -> SubscriptionEvent:
        """Log when a user is redirected due to invalid subscription"""
        try:
            event = SubscriptionEvent(
                event_type=EventType.REDIRECT,
                event_status=EventStatus.SUCCESS,
                user_id=user_id,
                user_email=user_email,
                details=json.dumps({
                    "redirect_url": redirect_url,
                    "reason": reason
                })
            )
            db.add(event)
            db.commit()
            
            logger.info(f"Logged redirect for user {user_email} to {redirect_url}")
            return event
            
        except Exception as e:
            logger.error(f"Failed to log redirect: {e}")
            db.rollback()
            raise
    
    @staticmethod
    def log_error(
        db: Session,
        error_type: str,
        error_message: str,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> SubscriptionEvent:
        """Log an error event"""
        try:
            event = SubscriptionEvent(
                event_type=EventType.ERROR,
                event_status=EventStatus.ERROR,
                user_id=user_id,
                user_email=user_email,
                error_message=f"{error_type}: {error_message}",
                details=json.dumps(details) if details else None
            )
            db.add(event)
            db.commit()
            
            logger.error(f"Logged error event: {error_type} - {error_message}")
            return event
            
        except Exception as e:
            logger.error(f"Failed to log error event: {e}")
            db.rollback()
            raise


class StripeAPITimer:
    """Context manager for timing Stripe API calls"""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
    
    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0