#!/bin/bash
# Setup Android phone as Artemis II display — run from Pi
set -e

echo "=== Artemis II Phone Display Setup ==="

# Install ADB if needed
if ! command -v adb &>/dev/null; then
    echo "Installing ADB..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq android-tools-adb
fi

echo "Waiting for phone..."
adb wait-for-device
MODEL=$(adb shell getprop ro.product.model 2>/dev/null | tr -d '\r')
echo "Found: $MODEL"

# Screen always on
adb shell settings put system screen_off_timeout 2147483647
adb shell svc power stayon true
adb shell settings put system screen_brightness_mode 0
adb shell settings put system screen_brightness 180
echo "Screen: always on, brightness set"

# ADB reverse: phone's localhost:8080 → Pi's localhost:8080
adb reverse tcp:8080 tcp:8080
echo "Port forward: phone:8080 → Pi:8080"

# Launch Chrome fullscreen
adb shell "am start -a android.intent.action.VIEW -d 'http://localhost:8080' com.android.chrome" 2>/dev/null
echo "Chrome launched — tap screen once for fullscreen"
echo ""
echo "=== Done ==="
