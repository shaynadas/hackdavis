#!/bin/bash

DEBUG_MODE=false
if [ "$1" = "debug" ]; then
    DEBUG_MODE=true
    echo -e "\033[1;35m[DEBUG] Running in verbose mode (showing all logs)...\033[0m"
fi

# Get local IP address (macOS specific)
LOCAL_IP=$(ipconfig getifaddr en0)
if [ -z "$LOCAL_IP" ]; then
    # Fallback if en0 is not the active interface
    LOCAL_IP=$(ifconfig | grep "inet " | grep -Fv 127.0.0.1 | awk '{print $2}' | head -n 1)
fi

echo -e "\n\033[1;34m--------------------------------------------------------\033[0m"
echo -e "\033[1;37m[INFO] Starting Eco-Driving Copilot...\033[0m"
echo -e "\033[1;37m[INFO] EXPO TELEMETRY URL (Enter this in your phone app):\033[0m"
echo -e "\033[1;36m       http://${LOCAL_IP}:8000/telemetry\033[0m"
echo -e "\033[1;34m--------------------------------------------------------\033[0m\n"

# Setup cleanup so Ctrl+C kills everything gracefully
cleanup() {
    echo ""
    echo -e "\033[1;33m[INFO] Shutting down all services...\033[0m"
    # Force kill all background jobs started by this script
    kill -9 $(jobs -p) 2>/dev/null
    # Ensure any child processes (like uvicorn workers or node) are also killed
    pkill -9 -P $$ 2>/dev/null
    exit
}
trap cleanup SIGINT SIGTERM

# 1. Start Backend
if [ "$DEBUG_MODE" = true ]; then
    echo -e "\033[1;37m[START] Backend API (Port 8000)...\033[0m"
else
    echo -ne "\033[1;37m[START] Backend API (Port 8000)...\033[0m"
fi
cd backend
if [ "$DEBUG_MODE" = true ]; then
    uvicorn main:app --host 0.0.0.0 --port 8000 &
else
    uvicorn main:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &
    sleep 1 # Give it a moment to start
    echo -e " \033[1;32m[OK]\033[0m"
fi
cd ..

# 2. Start CV Pipeline (Removed live camera feed)
# SOURCE=${1:-mock}
# echo "[START] CV Pipeline with source: $SOURCE (Port 8001)..."
# python cv_pipeline.py $SOURCE &

# 3. Start Frontend
if [ "$DEBUG_MODE" = true ]; then
    echo -e "\033[1;37m[START] Frontend Dashboard...\033[0m"
else
    echo -ne "\033[1;37m[START] Frontend Dashboard...\033[0m"
fi
cd backseat-driver
if [ "$DEBUG_MODE" = true ]; then
    npm run dev &
else
    npm run dev > /dev/null 2>&1 &
    sleep 1 # Give it a moment to start
    echo -e " \033[1;32m[OK]\033[0m"
fi
cd ..

echo ""
echo -e "\033[1;32m[SUCCESS] All services started successfully.\033[0m"
echo -e "\033[1;36m[INFO] Dashboard available at: http://localhost:5173\033[0m"
if [ "$DEBUG_MODE" = false ]; then
    echo -e "\033[1;30m[TIP] Run './start.sh debug' to see detailed logs and status codes.\033[0m"
fi
echo -e "\033[1;33m[INFO] Press Ctrl+C to stop all services.\033[0m"
echo -e "\033[1;34m--------------------------------------------------------\033[0m"

# Wait for all background jobs to finish (which is never, until Ctrl+C)
wait
