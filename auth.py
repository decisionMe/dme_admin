import os
from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeSerializer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get admin password from environment variable
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise ValueError("ADMIN_PASSWORD environment variable is not set")

# Create a serializer for session cookies
SECRET_KEY = os.urandom(24).hex()  # Generate a random secret key on startup
serializer = URLSafeSerializer(SECRET_KEY)

# Cookie name for the session
SESSION_COOKIE_NAME = "dme_admin_session"

def create_session_token():
    """Create a session token for the admin user"""
    return serializer.dumps({"role": "admin"})

def verify_session_token(token):
    """Verify a session token"""
    try:
        data = serializer.loads(token)
        return data.get("role") == "admin"
    except:
        return False

def verify_admin(request: Request):
    """Verify that the request is authenticated as admin"""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True

def login_required(request: Request):
    """Dependency to check if user is logged in, redirects to login page if not"""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not verify_session_token(session_token):
        return False
    return True