#!/usr/bin/env python3
"""
Script to delete all test customers from Stripe account and corresponding Auth0 users.
This will help clean up test data and ensure fresh sessions work properly.
"""

import stripe
import sys
import os
import httpx
import asyncio
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Auth0 configuration
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET")

async def get_auth0_management_token() -> Optional[str]:
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
    except Exception as e:
        print(f"  ⚠️  Error getting Auth0 token: {e}")
        return None

async def find_auth0_user_by_email(email: str, token: str) -> Optional[str]:
    """Find Auth0 user by email and return user ID"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{AUTH0_DOMAIN}/api/v2/users-by-email",
                params={"email": email},
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            users = response.json()
            if users:
                return users[0]["user_id"]
            return None
    except Exception as e:
        print(f"  ⚠️  Error finding Auth0 user for {email}: {e}")
        return None

async def delete_auth0_user(user_id: str, token: str) -> bool:
    """Delete Auth0 user by user ID"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"https://{AUTH0_DOMAIN}/api/v2/users/{user_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            return True
    except Exception as e:
        print(f"  ⚠️  Error deleting Auth0 user {user_id}: {e}")
        return False

async def delete_all_customers(api_key: str, dry_run: bool = True) -> None:
    """
    Delete all customers from Stripe test account and corresponding Auth0 users.

    Args:
        api_key: Stripe test secret key (sk_test_...)
        dry_run: If True, only list customers without deleting
    """
    stripe.api_key = api_key

    print(f"🔍 {'DRY RUN: ' if dry_run else ''}Fetching all customers...")

    # Get all customers
    customers = []
    starting_after = None

    while True:
        if starting_after:
            response = stripe.Customer.list(limit=100, starting_after=starting_after)
        else:
            response = stripe.Customer.list(limit=100)

        customers.extend(response.data)

        if not response.has_more:
            break

        starting_after = response.data[-1].id

    print(f"📊 Found {len(customers)} customers")

    if not customers:
        print("✅ No customers to delete!")
        return

    # List customers
    print("\n📋 Customer list:")
    for i, customer in enumerate(customers, 1):
        email = customer.email or "No email"
        created = customer.created
        print(f"  {i:3d}. {customer.id} - {email} (created: {created})")

    if dry_run:
        print(f"\n⚠️  DRY RUN: Would delete {len(customers)} customers and corresponding Auth0 users")
        print("   Run with --delete flag to actually delete them")
        return

    # Confirm deletion
    print(f"\n⚠️  About to DELETE {len(customers)} customers and their Auth0 users!")
    confirm = input("Type 'DELETE' to confirm: ")

    if confirm != "DELETE":
        print("❌ Deletion cancelled")
        return

    # Get Auth0 management token
    print("\n🔑 Getting Auth0 management token...")
    auth0_token = await get_auth0_management_token()
    if not auth0_token:
        print("❌ Failed to get Auth0 token - Auth0 cleanup will be skipped")

    # Delete customers and Auth0 users
    print(f"\n🗑️  Deleting {len(customers)} customers and Auth0 users...")
    deleted_stripe = 0
    deleted_auth0 = 0
    errors = []

    for i, customer in enumerate(customers, 1):
        customer_email = customer.email
        print(f"  🔄 {i:3d}/{len(customers)} Processing {customer.id} ({customer_email})")
        
        # Delete from Auth0 first (if we have email and token)
        if customer_email and auth0_token:
            try:
                user_id = await find_auth0_user_by_email(customer_email, auth0_token)
                if user_id:
                    success = await delete_auth0_user(user_id, auth0_token)
                    if success:
                        deleted_auth0 += 1
                        print(f"    ✅ Deleted Auth0 user {user_id}")
                    else:
                        print(f"    ❌ Failed to delete Auth0 user {user_id}")
                else:
                    print(f"    ℹ️  No Auth0 user found for {customer_email}")
            except Exception as e:
                error_msg = f"Auth0 deletion failed for {customer_email}: {e}"
                errors.append(error_msg)
                print(f"    ❌ {error_msg}")
        
        # Delete from Stripe
        try:
            stripe.Customer.delete(customer.id)
            deleted_stripe += 1
            print(f"    ✅ Deleted Stripe customer {customer.id}")
        except Exception as e:
            error_msg = f"Failed to delete Stripe customer {customer.id}: {e}"
            errors.append(error_msg)
            print(f"    ❌ {error_msg}")

    # Summary
    print(f"\n📊 Deletion Summary:")
    print(f"  ✅ Stripe customers deleted: {deleted_stripe}")
    print(f"  ✅ Auth0 users deleted: {deleted_auth0}")
    print(f"  ❌ Failed operations: {len(errors)}")

    if errors:
        print(f"\n❌ Errors:")
        for error in errors:
            print(f"  - {error}")

    print(f"\n✅ Cleanup complete!")

async def main_async():
    """Async main function"""
    if len(sys.argv) < 2:
        print("Usage: python cleanup_stripe_customers.py <stripe_test_key> [--delete]")
        print("  --delete: Actually delete customers and Auth0 users (default is dry run)")
        print("  Note: Requires AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET in .env")
        sys.exit(1)

    api_key = sys.argv[1]
    dry_run = "--delete" not in sys.argv

    # Validate API key
    if not api_key.startswith("sk_test_"):
        print("❌ Error: API key must be a test key starting with 'sk_test_'")
        sys.exit(1)

    # Validate Auth0 config
    if not all([AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET]):
        print("⚠️  Warning: Auth0 environment variables not configured")
        print("   Set AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET in .env")
        print("   Only Stripe cleanup will be performed")

    print("🧹 Stripe & Auth0 Cleanup Tool")
    print(f"🔑 Stripe API Key: {api_key[:12]}...")
    print(f"🔐 Auth0 Domain: {AUTH0_DOMAIN or 'Not configured'}")
    print(f"🚀 Mode: {'DRY RUN' if dry_run else 'DELETE'}")
    print()

    try:
        await delete_all_customers(api_key, dry_run)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

def main():
    """Main function wrapper"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()