import os
import logging
import httpx
from fastapi import HTTPException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logger
logger = logging.getLogger("auth0_service")

# Auth0 configuration
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET")
AUTH0_DB_CONNECTION_ID = os.getenv("AUTH0_DB_CONNECTION_ID")
REDIRECT_URI = os.getenv("REDIRECT_URI")
APP_URL = os.getenv("APP_URL")

async def get_auth0_management_token():
    """Get an Auth0 Management API token"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://{AUTH0_DOMAIN}/oauth/token",
                json={
                    "client_id": AUTH0_CLIENT_ID,
                    "client_secret": AUTH0_CLIENT_SECRET,
                    "audience": f"https://{AUTH0_DOMAIN}/api/v2/",
                    "grant_type": "client_credentials"
                }
            )
            response.raise_for_status()
            return response.json()["access_token"]
    except httpx.HTTPError as e:
        logger.error(f"HTTP error getting Auth0 token: {e}")
        raise HTTPException(status_code=500, detail="Error getting Auth0 token")
    except Exception as e:
        logger.error(f"Error getting Auth0 token: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def send_auth0_invitation(email, subscription_id):
    """Send an Auth0 email invitation"""
    try:
        token = await get_auth0_management_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://{AUTH0_DOMAIN}/api/v2/tickets/email",
                json={
                    "email": email,
                    "connection_id": AUTH0_DB_CONNECTION_ID,
                    "client_id": AUTH0_CLIENT_ID,
                    "invitation": True,
                    "send_invitation_email": True,
                    "user_metadata": {
                        "subscription_id": subscription_id
                    }
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error sending Auth0 invitation: {e}")
        raise HTTPException(status_code=500, detail="Error sending Auth0 invitation")
    except Exception as e:
        logger.error(f"Error sending Auth0 invitation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def create_auth0_authorize_url(subscription_id):
    """Create Auth0 authorization URL with subscription ID in state parameter"""
    return (
        f"https://{AUTH0_DOMAIN}/authorize"
        f"?response_type=code"
        f"&client_id={AUTH0_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={subscription_id}"
    )

async def exchange_code_for_tokens(code):
    """Exchange authorization code for tokens"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://{AUTH0_DOMAIN}/oauth/token",
                json={
                    "grant_type": "authorization_code",
                    "client_id": AUTH0_CLIENT_ID,
                    "client_secret": AUTH0_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": REDIRECT_URI
                }
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error exchanging code for tokens: {e}")
        raise HTTPException(status_code=500, detail="Error exchanging code for tokens")
    except Exception as e:
        logger.error(f"Error exchanging code for tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))