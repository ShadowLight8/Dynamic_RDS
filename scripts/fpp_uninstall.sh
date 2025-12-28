#!/bin/bash

echo "Stopping Dynamic RDS engine..."
sudo /home/fpp/media/plugins/Dynamic_RDS/callbacks.py --exit

if cmp -s ~/media/plugins/Dynamic_RDS/scripts/src_Dynamic_RDS_config.sh ~/media/scripts/Dynamic_RDS_config.sh; then
 echo -e "\nRemoving optional config script from FPP scripts directory..."
 rm ~/media/scripts/Dynamic_RDS_config.sh
else
 echo -e "\nLeaving modified optional config script"
fi

