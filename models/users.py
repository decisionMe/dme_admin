# models/users.py
from sqlalchemy import Column, String, Boolean, DateTime, JSON, Integer, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Session
from datetime import datetime
from typing import Dict, Any, Optional
from py_db.db import Base

DEBUG = False

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # We use Auth0 ID as the primary key

    @classmethod
    def get_by_firebase_uid(cls, db: Session, firebase_uid: str):
        """Get a user by their Firebase UID (which is stored in the id field)"""
        return db.query(cls).filter(cls.id == firebase_uid).first()

    @classmethod
    def get_by_auth0_id(cls, db: Session, auth0_id: str):
        """Get a user by their Auth0 ID (which is stored in the id field)"""
        return db.query(cls).filter(cls.id == auth0_id).first()

    @classmethod
    def create_from_firebase(cls, db: Session, user_record):
        """Create a new user from a Firebase user record"""
        user = cls(
            id=user_record.uid,
            email=user_record.email,
            email_verified=user_record.email_verified,
            auth_provider="firebase",
            is_active=True,
            account_filled=False,
            terms_accepted=False
        )
        db.add(user)
        return user

    @classmethod
    def create_from_auth0(cls, db: Session, user_info: Dict[str, Any]):
        """Create a new user from Auth0 user information"""
        from py_config.logging_config import get_logger
        logger = get_logger('auth')

        if DEBUG:
            logger.info(f"USER CREATION: create_from_auth0 called with user_info: {user_info}")

        # Extract the Auth0 unique identifier
        auth0_id = user_info.get("auth0_id") or user_info.get("sub")


        if DEBUG:
            logger.info(f"USER CREATION: Creating new user with auth0_id: {auth0_id}")

        if not auth0_id:
            logger.error("USER CREATION: No auth0_id found in user_info!")
            return None

        if not user_info.get("email"):
            logger.error("USER CREATION: No email found in user_info!")
            return None

        try:
            # Create a new user with Auth0 data
            user = cls(
                id=auth0_id,  # Use Auth0 ID as primary key for new users
                email=user_info.get("email", ""),
                email_verified=user_info.get("email_verified", False),
                auth_provider="auth0",
                is_active=True,
                account_filled=False,
                terms_accepted=False,
                last_active=datetime.now()
            )

            logger.info(f"USER CREATION: User object created with id={user.id}, email={user.email}")

            # Set name if available
            if "name" in user_info and user_info["name"]:
                # Try to extract first and last name
                name_parts = user_info["name"].split(" ", 1)
                if len(name_parts) >= 1:
                    user.first_name = name_parts[0]
                if len(name_parts) >= 2:
                    user.last_name = name_parts[1]
                logger.info(f"USER CREATION: Set name: first_name={user.first_name}, last_name={user.last_name}")

            # If there's a picture URL, we could store it in preferences
            if "picture" in user_info and user_info["picture"]:
                user.preferences = user.preferences or {}
                user.preferences["profile_picture"] = user_info["picture"]
                logger.info(f"USER CREATION: Set profile picture URL")

            logger.info(f"USER CREATION: Adding user to database session")
            db.add(user)

            # Note: We don't commit here - the caller (find_or_create_from_auth0) will commit

            return user

        except Exception as e:
            logger.error(f"USER CREATION: Error creating user: {str(e)}")
            db.rollback()
            raise

    @classmethod
    def find_or_create_from_auth0(cls, db: Session, user_info: Dict[str, Any]) -> "User":
        """Find existing user or create a new one from Auth0 profile"""
        from py_config.logging_config import get_logger
        logger = get_logger('auth')

        # Log incoming user info
        if DEBUG:
            logger.info(f"USER CREATION: find_or_create_from_auth0 called with user_info: {user_info}")

        # Extract Auth0 ID
        auth0_id = user_info.get("auth0_id") or user_info.get("sub")

        if DEBUG:
            logger.info(f"USER CREATION: Extracted auth0_id: {auth0_id}")

        # Try to find by Auth0 ID first
        user = cls.get_by_auth0_id(db, auth0_id)
        if user:
            if DEBUG:
                logger.info(f"USER CREATION: Found existing user by auth0_id: {user.id}, email: {user.email}")
            # Update last active time
            user.last_active = datetime.now()
            db.commit()
            if DEBUG:
                logger.info(f"USER CREATION: Updated last_active for user {user.id}")
            return user

        # If not found by Auth0 ID, try by email
        email = user_info.get("email")
        logger.info(f"USER CREATION: Looking up by email: {email}")
        if email:
            user = db.query(cls).filter(cls.email == email).first()
            if user:
                if DEBUG:
                    logger.info(f"USER CREATION: Found existing user by email: {user.id}")

                # Important: Update ID to match Auth0 ID
                old_id = user.id
                logger.info(f"USER CREATION: User ID migration: {old_id} -> {auth0_id}")

                # Update user with Auth0 information
                user.id = auth0_id  # This will cascade to all related tables thanks to onupdate="CASCADE"
                user.auth_provider = "auth0"
                user.last_active = datetime.now()

                # Add details from Auth0 profile if available
                if "name" in user_info and user_info["name"]:
                    # Try to extract first and last name
                    name_parts = user_info["name"].split(" ", 1)
                    if len(name_parts) >= 1:
                        user.first_name = name_parts[0]
                    if len(name_parts) >= 2:
                        user.last_name = name_parts[1]
                    logger.info(f"USER CREATION: Updated name: first_name={user.first_name}, last_name={user.last_name}")

                # If there's a picture URL, store it in preferences
                if "picture" in user_info and user_info["picture"]:
                    user.preferences = user.preferences or {}
                    user.preferences["profile_picture"] = user_info["picture"]
                    logger.info(f"USER CREATION: Updated profile picture URL")

                # Commit the changes to cascade the ID update
                db.commit()
                logger.info(f"USER CREATION: Updated user ID from {old_id} to {auth0_id} with CASCADE")
                return user

        # Create new user if not found
        logger.info(f"USER CREATION: User not found, creating new user with auth0_id: {auth0_id}, email: {email}")
        user = cls.create_from_auth0(db, user_info)
        logger.info(f"USER CREATION: Created new user with ID: {user.id}")
        # Important: make sure we commit the new user
        db.commit()
        logger.info(f"USER CREATION: Committed new user to database")
        return user

    team_id = Column(Integer, ForeignKey("teams.id"))
    email = Column(String, unique=True, nullable=False)
    first_name = Column(String)
    middle_initial = Column(String)
    last_name = Column(String)
    name_suffix = Column(String)
    phone = Column(String)
    phone_type = Column(String)
    title = Column(String)
    zip_code = Column(String)
    age_range = Column(String)
    auth_provider = Column(String)
    face_id_enabled = Column(Boolean, default=False)
    two_factor_enabled = Column(Boolean, default=False)
    terms_accepted = Column(Boolean, default=False)
    terms_accepted_date = Column(DateTime(timezone=False))
    account_filled = Column(Boolean, default=False)
    account_filled_date = Column(DateTime(timezone=False))
    is_active = Column(Boolean, default=True)
    last_active = Column(DateTime(timezone=False))
    email_verified = Column(Boolean, default=False)
    preferences = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    team = relationship("Team", back_populates="users")
    decisions = relationship("Decisions", back_populates="user")
    company_admin_roles = relationship("CompanyAdmin", back_populates="user")
    team_admin_roles = relationship("TeamAdmin", back_populates="user")
    decision_participations = relationship("DecisionParticipants", back_populates="user")
    subscriptions = relationship("Subscription",
                               back_populates="user",
                               primaryjoin="User.id==Subscription.user_id")