#!/bin/bash

echo Installing python3-smbus...
sudo apt-get install -y python3-smbus

echo Installing RPIO...
sudo pip install -U RPIO

echo Restarting FPP...
curl -s http://localhost/api/system/fppd/restart
echo ...Done

