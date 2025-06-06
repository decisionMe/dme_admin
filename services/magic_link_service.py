# services/magic_link_service.py
import os
import time
import hmac
import hashlib
import secrets
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

logger = logging.getLogger("magic_link_service")

class MagicLinkError(Exception):
    """Custom exception for magic link errors"""
    pass

def get_magic_link_secret() -> str:
    """Get the magic link secret from environment variables"""
    secret = os.getenv("MAGIC_LINK_SECRET")
    if not secret:
        logger.error("MAGIC_LINK_SECRET environment variable is not set")
        raise MagicLinkError("MAGIC_LINK_SECRET environment variable is not set")
    if len(secret) < 32:
        logger.warning("MAGIC_LINK_SECRET is shorter than recommended (32 characters)")
    return secret

def get_client_app_url() -> str:
    """Get the client app URL from environment variables"""
    url = os.getenv("CLIENT_APP_URL")
    if not url:
        logger.error("CLIENT_APP_URL environment variable is not set")
        raise MagicLinkError("CLIENT_APP_URL environment variable is not set")
    if not url.startswith(('http://', 'https://')):
        logger.warning(f"CLIENT_APP_URL does not start with http:// or https://: {url}")
    return url

def create_magic_token(auth0_id: str, email: str) -> str:
    """
    Create a secure magic token for user transition to client app

    Token format: {random_token}.{hmac_signature}
    HMAC message format: {token}.{auth0_id}.{expiry_timestamp}

    Args:
        auth0_id: The Auth0 user ID
        email: The user's email address

    Returns:
        Secure magic token string

    Raises:
        MagicLinkError: If environment variables are missing or token creation fails
    """
    try:
        # Input validation
        if not auth0_id or not isinstance(auth0_id, str):
            logger.error("Invalid auth0_id provided")
            raise MagicLinkError("auth0_id must be a non-empty string")

        if not email or not isinstance(email, str):
            logger.error("Invalid email provided")
            raise MagicLinkError("email must be a non-empty string")

        # Basic email format validation
        if "@" not in email or "." not in email:
            logger.warning(f"Email format appears invalid: {email}")

        # Get secret key
        secret_key = get_magic_link_secret()

        # Generate random token (32 bytes = 64 hex characters)
        random_token = secrets.token_hex(32)

        # Create expiry timestamp (5 minutes from now)
        expiry_timestamp = int(time.time()) + (5 * 60)  # 5 minutes

        # Create HMAC message: {token}.{auth0_id}.{expiry_timestamp}
        hmac_message = f"{random_token}.{auth0_id}.{expiry_timestamp}"

        # Generate HMAC signature using SHA256
        signature = hmac.new(
            secret_key.encode('utf-8'),
            hmac_message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Return token in format: {random_token}.{hmac_signature}
        magic_token = f"{random_token}.{signature}"

        logger.info(f"Magic token created for auth0_id: {auth0_id}, email: {email}")
        logger.debug(f"Token expires at: {expiry_timestamp} ({datetime.fromtimestamp(expiry_timestamp)})")

        return magic_token

    except MagicLinkError:
        # Re-raise MagicLinkError as-is
        raise
    except Exception as e:
        logger.error(f"Failed to create magic token for {auth0_id}: {e}", exc_info=True)
        raise MagicLinkError(f"Token creation failed: {e}")

def generate_magic_link(auth0_id: str, email: str, base_url: Optional[str] = None) -> str:
    """
    Generate a complete magic link URL for user transition to client app

    Args:
        auth0_id: The Auth0 user ID
        email: The user's email address
        base_url: Optional base URL override (uses CLIENT_APP_URL from env if not provided)

    Returns:
        Complete magic link URL

    Raises:
        MagicLinkError: If token creation or URL generation fails
    """
    try:
        # Create the magic token
        magic_token = create_magic_token(auth0_id, email)

        # Use provided base URL or get from environment
        if base_url is None:
            base_url = get_client_app_url()

        # Ensure base URL doesn't end with slash
        base_url = base_url.rstrip('/')

        # Create the magic link URL
        magic_link = f"{base_url}/auth/magic?token={magic_token}"

        logger.info(f"Magic link generated for auth0_id: {auth0_id}")
        logger.debug(f"Magic link URL: {magic_link}")

        return magic_link

    except Exception as e:
        logger.error(f"Failed to generate magic link for {auth0_id}: {e}")
        raise MagicLinkError(f"Magic link generation failed: {e}")

def validate_magic_token_format(token: str) -> bool:
    """
    Validate that a magic token has the correct format

    Args:
        token: The magic token to validate

    Returns:
        True if format is valid, False otherwise
    """
    try:
        # Token should have format: {random_token}.{hmac_signature}
        parts = token.split('.')
        if len(parts) != 2:
            return False

        random_part, signature_part = parts

        # Random part should be 64 hex characters (32 bytes)
        if len(random_part) != 64 or not all(c in '0123456789abcdef' for c in random_part.lower()):
            return False

        # Signature part should be 64 hex characters (SHA256 = 32 bytes = 64 hex)
        if len(signature_part) != 64 or not all(c in '0123456789abcdef' for c in signature_part.lower()):
            return False

        return True

    except Exception:
        return False

def get_token_info(token: str) -> Optional[dict]:
    """
    Extract information from a magic token (for debugging/logging purposes)
    Note: This does NOT validate the token signature

    Args:
        token: The magic token

    Returns:
        Dictionary with token info or None if invalid format
    """
    try:
        if not validate_magic_token_format(token):
            return None

        random_part, signature_part = token.split('.')

        return {
            "random_token": random_part,
            "signature": signature_part,
            "token_length": len(random_part),
            "signature_length": len(signature_part)
        }

    except Exception:
        return None

# Example usage and testing functions
def test_magic_link_generation():
    """Test function to verify magic link generation works correctly"""
    test_auth0_id = "auth0|test123456789"
    test_email = "test@example.com"

    try:
        # Test token creation
        token = create_magic_token(test_auth0_id, test_email)
        print(f"✅ Token created: {token}")

        # Validate token format
        is_valid_format = validate_magic_token_format(token)
        print(f"✅ Token format valid: {is_valid_format}")

        # Get token info
        token_info = get_token_info(token)
        print(f"✅ Token info: {token_info}")

        # Test magic link generation
        magic_link = generate_magic_link(test_auth0_id, test_email)
        print(f"✅ Magic link generated: {magic_link}")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    # Run tests if executed directly
    test_magic_link_generation()