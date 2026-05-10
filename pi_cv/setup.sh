#!/bin/bash
# setup.sh — eco-drive CV pipeline installer for Raspberry Pi 4B
# Idempotent: safe to re-run. Assumes Raspberry Pi OS 64-bit.

set -e

echo "========================================================"
echo "  Eco-drive CV pipeline — Pi 4B installer"
echo "========================================================"
echo

# ── Architecture check ───────────────────────────────────────
if [ "$(uname -m)" != "aarch64" ]; then
    echo "ERROR: 64-bit OS required. uname -m says: $(uname -m)"
    echo "Reflash Raspberry Pi OS 64-bit before running this."
    exit 1
fi
echo "[setup] arch ok (aarch64)"

# ── apt packages ─────────────────────────────────────────────
echo "[setup] installing apt packages..."
sudo apt update -qq
sudo apt install -y \
    python3-pip python3-venv \
    libatlas-base-dev libjpeg-dev libopenblas-dev \
    v4l-utils

# ── video group ──────────────────────────────────────────────
if ! groups | grep -qw video; then
    echo "[setup] adding $USER to video group"
    sudo usermod -aG video "$USER"
    NEEDS_RELOGIN=1
fi

# ── swap (NCNN export needs ~2 GB) ───────────────────────────
SWAP_MB=$(free -m | awk '/Swap/ {print $2}')
if [ "$SWAP_MB" -lt 1500 ] && [ -f /etc/dphys-swapfile ]; then
    echo "[setup] increasing swap to 2 GB (current: ${SWAP_MB} MB)"
    sudo dphys-swapfile swapoff
    sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
fi

# ── venv ─────────────────────────────────────────────────────
if [ ! -d venv ]; then
    echo "[setup] creating venv"
    python3 -m venv venv
fi

# Activate for the rest of this script
# shellcheck disable=SC1091
source venv/bin/activate

# ── python deps ──────────────────────────────────────────────
echo "[setup] installing python packages (10-15 min, fetches PyTorch)"
pip install --upgrade pip --quiet
pip install -r requirements.txt

# ── NCNN export ──────────────────────────────────────────────
if [ ! -d yolov8n_ncnn_model ]; then
    echo "[setup] exporting YOLOv8n to NCNN (5-10 min)"
    python export_ncnn.py
else
    echo "[setup] yolov8n_ncnn_model/ already exists, skipping export"
fi

# ── done ─────────────────────────────────────────────────────
echo
echo "========================================================"
echo "  Setup complete."
echo "========================================================"
echo
if [ "${NEEDS_RELOGIN:-0}" = "1" ]; then
    echo "IMPORTANT: log out and back in so 'video' group applies."
    echo
fi
echo "Next steps:"
echo "  source venv/bin/activate"
echo "  python probe_camera.py            # find your webcam index"
echo "  python cv_view.py <index>         # see live detection in browser"
echo
