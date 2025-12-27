#!/usr/bin/python3

import logging
import json
import os
import errno
import subprocess
import socket
import sys
import time

from sys import argv
from config import config,read_config_from_file

def logUnhandledException(eType, eValue, eTraceback):
  logging.error('Unhandled exception', exc_info=(eType, eValue, eTraceback))
sys.excepthook = logUnhandledException

def check_engine_running():
  try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
      sock.bind('\0Dynamic_RDS_Engine')
      return False  # Not running
  except socket.error:
    return True  # Running

if len(argv) <= 1:
  print('Usage:')
  print('   --list                              | Used by FPPD at startup. Starts Dynamic_RDS_Engine.py')
  print('   --update                            | Used by Dynamic_RDS.php to apply dynamic settings to the transmitter')
  print('   --reset                             | Used by Dynamic_RDS.php to reset the GPIO pin')
  print('   --exit                              | Used by FPPD or manually to shutdown Dynamic_RDS_Engine.py')
  print('   --type media --data \'{..json..}\'    | Used by FPPD when a new items starts in a playlist')
  print('   --type playlist --data \'{..json..}\' | Used by FPPD when a playlist starts or stops')
  print('   --type lifecycle startup/shutdown   | Used by FPPD when it starts or stops')
  print('Note: Running with sudo might be needed for manual execution')
  sys.exit()

script_dir = os.path.dirname(os.path.abspath(argv[0]))

logging.basicConfig(filename=script_dir + '/Dynamic_RDS_callbacks.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')

read_config_from_file()

logging.getLogger().setLevel(config['DynRDSCallbackLogLevel'])

logging.debug('---')
logging.debug('Args %s', argv[1:])

# RPi.GPIO is used for software PWM on the RPi, fail if it is missing
# TODO: Look at switching to gpiozero
if os.getenv('FPPPLATFORM', '') == 'Raspberry Pi' and config['DynRDSTransmitter'] == "QN8066":
  try:
    import RPi.GPIO
  except ImportError as impErr:
    logging.error("Failed to import RPi.GPIO %s", impErr.args[0])
    sys.exit(1)

# Environ has a few useful items when FPPD runs callbacks.py, but logging it all the time, even at debug, is too much
#logging.debug('Environ %s', os.environ)

# Always try to start the Engine since it does the real work for all command
updater_path = script_dir + '/Dynamic_RDS_Engine.py'
engineStarted = False
proc = None
logging.debug('Checking for socket lock by %s', updater_path)
if check_engine_running():
  logging.debug('Lock found — %s is already running', updater_path)
else:
  logging.debug('Lock not found')
  # Short circuit if Engine isn't running and command is to shut it down
  if argv[1] == '--exit' or (argv[1] == '--type' and argv[2] == 'lifecycle' and argv[3] == 'shutdown'):
    logging.info('Exit, but not running')
    sys.exit()
  logging.info('Starting %s', updater_path)
  with open(os.devnull, 'w', encoding='UTF-8') as devnull:
    proc = subprocess.Popen(['python3', updater_path], stdin=devnull, stdout=devnull, stderr=subprocess.PIPE, text=True, close_fds=True)
  try:
    # Wait up to 1 second to see if the process exits
    proc.wait(timeout=1)
    logging.error('%s exited early - %s', updater_path, proc.returncode)
    engineStarted = False
  except subprocess.TimeoutExpired:
    # Timeout means process is STILL RUNNING / success
    engineStarted = True

# Always setup FIFO - Expects Engine to be running to open the read side of the FIFO
fifo_path = script_dir + '/Dynamic_RDS_FIFO'
try:
  logging.debug('Creating fifo %s', fifo_path)
  os.mkfifo(fifo_path)
except OSError as oe:
  if oe.errno != errno.EEXIST:
    raise
  logging.debug('Fifo already exists')

if proc is not None and proc.poll() is not None:
  logging.error('%s failed to stay running - %s', updater_path, proc.stderr.read())
  sys.exit(1)

with open(fifo_path, 'w', encoding='UTF-8') as fifo:
  if len(argv) >= 4:
    logging.info('Args %s %s %s', argv[1], argv[2], argv[3])
  else:
    logging.info('Args %s', argv[1])

  # If Engine was started AND the argument isn't --list, INIT must be sent to Engine before the requested argument
  if engineStarted and argv[1] != '--list':
    logging.info(' Engine restart detected, sending INIT')
    fifo.write('INIT\n')

  if argv[1] == '--list':
    # Typically called first by FPPD and will block if read side isn't open
    fifo.write('INIT\n')
    print('media,playlist,lifecycle')

  elif argv[1] == '--update':
    # Not used by FPPD, but used by Dynamic_RDS.php
    fifo.write('UPDATE\n')

  elif argv[1] == '--reset':
    # Not used by FPPD, but used by Dynamic_RDS.php
    fifo.write('RESET\n')

  elif argv[1] == '--exit' or (argv[1] == '--type' and argv[2] == 'lifecycle' and argv[3] == 'shutdown'):
    # Used by FPPD lifecycle shutdown. Also useful for testing or scripting
    fifo.write('EXIT\n')
    fifo.flush()

    timeout = 5
    startTime = time.monotonic()
    logging.info(' Waiting for Engine to shutdown (timeout: %ss)', timeout)

    # Poll the socket lock until it's released
    while time.monotonic() - startTime < timeout:
      if not check_engine_running():
        elapsed = time.monotonic() - startTime
        logging.info(' Engine shutdown after %.2fs', elapsed)
        sys.exit()
      time.sleep(0.05)  # Sleep 50ms between attempts
    logging.warning('Engine shutdown timeout after %ss', timeout)

  elif argv[1] == '--type' and argv[2] == 'media':
    try:
      j = json.loads(argv[4])
    except Exception:
      logging.exception('Media JSON')

    # When default values are sent over fifo, other side more or less ignores them
    media_type = j['type'] if 'type' in j else 'pause'
    media_title = j['title'] if 'title' in j else ''
    media_artist = j['artist'] if 'artist' in j else ''
    media_album = j['album'] if 'album' in j else ''
    media_genre = j['genre'] if 'genre' in j else ''
    media_tracknum = str(j['track']) if 'track' in j else '0'
    media_length = str(j['length']) if 'length' in j else '0'

    logging.debug('Type is %s', media_type)
    logging.debug('Title is %s', media_title)
    logging.debug('Artist is %s', media_artist)
    logging.debug('Album is %s', media_album)
    logging.debug('Genre is %s', media_genre)
    logging.debug('Tracknum is %s', media_tracknum)
    logging.debug('Length is %s', media_length)

    # TODO: Other than type missing defaulting to pause, can media type be either of these any more?
    if media_type in ('pause', 'event'):
      fifo.write('T\n') # Blank Title
      fifo.write('A\n') # Blank Artist
      fifo.write('B\n') # Blank Album
      fifo.write('G\n') # Blank Genre
    else:
      fifo.write('T' + media_title + '\n')
      fifo.write('A' + media_artist + '\n')
      fifo.write('B' + media_album + '\n')
      fifo.write('G' + media_genre + '\n')
    fifo.write('N' + media_tracknum + '\n')
    fifo.write('L' + media_length + '\n') # Length is always sent last for media-based updates to optimize when the Engine has to update the RDS Data

  elif argv[1] == '--type' and argv[2] == 'playlist':
    try:
      j = json.loads(argv[4])
    except ValueError:
      logging.exception('Playlist JSON')

    playlist_action = j['Action'] if 'Action' in j else 'stop'

    logging.info(' Action %s', j['Action'])

    if playlist_action == 'start': # or playlist_action == 'playing':
      fifo.write('START\n')
    elif playlist_action == 'stop':
      fifo.write('STOP\n')
      sys.exit()
    elif playlist_action == 'query_next': # Skip this
      sys.exit()

    if j['Section'] == 'MainPlaylist':
      logging.debug('Playlist name %s', j['name'])
      fifo.write(f"MAINLIST{j['name']}\n")
      logging.debug('Playlist position %s', j['Item']+1)
      fifo.write(f"P{j['Item']+1}\n") # Playlist position is always sent last for playlist-based updates to optimize when the Engine has to update the RDS Data
    else:
      logging.debug('Clearing playlist values')
      fifo.write('MAINLIST\n')
      fifo.write('P\n')

    if j['currentEntry'] is None or j['currentEntry']['type'] == 'pause':
      # TODO: Review this case - what to send to Engine for other playlist events
      # Looks like a 'note' field is on all of them that could go into title
      logging.debug('Clearing media values')
      fifo.write('T\n')
      fifo.write('A\n')
      fifo.write('B\n')
      fifo.write('G\n')
      fifo.write('N\n')
      if j['currentEntry'] is None:
        fifo.write('L0\n')
      elif j['currentEntry']['type'] == 'pause':
        fifo.write(f"L{int(j['currentEntry']['duration'])}\n")
  logging.debug('Processing done')
