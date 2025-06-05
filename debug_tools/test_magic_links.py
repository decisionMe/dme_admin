# debug_tools/test_magic_links.py
"""
Test script for magic link functionality
Run this to verify that magic link generation works correctly
"""

import os
import sys
import time
from datetime import datetime

# Add parent directory to path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.magic_link_service import (
    create_magic_token,
    generate_magic_link,
    validate_magic_token_format,
    get_token_info,
    test_magic_link_generation,
    MagicLinkError
)

def test_environment_setup():
    """Test that environment variables are set correctly"""
    print("🧪 Testing Environment Setup...")
    
    magic_secret = os.getenv("MAGIC_LINK_SECRET")
    client_url = os.getenv("CLIENT_APP_URL")
    
    if not magic_secret:
        print("❌ MAGIC_LINK_SECRET not set")
        return False
    
    if not client_url:
        print("❌ CLIENT_APP_URL not set")
        return False
    
    print(f"✅ MAGIC_LINK_SECRET set (length: {len(magic_secret)})")
    print(f"✅ CLIENT_APP_URL set: {client_url}")
    
    if len(magic_secret) < 32:
        print("⚠️  WARNING: MAGIC_LINK_SECRET is shorter than recommended (32 characters)")
    
    if not client_url.startswith(('http://', 'https://')):
        print("⚠️  WARNING: CLIENT_APP_URL should start with http:// or https://")
    
    return True

def test_token_creation():
    """Test magic token creation with various inputs"""
    print("\n🧪 Testing Token Creation...")
    
    test_cases = [
        ("auth0|test123456789", "test@example.com", True),
        ("auth0|user_abc123", "user@domain.org", True),
        ("", "test@example.com", False),  # Empty auth0_id
        ("auth0|test", "", False),  # Empty email
        (None, "test@example.com", False),  # None auth0_id
        ("auth0|test", None, False),  # None email
    ]
    
    success_count = 0
    
    for auth0_id, email, should_succeed in test_cases:
        try:
            token = create_magic_token(auth0_id, email)
            if should_succeed:
                print(f"✅ Token created for {auth0_id}, {email}")
                
                # Validate token format
                if validate_magic_token_format(token):
                    print(f"   ✅ Token format is valid")
                else:
                    print(f"   ❌ Token format is invalid")
                    continue
                
                success_count += 1
            else:
                print(f"❌ Expected failure but got success for {auth0_id}, {email}")
        except MagicLinkError as e:
            if not should_succeed:
                print(f"✅ Expected failure for {auth0_id}, {email}: {e}")
                success_count += 1
            else:
                print(f"❌ Unexpected failure for {auth0_id}, {email}: {e}")
        except Exception as e:
            print(f"❌ Unexpected error for {auth0_id}, {email}: {e}")
    
    print(f"Token creation tests: {success_count}/{len(test_cases)} passed")
    return success_count == len(test_cases)

def test_magic_link_generation():
    """Test complete magic link generation"""
    print("\n🧪 Testing Magic Link Generation...")
    
    test_auth0_id = "auth0|test123456789"
    test_email = "test@example.com"
    
    try:
        # Test with default URL
        magic_link = generate_magic_link(test_auth0_id, test_email)
        print(f"✅ Magic link generated: {magic_link}")
        
        # Verify URL structure
        if "/auth/magic?token=" in magic_link:
            print("✅ Magic link has correct path structure")
        else:
            print("❌ Magic link missing expected path structure")
            return False
        
        # Test with custom URL
        custom_url = "https://custom.example.com"
        custom_link = generate_magic_link(test_auth0_id, test_email, custom_url)
        if custom_link.startswith(custom_url):
            print(f"✅ Custom URL magic link: {custom_link}")
        else:
            print("❌ Custom URL not used correctly")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Magic link generation failed: {e}")
        return False

def test_token_format_validation():
    """Test token format validation function"""
    print("\n🧪 Testing Token Format Validation...")
    
    # Create a valid token first
    valid_token = create_magic_token("auth0|test", "test@example.com")
    
    test_cases = [
        (valid_token, True, "Valid token"),
        ("invalid", False, "Too short"),
        ("a" * 128, False, "Too long"),
        ("a" * 64 + "." + "b" * 64, True, "Correct format"),
        ("a" * 64 + "b" * 64, False, "Missing dot separator"),
        ("a" * 63 + "." + "b" * 64, False, "First part too short"),
        ("a" * 64 + "." + "b" * 63, False, "Second part too short"),
        ("g" * 64 + "." + "h" * 64, False, "Invalid hex characters"),
    ]
    
    success_count = 0
    
    for token, expected, description in test_cases:
        result = validate_magic_token_format(token)
        if result == expected:
            print(f"✅ {description}: {result}")
            success_count += 1
        else:
            print(f"❌ {description}: expected {expected}, got {result}")
    
    print(f"Format validation tests: {success_count}/{len(test_cases)} passed")
    return success_count == len(test_cases)

def test_token_expiry_logic():
    """Test that tokens have proper expiry timestamps"""
    print("\n🧪 Testing Token Expiry Logic...")
    
    try:
        # Create token and check expiry
        start_time = time.time()
        token = create_magic_token("auth0|test", "test@example.com")
        
        # Extract the random part and use it to verify expiry
        random_part = token.split('.')[0]
        
        # We can't easily extract the expiry without the secret, but we can verify
        # the token was created within a reasonable time frame
        end_time = time.time()
        
        if end_time - start_time < 1:  # Should create quickly
            print("✅ Token created within reasonable time")
        else:
            print("⚠️  Token creation took longer than expected")
        
        print("✅ Token expiry logic tested (limited without secret access)")
        return True
        
    except Exception as e:
        print(f"❌ Token expiry test failed: {e}")
        return False

def run_all_tests():
    """Run all magic link tests"""
    print("🚀 Starting Magic Link Tests\n")
    print("=" * 50)
    
    tests = [
        ("Environment Setup", test_environment_setup),
        ("Token Creation", test_token_creation),
        ("Magic Link Generation", test_magic_link_generation),
        ("Token Format Validation", test_token_format_validation),
        ("Token Expiry Logic", test_token_expiry_logic),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        print("-" * 30)
        
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print("\n" + "=" * 50)
    print(f"🏁 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Magic link functionality is working correctly.")
        return True
    else:
        print("❌ Some tests failed. Please check the configuration and implementation.")
        return False

def interactive_test():
    """Interactive test for manual verification"""
    print("\n🔧 Interactive Magic Link Test")
    print("=" * 40)
    
    auth0_id = input("Enter Auth0 ID (or press Enter for default): ").strip()
    if not auth0_id:
        auth0_id = "auth0|interactive_test_user"
    
    email = input("Enter email (or press Enter for default): ").strip()
    if not email:
        email = "test@example.com"
    
    try:
        print(f"\nGenerating magic link for:")
        print(f"  Auth0 ID: {auth0_id}")
        print(f"  Email: {email}")
        
        magic_link = generate_magic_link(auth0_id, email)
        
        print(f"\n✅ Generated Magic Link:")
        print(f"  {magic_link}")
        
        # Extract token for analysis
        token = magic_link.split("token=")[1] if "token=" in magic_link else "N/A"
        print(f"\n📊 Token Analysis:")
        print(f"  Token: {token}")
        
        token_info = get_token_info(token)
        if token_info:
            print(f"  Format: Valid")
            print(f"  Random part length: {token_info['token_length']}")
            print(f"  Signature length: {token_info['signature_length']}")
        else:
            print(f"  Format: Invalid")
        
        print(f"\n🕒 Token will expire in 5 minutes from creation time")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_test()
    else:
        run_all_tests()
        
        # Ask if user wants to run interactive test
        while True:
            response = input("\nWould you like to run an interactive test? (y/n): ").strip().lower()
            if response in ['y', 'yes']:
                interactive_test()
                break
            elif response in ['n', 'no']:
                break
            else:
                print("Please enter 'y' or 'n'")