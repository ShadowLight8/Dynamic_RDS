#!/bin/bash
###############################################################################
# Dynamic_RDS_config.sh - Used to change the PS and/or RT RDS Strings         #
###############################################################################

# Set the PS text (set to '' or comment out to leave unchanged)
PS='{T}|{A}[|{P} of {C}]|Merry|Christ-|  -mas!'

# Set the RT text (set to '' or comment out to leave unchanged)
RT='{T}[ by {A}][ - Track {P} of {C}]|Merry Christmas!'

if [ "$PS" != "" ]; then
echo 'Setting PS Style Text to: '$PS
curl -d "$PS" -X POST http://localhost/api/plugin/Dynamic_RDS/settings/DynRDSPSStyle
echo -e '\n'
fi

if [ "$RT" != "" ]; then
echo 'Setting RT Style Text to: '$RT
curl -d "$RT" -X POST http://localhost/api/plugin/Dynamic_RDS/settings/DynRDSRTStyle
echo -e '\n'
fi

echo 'Applying changes...'

curl http://localhost/api/plugin/Dynamic_RDS/FastUpdate

echo 'Complete'
