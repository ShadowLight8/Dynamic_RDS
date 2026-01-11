#!/bin/bash

echo "Copying, if missing, optional config script to FPP scripts directory..."
cp -v -n ~/media/plugins/Dynamic_RDS/scripts/src_Dynamic_RDS_config.sh ~/media/scripts/Dynamic_RDS_config.sh

echo -e "\nInstalling python3-smbus2..."
sudo apt-get install -y python3-smbus2

if test -f /boot/firmware/config.txt; then
  echo -e "\nInstalling python3-gpiozero..."
  sudo apt-get install -y python3-gpiozero
fi

echo -e "\nRestarting FPP..."
curl -s http://localhost/api/system/fppd/restart
