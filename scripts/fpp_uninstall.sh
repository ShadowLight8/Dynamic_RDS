#!/bin/bash

sudo /home/fpp/media/plugins/Dynamic_RDS/callbacks.py --exit

#echo Uninstalling RPIO...
#sudo pip uninstall -y RPIO

echo "You can manually uninstall python3-smbus if nothing else uses it."
echo "Command is: sudo apt-get remove -y python3-smbus"
