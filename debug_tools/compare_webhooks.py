# debug_tools/compare_webhooks.py
#!/usr/bin/env python3
"""
Tool to compare webhooks received from Stripe with the configured webhook secret.
This helps diagnose signature verification issues.
"""

import os
import sys
import glob
import hmac
import hashlib
import json
import argparse
from datetime import datetime

def compute_signature(payload, timestamp, secret):
    """Compute Stripe webhook signature using the same algorithm as Stripe"""
    signed_payload = f"{timestamp}.{payload}"
    return hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def extract_timestamp(sig_header):
    """Extract timestamp from Stripe signature header"""
    for part in sig_header.split(','):
        if part.startswith('t='):
            return part[2:]
    return None

def analyze_webhook_file(file_path, webhook_secret):
    """Analyze a webhook diagnostic file and verify the signature"""
    print(f"\nAnalyzing file: {file_path}")

    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()

        # Extract information from the file
        timestamp_line = next((line for line in lines if line.startswith("Timestamp:")), None)
        sig_header_line = next((line for line in lines if line.startswith("Signature Header:")), None)
        secret_line = next((line for line in lines if line.startswith("Webhook Secret First 4 Chars:")), None)

        if not sig_header_line:
            print("  Error: No signature header found in the file")
            return

        sig_header = sig_header_line.split("Signature Header: ", 1)[1].strip()
        print(f"  Signature header: {sig_header[:30]}...")

        # Find corresponding body file
        file_id = os.path.basename(file_path).replace('webhook_sig_', '').replace('.txt', '')
        body_file = os.path.join(os.path.dirname(file_path), f"webhook_body_req_{file_id}.bin")

        if not os.path.exists(body_file):
            print(f"  Error: Corresponding body file not found: {body_file}")
            return

        # Read the body
        with open(body_file, 'rb') as f:
            body = f.read()

        print(f"  Body size: {len(body)} bytes")

        # Extract timestamp from signature header
        timestamp = extract_timestamp(sig_header)
        if not timestamp:
            print("  Error: Could not extract timestamp from signature header")
            return

        print(f"  Timestamp: {timestamp}")

        # Compute expected signature using provided webhook secret
        expected_sig = compute_signature(body.decode('utf-8', errors='replace'), timestamp, webhook_secret)
        print(f"  Expected signature (with provided secret): {expected_sig[:30]}...")

        # Check if expected signature is in the header
        v1_signatures = [part.split('=')[1] for part in sig_header.split(',') if part.startswith('v1=')]

        if not v1_signatures:
            print("  Error: No v1 signatures found in header")
            return

        for i, sig in enumerate(v1_signatures):
            print(f"  Actual signature {i+1}: {sig[:30]}...")
            if sig == expected_sig:
                print(f"  MATCH! Signature {i+1} matches the expected signature with provided secret")
            else:
                print(f"  NO MATCH. Signature {i+1} does not match expected signature")

        # Additional diagnostics
        print("\n  Additional diagnostics:")
        print(f"  - First 100 bytes of body: {body[:100]}")

        try:
            json_body = json.loads(body)
            print(f"  - Valid JSON: Yes")
            if 'id' in json_body:
                print(f"  - Event ID: {json_body['id']}")
            if 'type' in json_body:
                print(f"  - Event type: {json_body['type']}")
        except json.JSONDecodeError:
            print(f"  - Valid JSON: No (parsing error)")

    except Exception as e:
        print(f"  Error analyzing file: {e}")

def main():
    parser = argparse.ArgumentParser(description='Analyze Stripe webhook diagnostics')
    parser.add_argument('--secret', required=True, help='Stripe webhook secret for verification')
    parser.add_argument('--dir', default='debug_logs', help='Directory containing diagnostic files')

    args = parser.parse_args()

    # Find all diagnostic files
    sig_files = glob.glob(os.path.join(args.dir, 'webhook_sig_*.txt'))

    if not sig_files:
        print(f"No webhook diagnostic files found in {args.dir}")
        return

    print(f"Found {len(sig_files)} webhook diagnostic files")

    # Analyze each file
    for file_path in sorted(sig_files):
        analyze_webhook_file(file_path, args.webhook_secret)

    print("\nAnalysis complete!")

if __name__ == "__main__":
    main()