# middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import os
import time
from fastapi import Request
import base64

# Configure detailed logging
logger = logging.getLogger("webhook_middleware")
logger.setLevel(logging.DEBUG)

class RawBodyMiddleware(BaseHTTPMiddleware):
    """Middleware to preserve raw request body for Stripe webhook verification"""

    async def dispatch(self, request: Request, call_next):
        # Only preserve raw body for webhook endpoint
        if request.url.path == "/subscription/stripe/webhook":
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            request_id = f"req_{timestamp}_{id(request)}"

            logger.debug(f"[{request_id}] Webhook request received from {request.client.host}")
            logger.debug(f"[{request_id}] Headers: {dict(request.headers)}")

            # Store the original receive function
            original_receive = request._receive

            # Define a new receive function that stores the raw body
            async def receive():
                if not hasattr(request.state, "raw_body"):
                    # Get the original request body
                    body = await original_receive()
                    raw_body = body.get("body", b"")

                    # Store it in request state
                    request.state.raw_body = raw_body
                    request.state.request_id = request_id

                    # Debug logging - truncated to avoid logging sensitive data
                    body_preview = raw_body[:30]
                    logger.debug(f"[{request_id}] Raw body received: {len(raw_body)} bytes")
                    logger.debug(f"[{request_id}] Body preview: {body_preview}...")

                    # Save full raw body to debug file if in development
                    if os.getenv("SAVE_WEBHOOK_BODIES", "false").lower() == "true":
                        debug_dir = os.getenv("DEBUG_DIR", "debug_logs")
                        os.makedirs(debug_dir, exist_ok=True)
                        with open(f"{debug_dir}/webhook_body_{request_id}.bin", "wb") as f:
                            f.write(raw_body)
                        logger.debug(f"[{request_id}] Full body saved to debug file")

                    return body

                # Return the stored body on subsequent calls
                logger.debug(f"[{request_id}] Returning cached raw body on subsequent receive call")
                return {"type": "http.request", "body": request.state.raw_body}

            # Replace the receive function
            request._receive = receive

            # Process the request
            try:
                response = await call_next(request)
                logger.debug(f"[{request_id}] Webhook response status: {response.status_code}")
                return response
            except Exception as e:
                logger.error(f"[{request_id}] Error processing webhook: {str(e)}", exc_info=True)
                raise
        else:
            # For non-webhook requests, just process normally
            return await call_next(request)