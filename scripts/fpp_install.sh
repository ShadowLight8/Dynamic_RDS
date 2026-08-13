#!/bin/bash
set -e

source "${FPPDIR}/scripts/common"

echo "Copying, if missing, optional config script to FPP scripts directory..."
cp -v -n "${PLUGINDIR}/Dynamic_RDS/scripts/src_Dynamic_RDS_config.sh" "${MEDIADIR}/scripts/Dynamic_RDS_config.sh"

echo -e "\nInstalling python3-smbus2..."
apt-get install -y python3-smbus2

if test -f /boot/firmware/config.txt; then
  echo -e "\nInstalling python3-gpiozero..."
  apt-get install -y python3-gpiozero
fi

echo -e "\nFlagging FPP for restart..."
setSetting restartFlag 1
