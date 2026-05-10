#!/bin/bash

# Get local IP address (macOS specific)
LOCAL_IP=$(ipconfig getifaddr en0)
if [ -z "$LOCAL_IP" ]; then
    # Fallback if en0 is not the active interface
    LOCAL_IP=$(ifconfig | grep "inet " | grep -Fv 127.0.0.1 | awk '{print $2}' | head -n 1)
fi

echo -e "\n\033[1;36m=================================================================\033[0m"
echo -e "\033[1;32m🚀 Starting Eco-Driving Copilot...\033[0m"
echo -e "\033[1;33m📱 EXPO TELEMETRY URL (Enter this in your phone app):\033[0m"
echo -e "\033[1;37;44m    http://${LOCAL_IP}:8000/telemetry    \033[0m"
echo -e "\033[1;36m=================================================================\033[0m\n"
# Setup cleanup so Ctrl+C kills everything gracefully
cleanup() {
    echo ""
    echo "🛑 Shutting down all services..."
    # Force kill all background jobs started by this script
    kill -9 $(jobs -p) 2>/dev/null
    # Ensure any child processes (like uvicorn workers or node) are also killed
    pkill -9 -P $$ 2>/dev/null
    exit
}
trap cleanup SIGINT SIGTERM

# 1. Start Backend
echo "📦 Starting Backend API (Port 8000)..."
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 &
cd ..

# 2. Start CV Pipeline (Removed live camera feed)
# SOURCE=${1:-mock}
# echo "📸 Starting CV Pipeline with source: $SOURCE (Port 8001)..."
# python cv_pipeline.py $SOURCE &

# 3. Start Frontend
echo "💻 Starting Frontend Dashboard..."
cd backseat-driver
npm run dev &
cd ..

echo ""
echo "✅ All services started! Press Ctrl+C to stop everything at once."
echo "👉 View the dashboard at: http://localhost:5173"
echo "--------------------------------------------------------"

# Wait for all background jobs to finish (which is never, until Ctrl+C)
wait
