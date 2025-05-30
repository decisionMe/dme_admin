# auth0_subscription_handler.py
# Standalone Auth0 callback handler for subscription processing
# Copy this file to the main app project

import logging
import jwt
import os
import stripe
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

# Configure logging
logger = logging.getLogger("auth0_subscription_handler")

# You'll need to configure these for the main app:
# - Database session dependency
# - SubscriptionUser model import
# - Auth0 service functions
# - APP_URL configuration

def create_auth0_subscription_router(
    get_db_session,  # Database session dependency function
    subscription_user_model,  # SubscriptionUser model class
    exchange_code_for_tokens_func,  # Auth0 token exchange function
    app_url: str,  # Main app URL for redirects
    admin_db_session=None  # Optional: for cross-database access to admin config
):
    """
    Factory function to create Auth0 subscription callback router

    Args:
        get_db_session: Function that returns database session
        subscription_user_model: SubscriptionUser SQLAlchemy model
        exchange_code_for_tokens_func: Function to exchange Auth0 code for tokens
        app_url: Base URL of the main application
        admin_db_session: Optional session for admin database access
    """

    router = APIRouter(prefix="/subscription", tags=["subscription"])

    @router.get("/auth/callback")
    async def auth0_callback(
        code: str,
        state: str,
        db: Session = Depends(get_db_session)
    ):
        """Handler for Auth0 callback after authentication"""
        logger.info(f"Received Auth0 callback with state: {state}")

        try:
            # Exchange code for tokens
            logger.debug(f"Exchanging authorization code for tokens")
            token_data = await exchange_code_for_tokens_func(code)
            logger.debug(f"Received token data with keys: {', '.join(token_data.keys())}")

            # Get subscription_id from state parameter
            subscription_id = state
            logger.info(f"Processing Auth0 callback for subscription {subscription_id}")

            # Decode ID token to get user info
            id_token = token_data["id_token"]
            logger.debug(f"Decoding ID token")
            user_info = jwt.decode(
                id_token,
                options={"verify_signature": False}
            )
            logger.debug(f"ID token decoded, subject: {user_info.get('sub')}")

            # Update user record with Auth0 ID
            user = db.query(subscription_user_model).filter(
                subscription_user_model.subscription_id == subscription_id
            ).first()

            if not user:
                logger.error(f"User not found for subscription {subscription_id}")
                return RedirectResponse(url=f"{app_url}/error?reason=user_not_found")

            logger.info(f"Updating user record with Auth0 ID {user_info['sub']}")

            user.auth0_id = user_info["sub"]
            if "email" in user_info:
                user.email = user_info["email"]
                logger.debug(f"Updated user email to {user_info['email']}")
            user.registration_status = "AUTH0_ACCOUNT_LINKED"
            db.commit()
            logger.debug(f"User status updated to AUTH0_ACCOUNT_LINKED")

            # Create subscription record for the client app
            logger.info(f"Creating subscription record for client app")
            try:
                # Get subscription details from Stripe
                subscription = stripe.Subscription.retrieve(subscription_id)
                
                # Create subscription record
                from models.subscription import Subscription
                subscription_record = Subscription(
                    user_id=user_info["sub"],  # auth0_id as user_id
                    payment_method=subscription_id,  # Stripe subscription ID
                    status=subscription.status if hasattr(subscription, 'status') else 'active',
                    start_date=datetime.fromtimestamp(subscription.start_date) if hasattr(subscription, 'start_date') and subscription.start_date else datetime.now(),
                    end_date=datetime.fromtimestamp(subscription.current_period_end) if hasattr(subscription, 'current_period_end') and subscription.current_period_end else None,
                    payment_status='paid',
                    auto_renew=True
                )
                
                db.merge(subscription_record)
                db.commit()
                logger.info(f"Subscription record created for user {user_info['sub']}")
            except Exception as e:
                logger.error(f"Failed to create subscription record: {e}")
                # Don't fail the auth flow if subscription record creation fails

            # Optional: Check subscription validation if feature is enabled
            if admin_db_session:
                should_validate = check_subscription_validation_enabled(admin_db_session)
                if should_validate:
                    is_valid = validate_subscription_status(user_info["sub"], db)
                    if not is_valid:
                        landing_url = get_subscription_landing_url(admin_db_session)
                        if landing_url:
                            logger.info(f"Subscription invalid, redirecting to: {landing_url}")
                            return RedirectResponse(url=landing_url)

            # Redirect to app dashboard/main page
            redirect_url = f"{app_url}/dashboard"  # Adjust this to your main app's first page
            logger.info(f"Redirecting to main app: {redirect_url}")
            return RedirectResponse(url=redirect_url)

        except Exception as e:
            logger.error(f"Error in Auth0 callback: {e}", exc_info=True)
            error_url = f"{app_url}/error?reason={str(e)}"
            logger.info(f"Redirecting to error page: {error_url}")
            return RedirectResponse(url=error_url)

    return router

def check_subscription_validation_enabled(admin_db_session) -> bool:
    """Check if subscription validation is enabled in admin config"""
    try:
        # Import admin GlobalConfig model here
        # from admin_models import GlobalConfig
        # config = admin_db_session.query(GlobalConfig).first()
        # return config.subscription_validation_enabled if config else False
        return False  # Placeholder - implement based on your admin model access
    except Exception as e:
        logger.error(f"Error checking validation flag: {e}")
        return False

def get_subscription_landing_url(admin_db_session) -> Optional[str]:
    """Get subscription landing page URL from admin config"""
    try:
        # Import admin GlobalConfig model here
        # from admin_models import GlobalConfig
        # config = admin_db_session.query(GlobalConfig).first()
        # return config.subscription_landing_page_url if config else None
        return None  # Placeholder - implement based on your admin model access
    except Exception as e:
        logger.error(f"Error getting landing URL: {e}")
        return None

def validate_subscription_status(auth0_id: str, db_session) -> bool:
    """Validate user's subscription with Stripe"""
    try:
        import stripe

        # You'll need to configure Stripe API key in main app
        logger.debug(f"Validating subscription for auth0_id: {auth0_id}")

        # Find user by auth0_id (adjust import based on main app)
        from models.subscription_user import SubscriptionUser  # Adjust import path

        user = db_session.query(SubscriptionUser).filter(
            SubscriptionUser.auth0_id == auth0_id
        ).first()

        if not user or not user.subscription_id:
            logger.warning(f"No subscription found for auth0_id: {auth0_id}")
            return False

        # Check with Stripe
        subscription = stripe.Subscription.retrieve(user.subscription_id)
        valid_statuses = ['active', 'trialing']
        is_valid = subscription.status in valid_statuses

        logger.debug(f"Subscription {user.subscription_id} status: {subscription.status}, valid: {is_valid}")
        return is_valid

    except Exception as e:
        logger.error(f"Error validating subscription for {auth0_id}: {e}")
        return False

# Example usage in main app:
"""
from auth0_subscription_handler import create_auth0_subscription_router
from database import get_db
from models.subscription_user import SubscriptionUser
from services.auth0_service import exchange_code_for_tokens

app = FastAPI()

# Create and include the router
auth_router = create_auth0_subscription_router(
    get_db_session=get_db,
    subscription_user_model=SubscriptionUser,
    exchange_code_for_tokens_func=exchange_code_for_tokens,
    app_url="https://your-main-app.com"
)

app.include_router(auth_router)
"""