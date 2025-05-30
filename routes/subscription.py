# routes/subscription.py
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
import json
import jwt
import os
import stripe  # Add this import
from pydantic import BaseModel
from typing import Optional
from auth import verify_admin
from datetime import datetime

from database import get_db
from models.subscription_user import SubscriptionUser
from models.subscription import Subscription
from services.stripe_service import verify_stripe_signature
from services.auth0_service import (
    send_auth0_invitation,
    create_auth0_authorize_url,
    exchange_code_for_tokens,
    APP_URL
)

# Configure stripe
stripe.api_key = os.getenv("STRIPE_API_KEY")

# Configure logging
logger = logging.getLogger("subscription_routes")
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/subscription", tags=["subscription"])

# Admin recovery request model
class RecoveryRequest(BaseModel):
    subscription_id: str
    email: str

# Fix for the success handler

@router.get("/stripe/success")
async def stripe_success(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Handler for Stripe checkout success redirects"""
    logger.info(f"🎯 CHECKPOINT 1: Received success redirect with session_id: {session_id}")
    logger.info(f"🔑 CHECKPOINT 2: Using API key: {stripe.api_key[:15]}...")
    logger.info(f"🌐 CHECKPOINT 3: APP_URL is: {APP_URL}")

    try:
        logger.info(f"🔍 CHECKPOINT 4: Attempting to retrieve session from Stripe...")

        # Retrieve the session from Stripe to get complete details
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["subscription", "subscription.default_payment_method"]
        )

        logger.info(f"✅ CHECKPOINT 5: Successfully retrieved session! Mode: {session.mode}, Status: {session.status}")
        logger.info(f"📊 CHECKPOINT 6: Session details - Customer: {session.customer}, Amount: {session.amount_total}")

        # Check if this is a subscription checkout
        if session.mode != "subscription":
            logger.warning(f"❌ CHECKPOINT 7: Session {session_id} is not a subscription mode (mode: {session.mode}), redirecting to error")
            error_url = f"{APP_URL}/error?reason=not_subscription"
            logger.info(f"🔗 CHECKPOINT 8: Redirecting to error URL: {error_url}")
            return RedirectResponse(url=error_url)

        logger.info(f"✅ CHECKPOINT 9: Session is subscription mode, proceeding...")

        # Get subscription details
        subscription = session.subscription
        if not subscription:
            logger.warning(f"❌ CHECKPOINT 10: No subscription found for session {session_id}")
            error_url = f"{APP_URL}/error?reason=no_subscription"
            logger.info(f"🔗 CHECKPOINT 11: Redirecting to error URL: {error_url}")
            return RedirectResponse(url=error_url)

        subscription_id = subscription.id
        logger.info(f"🎉 CHECKPOINT 12: Found subscription! ID: {subscription_id}")
        logger.info(f"💰 CHECKPOINT 13: Processing Stripe success for session {session_id}, subscription {subscription_id}")

        # Extract customer email
        customer_email = None
        if session.customer_details and hasattr(session.customer_details, "email"):
            customer_email = session.customer_details.email
            logger.info(f"📧 CHECKPOINT 14: Customer email: {customer_email}")
        else:
            logger.info(f"📧 CHECKPOINT 15: No customer email found")

        # Extract custom field for different user email
        different_user_email = None
        if hasattr(session, "custom_fields") and session.custom_fields:
            for field in session.custom_fields:
                if field.get('type') == 'text' and field.get('text') and field.get('text', {}).get('value'):
                    different_user_email = field.get('text', {}).get('value').strip()
                    logger.info(f"📧 CHECKPOINT 15a: Found custom email field: {different_user_email}")
                    break

        # Check if it's a gift subscription based on custom field
        is_gift = different_user_email is not None
        recipient_email = different_user_email

        logger.info(f"💾 CHECKPOINT 18: Creating/updating user record in database...")

        # Create or update user record
        user = SubscriptionUser(
            subscription_id=subscription_id,
            email=different_user_email if different_user_email else customer_email,
            purchaser_email=customer_email,
            registration_status="PAYMENT_COMPLETED"
        )

        db.merge(user)  # This will insert or update as needed
        db.commit()
        logger.info(f"✅ CHECKPOINT 19: User record created/updated for subscription {subscription_id}")

        # After AUTH0_ACCOUNT_LINKED, create the subscription record for the client app
        # This will be done in the auth0 callback when registration is complete

        if is_gift and recipient_email:
            logger.info(f"🎁 CHECKPOINT 20: Processing gift subscription for {recipient_email}")
            # For gift subscriptions, send Auth0 invitation
            invitation_result = await send_auth0_invitation(recipient_email, subscription_id)
            logger.info(f"📨 CHECKPOINT 21: Auth0 invitation sent: {invitation_result}")

            # Update status
            user = db.query(SubscriptionUser).filter(SubscriptionUser.subscription_id == subscription_id).first()
            user.registration_status = "AUTH0_INVITE_SENT"
            db.commit()
            logger.info(f"✅ CHECKPOINT 22: User status updated to AUTH0_INVITE_SENT")

            # Redirect to gift confirmation page
            redirect_url = f"{APP_URL}/gift-confirmation"
            logger.info(f"🔗 CHECKPOINT 23: Redirecting to gift confirmation: {redirect_url}")
            return RedirectResponse(url=redirect_url)
        else:
            logger.info(f"🔐 CHECKPOINT 24: Processing direct subscription, redirecting to Auth0")
            # For direct subscriptions, redirect to Auth0
            auth0_url = create_auth0_authorize_url(subscription_id)
            logger.info(f"🔗 CHECKPOINT 25: Auth0 redirect URL: {auth0_url}")
            response = RedirectResponse(url=auth0_url)
            response.headers["ngrok-skip-browser-warning"] = "true"
            logger.info(f"✅ CHECKPOINT 26: Returning Auth0 redirect response")
            return response

    except stripe.error.StripeError as e:
        logger.error(f"❌ CHECKPOINT ERROR A: Stripe error: {e}", exc_info=True)
        error_url = f"{APP_URL}/error?reason=stripe_error"
        logger.error(f"🔗 CHECKPOINT ERROR B: Redirecting to Stripe error URL: {error_url}")
        return RedirectResponse(url=error_url)
    except Exception as e:
        logger.error(f"❌ CHECKPOINT ERROR C: General error handling Stripe success: {e}", exc_info=True)
        # Redirect to error page
        error_url = f"{APP_URL}/error?reason={str(e)}"
        logger.error(f"🔗 CHECKPOINT ERROR D: Redirecting to general error page: {error_url}")

        return RedirectResponse(url=error_url)




@router.get("/auth/callback")
async def auth0_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """Handler for Auth0 callback after authentication"""
    logger.info(f"Received Auth0 callback with state: {state}")

    try:
        # Exchange code for tokens
        logger.debug(f"Exchanging authorization code for tokens")
        token_data = await exchange_code_for_tokens(code)
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
        user = db.query(SubscriptionUser).filter(SubscriptionUser.subscription_id == subscription_id).first()

        if not user:
            logger.error(f"User not found for subscription {subscription_id}")
            # This should not happen normally, but handle it gracefully
            return RedirectResponse(url=f"{APP_URL}/error?reason=user_not_found")

        logger.info(f"Updating user record with Auth0 ID {user_info['sub']}")

        user.auth0_id = user_info["sub"]
        if "email" in user_info:
            user.email = user_info["email"]
            logger.debug(f"Updated user email to {user_info['email']}")
        user.registration_status = "AUTH0_ACCOUNT_LINKED"
        db.commit()
        logger.debug(f"User status updated to AUTH0_ACCOUNT_LINKED")

        # Redirect to app dashboard
        redirect_url = f"{APP_URL}/dashboard"
        logger.info(f"Redirecting to dashboard: {redirect_url}")
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"Error in Auth0 callback: {e}", exc_info=True)
        error_url = f"{APP_URL}/error?reason={str(e)}"
        logger.info(f"Redirecting to error page: {error_url}")
        return RedirectResponse(url=error_url)


@router.post("/admin/recover", dependencies=[Depends(verify_admin)])
async def recover_subscription(
    request: RecoveryRequest,
    db: Session = Depends(get_db)
):
    """Admin endpoint to recover abandoned subscriptions"""
    logger.info(f"Processing admin recovery request for subscription {request.subscription_id}")

    try:
        from services.stripe_service import get_subscription_with_payment_method

        # Get subscription details from Stripe
        logger.debug(f"Getting subscription details from Stripe")
        from services.stripe_service import verify_subscription_exists
        verify_subscription_exists(request.subscription_id)
        
        # Retrieve full subscription details
        subscription = stripe.Subscription.retrieve(request.subscription_id)

        logger.info(f"Admin recovery for subscription {request.subscription_id}, email {request.email}")

        # Create or update user record
        user = SubscriptionUser(
            subscription_id=request.subscription_id,
            email=request.email,
            registration_status="PAYMENT_COMPLETED"
        )

        db.merge(user)
        db.commit()
        logger.debug(f"User record created/updated for subscription {request.subscription_id}")

        # Note: Admin recovery doesn't create subscription record yet since we don't have auth0_id
        # The subscription record will be created when the user completes Auth0 registration

        # Send Auth0 invitation
        logger.debug(f"Sending Auth0 invitation to {request.email}")
        invitation_result = await send_auth0_invitation(request.email, request.subscription_id)
        logger.debug(f"Auth0 invitation sent: {invitation_result}")

        # Update status
        user = db.query(SubscriptionUser).filter(SubscriptionUser.subscription_id == request.subscription_id).first()
        user.registration_status = "AUTH0_INVITE_SENT"
        db.commit()
        logger.debug(f"User status updated to AUTH0_INVITE_SENT")

        return {"success": True}

    except SQLAlchemyError as e:
        logger.error(f"Database error in admin recovery: {e}", exc_info=True)
        db.rollback()
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Error in admin recovery: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))