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

# 2. Start CV Pipeline (webcam, source=0, port 8001)
if [ "$DEBUG_MODE" = true ]; then
    echo -e "\033[1;37m[START] CV Pipeline (Webcam, Port 8001)...\033[0m"
else
    echo -ne "\033[1;37m[START] CV Pipeline (Webcam, Port 8001)...\033[0m"
fi
if [ "$DEBUG_MODE" = true ]; then
    python cv_pipeline.py 0 &
else
    python cv_pipeline.py 0 > /dev/null 2>&1 &
    sleep 2 # Give YOLO a moment to load
    echo -e " \033[1;32m[OK]\033[0m"
fi

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

# 4. Start Arduino Bridge (optional — skips if no Arduino detected)
ARDUINO_PORT=$(python -c "
import serial.tools.list_ports, sys
ports = list(serial.tools.list_ports.comports())
for p in ports:
    d = (p.description or '').lower()
    h = (p.hwid or '').lower()
    if 'arduino' in d or 'uno' in d or '2341' in h:
        print(p.device); sys.exit(0)
for p in ports:
    if 'bluetooth' not in (p.description or '').lower():
        print(p.device); sys.exit(0)
" 2>/dev/null)

if [ -n "$ARDUINO_PORT" ]; then
    if [ "$DEBUG_MODE" = true ]; then
        echo -e "\033[1;37m[START] Arduino Bridge (${ARDUINO_PORT})...\033[0m"
        python arduino/bridge.py --port "$ARDUINO_PORT" &
    else
        echo -ne "\033[1;37m[START] Arduino Bridge (${ARDUINO_PORT})...\033[0m"
        python arduino/bridge.py --port "$ARDUINO_PORT" > /dev/null 2>&1 &
        sleep 1
        echo -e " \033[1;32m[OK]\033[0m"
    fi
else
    echo -e "\033[1;37m[START] Arduino Bridge...\033[0m\033[1;30m [SKIP] No Arduino detected.\033[0m"
fi

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
