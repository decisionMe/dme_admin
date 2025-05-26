from sqlalchemy import Column, String, DateTime, Enum
from sqlalchemy.sql import func
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Base

class SubscriptionUser(Base):
    __tablename__ = "subscription_users"

    subscription_id = Column(String, primary_key=True, index=True)
    email = Column(String, nullable=True)
    purchaser_email = Column(String, nullable=True)
    auth0_id = Column(String, nullable=True, index=True)
    registration_status = Column(
        Enum("PAYMENT_COMPLETED", "AUTH0_INVITE_SENT", "AUTH0_ACCOUNT_LINKED", name="registration_status"),
        default="PAYMENT_COMPLETED"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())