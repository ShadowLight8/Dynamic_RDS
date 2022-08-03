#!/bin/bash

sudo apt-get install -y python3-smbus

#TODO: Disable onboard audio to use pwm hardware

#Workaround for missing symlink of python -> python3 on BBB
if [ -f /usr/bin/python3 ]; then
  if [ ! -f /usr/bin/python ]; then
    echo "Adding /usr/bin/python -> python3 symlink"
    sudo ln -s python3 /usr/bin/python
  fi
fi
