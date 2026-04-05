#!/bin/bash
# Artemis II Tracker — Raspberry Pi 5 setup script
# Run this on the Pi: bash setup_pi.sh

set -e

echo "=== Artemis II Tracker — Pi Setup ==="

# System deps
echo "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv python3-dev \
    i2c-tools libopenjp2-7 fonts-dejavu-core

# Enable SPI and I2C
echo "Enabling SPI and I2C..."
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0

# Set SPI buffer size for LED strip
if ! grep -q "spidev.bufsiz" /boot/firmware/cmdline.txt 2>/dev/null; then
    echo "Setting SPI buffer size..."
    sudo sed -i 's/$/ spidev.bufsiz=65536/' /boot/firmware/cmdline.txt
fi

# Python venv
echo "Setting up Python environment..."
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install httpx
pip install adafruit-circuitpython-neopixel-spi adafruit-blinka
pip install luma.oled Pillow

echo ""
echo "=== Setup complete ==="
echo ""
echo "Test it:  source .venv/bin/activate && python -m artemis --demo"
echo "Run live: source .venv/bin/activate && python -m artemis"
echo ""
echo "NOTE: If this is the first time enabling SPI, reboot first:"
echo "  sudo reboot"
