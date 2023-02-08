#!/bin/bash

echo Installing python3-smbus...
sudo apt-get install -y python3-smbus

if test -f /boot/config.txt; then
  echo Installing RPi.GPIO
  sudo apt-get install -y python3-rpi.gpio
fi

echo Restarting FPP...
curl -s http://localhost/api/system/fppd/restart
echo -e "\n...Done"

