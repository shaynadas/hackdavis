#!/bin/bash

echo "🚀 Starting Eco-Driving Copilot..."

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

# 2. Start CV Pipeline
# Defaults to "mock". Run `./start.sh 0` to use your webcam!
SOURCE=${1:-mock}
echo "📸 Starting CV Pipeline with source: $SOURCE (Port 8001)..."
python cv_pipeline.py $SOURCE &

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
