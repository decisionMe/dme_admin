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

from database import get_db
from models.subscription_user import SubscriptionUser
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
    db: Session = Depends(get_db)
):
    """Handler for Stripe checkout success redirects"""
    logger.info(f"Received success redirect with session_id: {session_id}")

    try:
        # Retrieve the session from Stripe to get complete details
        # Fix: Use correct Stripe API syntax (Session instead of sessions)
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["subscription"]
        )

        # Check if this is a subscription checkout
        if session.mode != "subscription":
            logger.warning(f"Session {session_id} is not a subscription mode, redirecting to error")
            return RedirectResponse(url=f"{APP_URL}/error?reason=not_subscription")

        # Get subscription details
        subscription = session.subscription
        if not subscription:
            logger.warning(f"No subscription found for session {session_id}")
            return RedirectResponse(url=f"{APP_URL}/error?reason=no_subscription")

        subscription_id = subscription.id
        logger.info(f"Processing Stripe success for session {session_id}, subscription {subscription_id}")

        # Extract customer email
        customer_email = None
        if session.customer_details and hasattr(session.customer_details, "email"):
            customer_email = session.customer_details.email
            logger.debug(f"Customer email: {customer_email}")

        # Check if it's a gift subscription
        is_gift = hasattr(session, "shipping") and session.shipping is not None
        recipient_email = None
        if is_gift and session.shipping:
            recipient_email = session.shipping.name  # Using name field for email
            logger.debug(f"Gift subscription with recipient email: {recipient_email}")

        # Create or update user record
        user = SubscriptionUser(
            subscription_id=subscription_id,
            email=recipient_email if is_gift and recipient_email else customer_email,
            registration_status="PAYMENT_COMPLETED"
        )

        db.merge(user)  # This will insert or update as needed
        db.commit()
        logger.debug(f"User record created/updated for subscription {subscription_id}")

        if is_gift and recipient_email:
            logger.info(f"Processing gift subscription for {recipient_email}")
            # For gift subscriptions, send Auth0 invitation
            invitation_result = await send_auth0_invitation(recipient_email, subscription_id)
            logger.debug(f"Auth0 invitation sent: {invitation_result}")

            # Update status
            user = db.query(SubscriptionUser).filter(SubscriptionUser.subscription_id == subscription_id).first()
            user.registration_status = "AUTH0_INVITE_SENT"
            db.commit()
            logger.debug(f"User status updated to AUTH0_INVITE_SENT")

            # Redirect to gift confirmation page
            redirect_url = f"{APP_URL}/gift-confirmation"
            logger.info(f"Redirecting to gift confirmation: {redirect_url}")
            return RedirectResponse(url=redirect_url)
        else:
            logger.info(f"Processing direct subscription, redirecting to Auth0")
            # For direct subscriptions, redirect to Auth0
            auth0_url = create_auth0_authorize_url(subscription_id)
            logger.debug(f"Auth0 redirect URL: {auth0_url}")
            return RedirectResponse(url=auth0_url)

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}", exc_info=True)
        error_url = f"{APP_URL}/error?reason=stripe_error"
        return RedirectResponse(url=error_url)
    except Exception as e:
        logger.error(f"Error handling Stripe success: {e}", exc_info=True)
        # Redirect to error page
        error_url = f"{APP_URL}/error?reason={str(e)}"
        logger.info(f"Redirecting to error page: {error_url}")

        return RedirectResponse(url=error_url)


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handler for Stripe webhook events"""
    # Get request ID from middleware if available
    request_id = getattr(request.state, "request_id", f"req_{id(request)}")
    logger.debug(f"[{request_id}] Processing webhook request")

    # Log headers and remote address for debugging
    remote_addr = request.client.host
    logger.debug(f"[{request_id}] Remote address: {remote_addr}")
    logger.debug(f"[{request_id}] Host header: {request.headers.get('host')}")
    logger.debug(f"[{request_id}] User-Agent: {request.headers.get('user-agent')}")

    # Log Stripe signature header
    sig_header = request.headers.get("stripe-signature")
    if sig_header:
        logger.debug(f"[{request_id}] Stripe signature present, length: {len(sig_header)}")
    else:
        logger.warning(f"[{request_id}] No Stripe signature header found")

    try:
        # Access the raw body from request state if available (set by middleware)
        if hasattr(request.state, "raw_body"):
            logger.debug(f"[{request_id}] Using raw body from middleware, size: {len(request.state.raw_body)} bytes")
            payload = request.state.raw_body
        else:
            logger.debug(f"[{request_id}] No raw body in request state, using body() method")
            payload = await request.body()
            logger.debug(f"[{request_id}] Body size from request.body(): {len(payload)} bytes")

        # Differentiate between Stripe CLI and real webhooks
        is_cli = "stripe-mock" in request.headers.get("user-agent", "").lower() or remote_addr == "127.0.0.1"
        source = "Stripe CLI" if is_cli else "Stripe"
        logger.debug(f"[{request_id}] Webhook source appears to be: {source}")

        # Get database session
        db = next(get_db())

        try:
            # Verify webhook signature - pass remote_addr to determine which secret to use
            event = verify_stripe_signature(payload, sig_header, request_id, remote_addr)

            logger.info(f"[{request_id}] Webhook verified successfully: {event['type']}")

            # Handle checkout.session.completed event
            if event["type"] == "checkout.session.completed":
                session = event["data"]["object"]

                # Get session ID
                session_id = session["id"]
                logger.info(f"[{request_id}] Processing checkout.session.completed for session {session_id}")

                # Retrieve the session from Stripe to get complete details
                # Fix: Use correct Stripe API syntax (Session instead of sessions)
                session_details = stripe.checkout.Session.retrieve(
                    session_id,
                    expand=["subscription"]
                )

                # Check if this is a subscription checkout
                if session_details.mode != "subscription":
                    logger.info(f"[{request_id}] Session {session_id} is not a subscription mode, skipping")

                    # Add this code to handle payment mode checkouts
                    if session_details.mode == "payment":
                        # Extract payment intent ID as your unique identifier
                        payment_intent_id = session_details.get("payment_intent")
                        customer_email = None

                        # Extract customer email if available
                        if hasattr(session_details, "customer_details") and hasattr(session_details.customer_details, "email"):
                            customer_email = session_details.customer_details.email

                        logger.info(f"[{request_id}] Processing payment mode checkout with payment_intent {payment_intent_id}")

                        # Store in database
                        try:
                            # Create user record
                            user = SubscriptionUser(
                                subscription_id=payment_intent_id,  # Use payment_intent as unique ID
                                email=customer_email,
                                registration_status="PAYMENT_COMPLETED"
                            )

                            db.add(user)
                            db.commit()
                            logger.info(f"[{request_id}] Created payment record for {payment_intent_id}")
                        except Exception as e:
                            logger.error(f"[{request_id}] Error creating payment record: {e}")
                            db.rollback()

                    return JSONResponse(content={"success": True})
                # Get subscription details
                subscription = session_details.subscription
                if not subscription:
                    logger.warning(f"[{request_id}] No subscription found for session {session_id}")
                    return JSONResponse(content={"success": True})

                subscription_id = subscription.id
                logger.info(f"[{request_id}] Found subscription {subscription_id} for session {session_id}")

                # Extract customer email
                customer_email = None
                if session_details.customer_details and hasattr(session_details.customer_details, "email"):
                    customer_email = session_details.customer_details.email
                    logger.debug(f"[{request_id}] Customer email: {customer_email}")

                # Check if it's a gift subscription
                is_gift = hasattr(session_details, "shipping") and session_details.shipping is not None
                recipient_email = None
                if is_gift and session_details.shipping:
                    recipient_email = session_details.shipping.name  # Using name field for email
                    logger.info(f"[{request_id}] Gift subscription for recipient: {recipient_email}")

                # Check if user already exists
                existing_user = db.query(SubscriptionUser).filter(SubscriptionUser.subscription_id == subscription_id).first()

                if not existing_user:
                    logger.info(f"[{request_id}] Creating new user record for subscription {subscription_id}")

                    # Create user record
                    user = SubscriptionUser(
                        subscription_id=subscription_id,
                        email=recipient_email if is_gift and recipient_email else customer_email,
                        registration_status="PAYMENT_COMPLETED"
                    )
                    db.add(user)
                    db.commit()
                    logger.debug(f"[{request_id}] User record created with subscription_id {subscription_id}")

                    # For gift subscriptions, send Auth0 invitation
                    if is_gift and recipient_email:
                        logger.info(f"[{request_id}] Sending Auth0 invitation to {recipient_email}")
                        try:
                            invitation_result = await send_auth0_invitation(recipient_email, subscription_id)
                            logger.debug(f"[{request_id}] Auth0 invitation sent: {invitation_result}")

                            # Update status
                            user.registration_status = "AUTH0_INVITE_SENT"
                            db.commit()
                            logger.debug(f"[{request_id}] User status updated to AUTH0_INVITE_SENT")
                        except Exception as e:
                            logger.error(f"[{request_id}] Error sending Auth0 invitation: {e}", exc_info=True)
                else:
                    logger.info(f"[{request_id}] User already exists for subscription {subscription_id}")

            return JSONResponse(content={"success": True})

        except Exception as e:
            logger.error(f"[{request_id}] Webhook processing error: {e}", exc_info=True)

            # More detailed debugging for signature errors
            if "Invalid signature" in str(e):
                logger.error(f"[{request_id}] Signature verification failed. Check that STRIPE_WEBHOOK_SECRET matches the value in Stripe dashboard.")
                if os.getenv("STRIPE_CLI_USED", "false").lower() == "true":
                    logger.error(f"[{request_id}] If using Stripe CLI, make sure to use the webhook signing secret shown when starting the CLI.")

            return JSONResponse(
                status_code=400,
                content={"success": False, "error": str(e)}
            )

    except Exception as e:
        logger.error(f"[{request_id}] Webhook handler error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


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
        from services.stripe_service import verify_subscription_exists

        # Verify the subscription exists in Stripe
        logger.debug(f"Verifying subscription exists in Stripe")
        verify_subscription_exists(request.subscription_id)

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