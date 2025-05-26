#!/usr/bin/env python3
"""
Script to list and expire checkout sessions from Stripe account.
This will help clean up dangling sessions that are causing 404 errors.
"""

import stripe
import sys
from datetime import datetime

def cleanup_sessions(api_key: str, dry_run: bool = True) -> None:
    """
    List and optionally expire checkout sessions.
    
    Args:
        api_key: Stripe test secret key (sk_test_...)
        dry_run: If True, only list sessions without expiring
    """
    stripe.api_key = api_key
    
    print(f"🔍 {'DRY RUN: ' if dry_run else ''}Fetching all checkout sessions...")
    
    # Get all checkout sessions
    sessions = []
    starting_after = None
    
    while True:
        if starting_after:
            response = stripe.checkout.Session.list(limit=100, starting_after=starting_after)
        else:
            response = stripe.checkout.Session.list(limit=100)
        
        sessions.extend(response.data)
        
        if not response.has_more:
            break
        
        starting_after = response.data[-1].id
    
    print(f"📊 Found {len(sessions)} checkout sessions")
    
    if not sessions:
        print("✅ No sessions found!")
        return
    
    # Categorize sessions
    open_sessions = [s for s in sessions if s.status == 'open']
    completed_sessions = [s for s in sessions if s.status == 'complete']
    expired_sessions = [s for s in sessions if s.status == 'expired']
    
    print(f"\n📋 Session breakdown:")
    print(f"  🟢 Open: {len(open_sessions)}")
    print(f"  ✅ Complete: {len(completed_sessions)}")
    print(f"  ❌ Expired: {len(expired_sessions)}")
    
    # List sessions
    print(f"\n📋 All sessions:")
    for i, session in enumerate(sessions, 1):
        created = datetime.fromtimestamp(session.created).strftime('%Y-%m-%d %H:%M:%S')
        status_emoji = {'open': '🟢', 'complete': '✅', 'expired': '❌'}.get(session.status, '❓')
        print(f"  {i:3d}. {session.id} - {status_emoji} {session.status} - {session.mode} - {created}")
    
    if dry_run:
        print(f"\n⚠️  DRY RUN: Would expire {len(open_sessions)} open sessions")
        print("   Run with --expire flag to actually expire them")
        print("   (Note: Expired and completed sessions cannot be deleted via API)")
        return
    
    if not open_sessions:
        print(f"\n✅ No open sessions to expire!")
        return
    
    # Confirm expiration
    print(f"\n⚠️  About to EXPIRE {len(open_sessions)} open sessions!")
    print("   (This will make them unusable but they'll still appear in your dashboard)")
    confirm = input("Type 'EXPIRE' to confirm: ")
    
    if confirm != "EXPIRE":
        print("❌ Expiration cancelled")
        return
    
    # Expire sessions
    print(f"\n⏰ Expiring {len(open_sessions)} open sessions...")
    expired_count = 0
    errors = []
    
    for i, session in enumerate(open_sessions, 1):
        try:
            stripe.checkout.Session.expire(session.id)
            expired_count += 1
            print(f"  ✅ {i:3d}/{len(open_sessions)} Expired {session.id}")
        except Exception as e:
            error_msg = f"Failed to expire {session.id}: {e}"
            errors.append(error_msg)
            print(f"  ❌ {i:3d}/{len(open_sessions)} {error_msg}")
    
    # Summary
    print(f"\n📊 Expiration Summary:")
    print(f"  ✅ Successfully expired: {expired_count}")
    print(f"  ❌ Failed to expire: {len(errors)}")
    
    if errors:
        print(f"\n❌ Errors:")
        for error in errors:
            print(f"  - {error}")
    
    print(f"\n✅ Cleanup complete!")
    print(f"💡 Tip: Old expired sessions will eventually be cleaned up by Stripe automatically")

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python cleanup_stripe_sessions.py <stripe_test_key> [--expire]")
        print("  --expire: Actually expire open sessions (default is dry run)")
        sys.exit(1)
    
    api_key = sys.argv[1]
    dry_run = "--expire" not in sys.argv
    
    # Validate API key
    if not api_key.startswith("sk_test_"):
        print("❌ Error: API key must be a test key starting with 'sk_test_'")
        sys.exit(1)
    
    print("🧹 Stripe Checkout Session Cleanup Tool")
    print(f"🔑 API Key: {api_key[:12]}...")
    print(f"🚀 Mode: {'DRY RUN' if dry_run else 'EXPIRE'}")
    print()
    
    try:
        cleanup_sessions(api_key, dry_run)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()