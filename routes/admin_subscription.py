# routes/admin_subscription.py

"""
Admin routes for managing subscription validation settings.

These endpoints allow administrators to enable/disable subscription validation
and configure the landing page URL for failed validations.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from models.globals import GlobalConfig
from auth import verify_session_token, SESSION_COOKIE_NAME
from fastapi import status
from fastapi.responses import RedirectResponse
import logging
import re

logger = logging.getLogger("admin_subscription")

# Create router
router = APIRouter()

# Template configuration
templates = Jinja2Templates(directory="templates")

def is_valid_url(url: str) -> bool:
    """Validate URL format"""
    if not url:
        return True  # Empty URL is valid (optional field)

    # Basic URL pattern
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return url_pattern.match(url) is not None

@router.get("/admin/subscription-validation")
async def subscription_validation_page(request: Request, db: Session = Depends(get_db)):
    """Display subscription validation settings page"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        logger.info("User not authenticated, redirecting to login")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    try:
        # Get current config
        config = GlobalConfig.get(db)
        if not config:
            # Create default config if none exists
            config = GlobalConfig(
                id=True,
                subscription_validation_enabled=False,
                subscription_landing_page_url=None
            )
            db.add(config)
            db.commit()

        return templates.TemplateResponse(
            "admin/subscription_validation.html",
            {
                "request": request,
                "subscription_validation_enabled": config.subscription_validation_enabled,
                "subscription_landing_page_url": config.subscription_landing_page_url or "",
                "is_authenticated": True
            }
        )
    except Exception as e:
        logger.error(f"Error loading subscription validation page: {e}")
        return templates.TemplateResponse(
            "admin/subscription_validation.html",
            {
                "request": request,
                "subscription_validation_enabled": False,
                "subscription_landing_page_url": "",
                "is_authenticated": True,
                "error": "Failed to load settings"
            }
        )

@router.get("/api/admin/subscription-settings")
async def get_subscription_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current subscription validation settings"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        config = GlobalConfig.get(db)
        if not config:
            # Create default config if none exists
            config = GlobalConfig(
                id=True,
                subscription_validation_enabled=False,
                subscription_landing_page_url=None
            )
            db.add(config)
            db.commit()

        return JSONResponse({
            "subscription_validation_enabled": config.subscription_validation_enabled,
            "subscription_landing_page_url": config.subscription_landing_page_url
        })

    except Exception as e:
        logger.error(f"Error getting subscription settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/admin/subscription-settings")
async def update_subscription_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Update subscription validation settings"""
    # Check if user is logged in
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Parse request body
        data = await request.json()

        # Validate URL if provided
        landing_page_url = data.get("subscription_landing_page_url", "")
        if landing_page_url and not is_valid_url(landing_page_url):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Invalid URL format. Please provide a valid URL starting with http:// or https://"
                }
            )

        # Get or create config
        config = GlobalConfig.get(db)
        if not config:
            config = GlobalConfig(id=True)
            db.add(config)

        # Update settings
        if "subscription_validation_enabled" in data:
            config.subscription_validation_enabled = bool(data["subscription_validation_enabled"])

        if "subscription_landing_page_url" in data:
            # If empty string, set to None so default page is used
            config.subscription_landing_page_url = data["subscription_landing_page_url"] or None

        db.commit()

        logger.info(f"Updated subscription settings: enabled={config.subscription_validation_enabled}, url={config.subscription_landing_page_url}")

        return JSONResponse({
            "success": True,
            "subscription_validation_enabled": config.subscription_validation_enabled,
            "subscription_landing_page_url": config.subscription_landing_page_url
        })

    except Exception as e:
        logger.error(f"Error updating subscription settings: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))