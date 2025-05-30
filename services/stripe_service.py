# services/stripe_service.py
import os
import stripe
import logging
import json
import hmac
import hashlib
import time
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import base64

# Load environment variables
load_dotenv()

# Configure logger
logger = logging.getLogger("stripe_service")
logger.setLevel(logging.DEBUG)

# Configure Stripe
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_WEBHOOK_SECRET_CLI = os.getenv("STRIPE_WEBHOOK_SECRET_CLI")

# Initialize Stripe client
stripe.api_key = STRIPE_API_KEY

def verify_stripe_signature(payload, sig_header, request_id=None, remote_addr=None):
    """Verify Stripe webhook signature with detailed debugging"""
    request_tag = f"[{request_id}] " if request_id else ""

    try:
        logger.debug(f"{request_tag}Starting signature verification")

        # Check for missing prerequisites
        if not STRIPE_WEBHOOK_SECRET:
            logger.error(f"{request_tag}STRIPE_WEBHOOK_SECRET is not set")
            raise HTTPException(status_code=500, detail="Webhook secret not configured")

        if not sig_header:
            logger.warning(f"{request_tag}No signature header provided")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No signature header"}
            )

        # Ensure payload is bytes
        if isinstance(payload, str):
            logger.debug(f"{request_tag}Converting payload from string to bytes")
            payload = payload.encode('utf-8')

        # Log signature details
        sig_parts = sig_header.split(',')
        logger.debug(f"{request_tag}Signature header has {len(sig_parts)} parts")
        for i, part in enumerate(sig_parts):
            logger.debug(f"{request_tag}Signature part {i+1}: {part[:10]}...")

        # Log verification parameters
        logger.debug(f"{request_tag}Webhook secret first 4 chars: {STRIPE_WEBHOOK_SECRET[:4]}***")
        logger.debug(f"{request_tag}Payload size: {len(payload)} bytes")

        # Determine if this is from Stripe CLI or real Stripe
        is_cli = remote_addr == "127.0.0.1"

        # Choose the appropriate webhook secret
        webhook_secret = STRIPE_WEBHOOK_SECRET_CLI if is_cli and STRIPE_WEBHOOK_SECRET_CLI else STRIPE_WEBHOOK_SECRET
        logger.debug(f"{request_tag}Using {'CLI' if is_cli and STRIPE_WEBHOOK_SECRET_CLI else 'standard'} webhook secret")

        # Manual signature verification for debugging - DO NOT USE IN PRODUCTION
        if os.getenv("DEBUG_SIGNATURES", "false").lower() == "true":
            for part in sig_parts:
                if part.startswith("t="):
                    timestamp = part[2:]
                    logger.debug(f"{request_tag}Signature timestamp: {timestamp}")

                    # Construct the signed payload string
                    signed_payload = f"{timestamp}.{payload.decode('utf-8') if isinstance(payload, bytes) else payload}"

                    # Compute the expected signature
                    computed_sig = hmac.new(
                        webhook_secret.encode('utf-8'),
                        signed_payload.encode('utf-8'),
                        hashlib.sha256
                    ).hexdigest()

                    # Log first 10 chars of computed signature
                    logger.debug(f"{request_tag}Computed signature first 10 chars: {computed_sig[:10]}...")

        # Save diagnostic information in development
        if os.getenv("SAVE_WEBHOOK_DIAGNOSTICS", "false").lower() == "true":
            debug_dir = os.getenv("DEBUG_DIR", "debug_logs")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            diagnostic_id = f"{timestamp}_{id(payload)}"

            with open(f"{debug_dir}/webhook_sig_{diagnostic_id}.txt", "w") as f:
                f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Source: {'CLI' if is_cli else 'Stripe'}\n")
                f.write(f"Remote Address: {remote_addr}\n")
                f.write(f"Signature Header: {sig_header}\n")
                f.write(f"Webhook Secret Type: {'CLI' if is_cli and STRIPE_WEBHOOK_SECRET_CLI else 'standard'}\n")
                f.write(f"Webhook Secret First 4 Chars: {webhook_secret[:4]}***\n")
                f.write(f"Payload Size: {len(payload)} bytes\n")

            logger.debug(f"{request_tag}Diagnostics saved to {debug_dir}/webhook_sig_{diagnostic_id}.txt")

        # Use Stripe's SDK for actual verification
        logger.debug(f"{request_tag}Calling Stripe SDK for verification")
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )

        logger.info(f"{request_tag}Signature verified successfully for event {event['id']} of type {event['type']}")
        return event

    except stripe.error.SignatureVerificationError as e:
        logger.error(f"{request_tag}Stripe signature verification failed: {e}")

        # Detailed error logging
        if hasattr(e, "header") and e.header:
            logger.error(f"{request_tag}Error header: {e.header}")
        if hasattr(e, "payload") and e.payload:
            logger.error(f"{request_tag}Error payload size: {len(e.payload)} bytes")

        raise HTTPException(status_code=400, detail=f"Invalid signature: {str(e)}")

    except json.JSONDecodeError as e:
        logger.error(f"{request_tag}JSON decode error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")

    except Exception as e:
        logger.error(f"{request_tag}Error verifying Stripe webhook: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

def get_subscription_from_session(session_id):
    """Get subscription details from a checkout session (DO NOT USE - Instead use direct Stripe API call)"""
    # This function is deprecated - Instead, use the Stripe API directly with the expand parameter
    raise DeprecationWarning("This function is deprecated. Use stripe.checkout.sessions.retrieve directly with expand=['subscription']")

def verify_subscription_exists(subscription_id):
    """Verify that a subscription exists in Stripe"""
    try:
        logger.debug(f"Verifying subscription {subscription_id} exists")
        subscription = stripe.Subscription.retrieve(subscription_id)
        logger.debug(f"Subscription retrieved: {subscription.id}, status: {subscription.status}")
        return True
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error verifying subscription {subscription_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error verifying subscription {subscription_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def get_subscription_with_payment_method(subscription_id):
    """Get subscription details including payment method"""
    try:
        logger.debug(f"Retrieving subscription {subscription_id} with payment method")
        subscription = stripe.Subscription.retrieve(
            subscription_id,
            expand=["default_payment_method"]
        )
        
        payment_method_id = None
        if subscription.default_payment_method:
            # If it's an object, get the ID
            if hasattr(subscription.default_payment_method, 'id'):
                payment_method_id = subscription.default_payment_method.id
            # If it's a string, use it directly
            elif isinstance(subscription.default_payment_method, str):
                payment_method_id = subscription.default_payment_method
        
        logger.debug(f"Subscription retrieved: {subscription.id}, payment_method: {payment_method_id}")
        return subscription, payment_method_id
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error retrieving subscription {subscription_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving subscription {subscription_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))