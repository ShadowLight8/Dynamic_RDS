#!/bin/bash

echo "Copying, if missing, optional config script to FPP scripts directory..."
cp -v -n ~/media/plugins/Dynamic_RDS/scripts/src_Dynamic_RDS_config.sh ~/media/scripts/Dynamic_RDS_config.sh

echo -e "\nInstalling python3-smbus..."
sudo apt-get install -y python3-smbus

if test -f /boot/config.txt; then
  echo -e "\nInstalling python3-rpi-lgpio..."
  sudo apt-get install -y python3-rpi-lgpio
fi

echo -e "\nRestarting FPP..."
curl -s http://localhost/api/system/fppd/restart
