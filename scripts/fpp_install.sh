#!/bin/bash

echo Installing python3-smbus...
sudo apt-get install -y python3-smbus

echo ========================================
echo === REBOOT OF FPP HIGHLY RECOMMENDED ===
echo ========================================

#TODO: Disable onboard audio to use pwm hardware
