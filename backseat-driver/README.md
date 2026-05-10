# Backseat Driver Dashboard

This is the standalone frontend dashboard for the Eco-Driving Recommendation API. It acts as an admin/god-view interface to monitor the real-time pipeline of perception, location, road context, and voice configuration data.

## Getting Started

1. Navigate to the `backseat-driver` directory.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
4. Start the development server:
   ```bash
   npm run dev
   ```

## Configuration

By default, the dashboard expects the backend to be running on `http://localhost:8000`.

### Physical Road Testing (Raspberry Pi)

If you are running the backend on a Raspberry Pi for live road testing and opening the dashboard on a laptop or phone, you must change the `VITE_API_BASE_URL` in your `.env` file to the Pi's local network IP.

Example:
```env
VITE_API_BASE_URL=http://192.168.1.100:8000
VITE_VIDEO_STREAM_URL=http://192.168.1.100:8001/video_feed
```

## Browser GPS Streaming

The frontend must actively send browser location to the backend. Running the dashboard alone does not automatically update backend location. 

- Click **"Start GPS Stream"** to call `navigator.geolocation.watchPosition`.
- The browser may return `speed` as `null` when stationary, so the app handles this and sends `speed_mph: 0`.
- On Mac, ensure you enable location permissions for Chrome/Safari in System Settings.
- For road testing on a phone, open the dashboard on the phone's browser and press "Start GPS Stream".
- For Pi road testing, make sure `VITE_API_BASE_URL` points to the Pi's IP, not localhost.

## Features

- **Live Video Feed**: Displays the MJPEG stream from the CV processing camera, or uses local webcam as a fallback.
- **VIN Voice Capture**: A unified button allows the user to record their voice and securely capture the VIN.
- **Audio Feedback**: The dashboard can synthesize and play the generated eco-driving advice using ElevenLabs TTS.
- **Telemetry Charts**: Real-time graphing of Speed (Current, Optimal, Traffic) and RPM/Eco Score.
- **Raw JSON Debugging**: Direct access to the raw payload data being transmitted between the phone, CV engine, and backend.
