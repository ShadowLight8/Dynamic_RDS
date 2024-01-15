#!/usr/bin/python3

import logging
import json
import os
import errno
import subprocess
import socket
import sys
from datetime import date
from sys import argv

from config import config,read_config_from_file

def logUnhandledException(eType, eValue, eTraceback):
  logging.error("Unhandled exception", exc_info=(eType, eValue, eTraceback))
sys.excepthook = logUnhandledException

if len(argv) <= 1:
  print('Usage:')
  print('   --list     | Used by fppd at startup. Used to start up the Dynamic_RDS_Engine.py script')
  print('   --update   | Function by Dynamic_RDS.php to apply dynamic settings to the transmitter')
  print('   --reset    | Function by Dynamic_RDS.php to reset the GPIO pin')
  print('   --exit     | Function used to shutdown the Dynamic_RDS_Engine.py script')
  print('   --type media --data \'{..json..}\'    | Used by fppd when a new items starts in a playlist')
  print('   --type playlist --data \'{..json..}\' | Used by fppd when a playlist starts or stops')
  print('Note: Running with sudo might be needed for manual execution')
  sys.exit()

script_dir = os.path.dirname(os.path.abspath(argv[0]))

logging.basicConfig(filename=script_dir + '/Dynamic_RDS_callbacks.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')

read_config_from_file()

logging.getLogger().setLevel(config['DynRDSCallbackLogLevel'])

logging.info('--- %s', date.today())
logging.debug('Arguments %s', argv[1:])

# If smbus is missing, don't try to start up the Engine as it will fail and cause FPP to hang
try:
  import smbus
except ImportError as impErr:
  logging.error("Failed to import smbus %s", impErr.args[0])
  sys.exit(1)

#if config['DynRDSTransmitter'] == "QN8066":
#  try:
#    import RPIO.PWM
#  except ImportError as impErr:
#    logging.error("Failed to import RPIO %s", impErr.args[0])
#    sys.exit(1)

# Environ has a few useful items when FPPD runs callbacks.py, but logging it all the time, even at debug, is too much
#logging.debug('Environ %s', os.environ)

# Always start the Engine since it does the real work for all command
updater_path = script_dir + '/Dynamic_RDS_Engine.py'
engineStarted = False
try:
  logging.debug('Checking for socket lock by %s', updater_path)
  lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
  lock_socket.bind('\0Dynamic_RDS_Engine')
  lock_socket.close()
  logging.debug('Lock not found')

  # Short circuit if Engine isn't running and command is to shut it down
  if argv[1] == '--exit':
    logging.info('Exit, but not running')
    sys.exit()

  logging.info('Starting %s', updater_path)
  devnull = open(os.devnull, 'w', encoding='UTF-8')
  subprocess.Popen(['python3', updater_path], stdin=devnull, stdout=devnull, stderr=devnull, close_fds=True)
  engineStarted = True
except socket.error:
  logging.debug('Lock found - %s is running', updater_path)

# Always setup FIFO - Expects Engine to be running to open the read side of the FIFO
fifo_path = script_dir + '/Dynamic_RDS_FIFO'
try:
  logging.debug('Setting up write side of fifo %s', fifo_path)
  os.mkfifo(fifo_path)
except OSError as oe:
  if oe.errno != errno.EEXIST:
    raise
  logging.debug('Fifo already exists')

with open(fifo_path, 'w', encoding='UTF-8') as fifo:
  logging.info('Processing %s', argv[1])

  # If Engine was started AND the argument isn't --list, INIT must be sent to Engine before the requested argument
  if engineStarted and argv[1] != '--list':
    logging.info('Engine restart detected, sending INIT')
    fifo.write('INIT\n')

  if argv[1] == '--list':
    # Typically called first and will block if read side isn't open
    fifo.write('INIT\n')
    print('media,playlist')

  elif argv[1] == '--update':
    # Not used by FPPD, but used by Dynamic_RDS.php
    fifo.write('UPDATE\n')

  elif argv[1] == '--reset':
    # Not used by FPPD, but used by Dynamic_RDS.php
    fifo.write('RESET\n')

  elif argv[1] == '--exit':
    # Not used by FPPD, but useful for testing or scripting
    fifo.write('EXIT\n')

  elif argv[1] == '--type' and argv[2] == 'media':
    logging.info('Type media')
    try:
      j = json.loads(argv[4])
    except Exception:
      logging.exception('Media JSON')

    # When default values are sent over fifo, other side more or less ignores them
    media_type = j['type'] if 'type' in j else 'pause'
    media_title = j['title'] if 'title' in j else ''
    media_artist = j['artist'] if 'artist' in j else ''
    media_tracknum = str(j['track']) if 'track' in j else '0'
    media_length = str(j['length']) if 'length' in j else '0'

    logging.debug('Type is %s', media_type)
    logging.debug('Title is %s', media_title)
    logging.debug('Artist is %s', media_artist)
    logging.debug('Tracknum is %s', media_tracknum)
    logging.debug('Length is %s', media_length)

    # TODO: Review this case - what to send to Engine for other playlist events
    if media_type in ('pause', 'event'):
      fifo.write('T\n') # Blank Title
      fifo.write('A\n') # Blank Artist
    else:
      fifo.write('T' + media_title + '\n')
      fifo.write('A' + media_artist + '\n')
    fifo.write('N' + media_tracknum + '\n')
    fifo.write('L' + media_length + '\n') # Length is always sent last to optimize when the Engine has to update the RDS Data

  elif argv[1] == '--type' and argv[2] == 'playlist':
    logging.info('Type playlist')

    try:
      j = json.loads(argv[4])
    except ValueError:
      logging.exception('Playlist JSON')

    playlist_action = j['Action'] if 'Action' in j else 'stop'

    logging.info('Playlist action %s', j['Action'])

    if playlist_action == 'start': # or playlist_action == 'playing':
      fifo.write('START\n')
    elif playlist_action == 'stop':
      fifo.write('STOP\n')
    if j['Section'] == 'MainPlaylist':
      fifo.write('MAINLIST' + j['name'] + '\n')
  logging.debug('Processing done')
