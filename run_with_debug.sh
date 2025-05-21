#!/bin/bash
# run_with_debug.sh - Script to run the application with debug settings

# Create debug directory
mkdir -p debug_logs

# Set environment variables for debugging
export LOG_LEVEL=DEBUG
export SAVE_WEBHOOK_BODIES=true
export SAVE_WEBHOOK_DIAGNOSTICS=true
export DEBUG_SIGNATURES=true
export DEBUG_DIR=debug_logs
export STRIPE_CLI_USED=true
export LOG_FILE=debug_logs/app.log

# Check if port is specified as argument
if [ -n "$1" ]; then
    PORT=$1
else
    PORT=8001
fi

echo "Starting server on port $PORT with debug settings..."
echo "Debug logs will be saved to ./debug_logs/"

# Run the application with debug settings
uvicorn app:app --host 0.0.0.0 --port $PORT --reload --log-level debug