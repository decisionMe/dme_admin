#!/usr/bin/env python3
"""
Script to delete all test customers from Stripe account.
This will help clean up test data and ensure fresh sessions work properly.
"""

import stripe
import sys
from typing import List

def delete_all_customers(api_key: str, dry_run: bool = True) -> None:
    """
    Delete all customers from Stripe test account.

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
        print(f"\n⚠️  DRY RUN: Would delete {len(customers)} customers")
        print("   Run with --delete flag to actually delete them")
        return

    # Confirm deletion
    print(f"\n⚠️  About to DELETE {len(customers)} customers!")
    confirm = input("Type 'DELETE' to confirm: ")

    if confirm != "DELETE":
        print("❌ Deletion cancelled")
        return

    # Delete customers
    print(f"\n🗑️  Deleting {len(customers)} customers...")
    deleted_count = 0
    errors = []

    for i, customer in enumerate(customers, 1):
        try:
            stripe.Customer.delete(customer.id)
            deleted_count += 1
            print(f"  ✅ {i:3d}/{len(customers)} Deleted {customer.id}")
        except Exception as e:
            error_msg = f"Failed to delete {customer.id}: {e}"
            errors.append(error_msg)
            print(f"  ❌ {i:3d}/{len(customers)} {error_msg}")

    # Summary
    print(f"\n📊 Deletion Summary:")
    print(f"  ✅ Successfully deleted: {deleted_count}")
    print(f"  ❌ Failed to delete: {len(errors)}")

    if errors:
        print(f"\n❌ Errors:")
        for error in errors:
            print(f"  - {error}")

    print(f"\n✅ Cleanup complete!")

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python cleanup_stripe_customers.py <stripe_test_key> [--delete]")
        print("  --delete: Actually delete customers (default is dry run)")
        sys.exit(1)

    api_key = sys.argv[1]
    dry_run = "--delete" not in sys.argv

    # Validate API key
    if not api_key.startswith("sk_test_"):
        print("❌ Error: API key must be a test key starting with 'sk_test_'")
        sys.exit(1)

    print("🧹 Stripe Customer Cleanup Tool")
    print(f"🔑 API Key: {api_key[:12]}...")
    print(f"🚀 Mode: {'DRY RUN' if dry_run else 'DELETE'}")
    print()

    try:
        delete_all_customers(api_key, dry_run)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()