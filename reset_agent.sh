#!/bin/bash
# Reset all agent data - sessions, artifacts, and logs

echo ""
echo "========================================"
echo "  HIP Agent Data Reset"
echo "========================================"
echo ""

# Stop the agent if running
echo "[1/3] Stopping agent if running..."
pkill -f "python main.py" 2>/dev/null || true
pkill -f "uvicorn" 2>/dev/null || true
sleep 2

# Delete sessions database
echo "[2/3] Removing sessions database..."
if [ -f "sessions.db" ]; then
    rm -f sessions.db
    echo "  - Deleted sessions.db"
else
    echo "  - sessions.db not found (already clean)"
fi

# Delete artifacts directory
echo "[3/3] Removing artifacts..."
if [ -d "my_agent/.adk/artifacts" ]; then
    rm -rf my_agent/.adk/artifacts
    echo "  - Deleted my_agent/.adk/artifacts"
else
    echo "  - artifacts directory not found (already clean)"
fi

# Also clean session.db inside my_agent if exists
if [ -f "my_agent/.adk/session.db" ]; then
    rm -f my_agent/.adk/session.db
    echo "  - Deleted my_agent/.adk/session.db"
fi

echo ""
echo "========================================"
echo "  Reset complete!"
echo "========================================"
echo ""
echo "All chat history, artifacts, and sessions have been deleted."
echo "You can now restart the agent with: python main.py"
echo ""
