#!/usr/bin/env python3

import sys

# Discovery must not wait for engine imports or FIFO readiness.
if sys.argv[1:] == ['--list']:
  print('media,playlist,lifecycle')
  sys.exit(0)

import logging
import json
import os
import errno
import subprocess
import socket
import fcntl
import time

from sys import argv
from config import config,read_config_from_file

def logUnhandledException(eType, eValue, eTraceback):
  logging.error('Unhandled exception', exc_info=(eType, eValue, eTraceback))
sys.excepthook = logUnhandledException

def engine_running():
  # Probe the engine's lock by connecting to it. Binding the name to test it would briefly hold the lock
  # ourselves, so an engine starting at that moment would fail to get it and exit.
  with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
    try:
      sock.connect('\0Dynamic_RDS_Engine')
      return True
    except ConnectionRefusedError:
      return False  # Nothing has bound the name
    except OSError as error:
      # Unexpected - assume it's running rather than risk launching a second engine
      logging.warning('Engine lock probe failed (%s) - assuming the engine is running', error)
      return True

if len(argv) <= 1:
  print('Usage:')
  print('   --list                              | Lists supported FPP callbacks without starting the engine')
  print('   --start                             | Manually enable FM transmission')
  print('   --stop                              | Disable FM transmission without exiting the engine')
  print('   --update                            | Used by Dynamic_RDS.php to apply dynamic settings to the transmitter')
  print('   --reset                             | Used by Dynamic_RDS.php to reset the GPIO pin')
  print('   --exit                              | Used by FPPD or manually to shutdown Dynamic_RDS_Engine.py')
  print('   --type media --data \'{..json..}\'    | Used by FPPD when a new items starts in a playlist')
  print('   --type playlist --data \'{..json..}\' | Used by FPPD when a playlist starts or stops')
  print('   --type lifecycle startup/shutdown   | Used by FPPD when it starts or stops')
  print('Note: Running with sudo might be needed for manual execution')
  sys.exit()

script_dir = os.path.dirname(os.path.abspath(argv[0]))

log_dir = os.environ.get('LOGDIR', '/home/fpp/media/logs')
logging.basicConfig(filename=os.path.join(log_dir, 'plugin-Dynamic_RDS.log'), level=logging.INFO, format='%(asctime)s C %(levelname)s %(message)s', datefmt='%H:%M:%S')

read_config_from_file()

logging.getLogger().setLevel(config['DynRDSCallbackLogLevel'])

logging.debug('---')
logging.debug('Args %s', argv[1:])

# Environ has a few useful items when FPPD runs callbacks.py, but logging it all the time, even at debug, is too much
#logging.debug('Environ %s', os.environ)


updater_path = script_dir + '/Dynamic_RDS_Engine.py'
fifo_path = script_dir + '/Dynamic_RDS_FIFO'
launch_lock_path = script_dir + '/Dynamic_RDS_Launch.lock'

isShutdown = argv[1] == '--exit' or argv[1:4] == ['--type', 'lifecycle', 'shutdown']

# Simple commands and the FIFO line each one sends
simpleCommands = {
  '--start': 'MANUALSTART',
  '--stop': 'MANUALSTOP',
  '--update': 'UPDATE', # Not used by FPPD, but used by Dynamic_RDS.php
  '--reset': 'RESET', # Not used by FPPD, but used by Dynamic_RDS.php
}

def build_lines():
  # Everything this callback sends, built before the FIFO is touched so it can go out in one write
  if argv[1] in simpleCommands:
    return [simpleCommands[argv[1]]]

  if isShutdown:
    # Used by FPPD lifecycle shutdown. Also useful for testing or scripting
    return ['EXIT']

  if argv[1] == '--type' and argv[2] == 'media':
    return build_media_lines()

  if argv[1] == '--type' and argv[2] == 'playlist':
    return build_playlist_lines()

  return []

def build_media_lines():
  try:
    j = json.loads(argv[4])
  except Exception:
    logging.exception('Media JSON')
    j = {}

  # When default values are sent over fifo, other side more or less ignores them
  media_type = j['type'] if 'type' in j else 'pause'
  # Extract title with fallback to Media or Sequence filename without extension
  if 'title' in j and j['title']:
    media_title = j['title']
  elif 'Media' in j and j['Media']:
    # Remove file extension from Media filename
    media_title = os.path.splitext(j['Media'])[0]
  elif 'Sequence' in j and j['Sequence']:
    # Remove file extension from Sequence filename
    media_title = os.path.splitext(j['Sequence'])[0]
  else:
    media_title = ''
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
    lines = ['T', 'A', 'B', 'G'] # Blank Title, Artist, Album, and Genre
  else:
    lines = ['T' + media_title, 'A' + media_artist, 'B' + media_album, 'G' + media_genre]
  lines.append('N' + media_tracknum)
  lines.append('L' + media_length) # Length is always sent last for media-based updates to optimize when the Engine has to update the RDS Data
  return lines

def build_playlist_lines():
  try:
    j = json.loads(argv[4])
  except ValueError:
    logging.exception('Playlist JSON')

  playlist_action = j['Action'] if 'Action' in j else 'stop'

  logging.info(' Action %s', j['Action'])

  # Remotes have no playlists, so FPPD fakes a single 'start' the first time it opens
  # media and never sends a matching 'stop' (see OpenMediaOutput in FPP's mediaoutput.cpp).
  # Treating it as a real START would mark a playlist active forever and block mpc polling.
  if playlist_action == 'start' and j.get('name') == 'FPP Remote' and j.get('desc') == 'FPP Remote Mode':
    return ['REMOTESTART']

  lines = []
  if playlist_action == 'start': # or playlist_action == 'playing':
    lines.append('START')
  elif playlist_action == 'stop':
    return ['STOP']
  elif playlist_action == 'query_next': # Skip this
    return []

  if j['Section'] == 'MainPlaylist':
    logging.debug('Playlist name %s', j['name'])
    lines.append(f"MAINLIST{j['name']}")
    logging.debug('Playlist position %s', j['Item']+1)
    lines.append(f"P{j['Item']+1}") # Playlist position is always sent last for playlist-based updates to optimize when the Engine has to update the RDS Data
  else:
    logging.debug('Clearing playlist values')
    lines.extend(['MAINLIST', 'P'])

  if j['currentEntry'] is None or j['currentEntry']['type'] == 'pause':
    # TODO: Review this case - what to send to Engine for other playlist events
    # Looks like a 'note' field is on all of them that could go into title
    logging.debug('Clearing media values')
    lines.extend(['T', 'A', 'B', 'G', 'N'])
    if j['currentEntry'] is None:
      lines.append('L0')
    elif j['currentEntry']['type'] == 'pause':
      lines.append(f"L{int(j['currentEntry']['duration'])}")
  return lines

def launch_engine():
  # Returns 'started' when this callback launched the engine (so it must send INIT), 'running' when an
  # engine already holds the lock, or 'launching' when another callback is launching one right now.
  # Launches are serialized with a lock file - without it, a second callback arriving between the first
  # one's Popen and the engine binding its lock would launch a second engine, which exits with
  # 'Unable to create lock'.
  try:
    lockFd = os.open(launch_lock_path, os.O_RDONLY | os.O_CREAT, 0o644)
  except OSError as error:
    logging.warning('Unable to open launch lock %s (%s) - launching without it', launch_lock_path, error)
    lockFd = None
  try:
    if lockFd is not None:
      try:
        fcntl.flock(lockFd, fcntl.LOCK_EX | fcntl.LOCK_NB)
      except BlockingIOError:
        # The holder sends INIT once its engine is up, so just queue our lines behind it
        logging.debug('Another callback is launching the engine')
        return 'launching'
      # The previous holder may have finished launching while we waited to check
      if engine_running():
        return 'running'
    return start_engine_process()
  finally:
    # Released before writing to the FIFO, so other callbacks are only held up by the launch itself.
    # os.open fds aren't inheritable and Popen closes fds anyway - the engine must never inherit this
    # one, or it would hold the launch lock for its whole life.
    if lockFd is not None:
      os.close(lockFd)

def start_engine_process():
  logging.info('Starting %s', updater_path)
  with open(os.devnull, 'w', encoding='UTF-8') as devnull:
    # Start Engine process in background - intentionally not using 'with'
    # statement as we need the process to continue running after this script exits
    proc = subprocess.Popen( # pylint: disable=consider-using-with
      ['python3', updater_path], stdin=devnull, stdout=devnull, stderr=subprocess.PIPE, text=True, close_fds=True)

  # The engine binds its lock before its slow imports, so this is normally well under a second. Waiting
  # for the lock (not for the FIFO) keeps the launch lock short - opening the FIFO can take several
  # seconds on a Pi Zero at boot, and that wait happens in the background below.
  deadline = time.monotonic() + 10
  while not engine_running():
    if proc.poll() is not None:
      errorText = proc.stderr.read()
      if 'Unable to create lock' in errorText:
        # Another engine won the lock (e.g. one started by hand) - its INIT is someone else's job
        logging.info('%s already running - another instance holds the lock', updater_path)
        return 'running'
      logging.error('%s exited early - %s %s', updater_path, proc.returncode, errorText)
      sys.exit(1)
    if time.monotonic() >= deadline:
      logging.warning('%s has not taken its lock after 10s - continuing', updater_path)
      break
    time.sleep(0.05)
  return 'started'

def ensure_fifo():
  # pylint: disable=duplicate-code
  try:
    logging.debug('Creating fifo %s', fifo_path)
    os.mkfifo(fifo_path)
  except OSError as oe:
    if oe.errno != errno.EEXIST:
      raise
    logging.debug('Fifo already exists')
  # pylint: enable=duplicate-code

def open_fifo_for_write(openTimeout):
  # A plain open() for write blocks until the engine opens the read side - forever if the engine is
  # hung or exiting. A non-blocking open fails with ENXIO while there is no reader, so retry until the
  # deadline. ENOENT is retried too: an exiting engine removes the FIFO and a new one recreates it.
  # Returns None when the deadline passes. openTimeout=0 makes a single attempt.
  deadline = time.monotonic() + openTimeout
  while True:
    try:
      return os.open(fifo_path, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as error:
      if error.errno not in (errno.ENXIO, errno.ENOENT):
        logging.error('Unable to open FIFO %s (%s) - dropping %s', fifo_path, error, argv[1:])
        sys.exit(1)
      if time.monotonic() >= deadline:
        return None
    time.sleep(0.05)

def write_fifo(fd, data):
  # Back to blocking writes once connected - only the open needed to be non-blocking. One write of up to
  # PIPE_BUF (4096) bytes is atomic, so the engine reads this callback's lines together.
  os.set_blocking(fd, True)
  try:
    view = memoryview(data)
    while view:
      view = view[os.write(fd, view):]
  except BrokenPipeError:
    logging.error('Engine closed the FIFO - dropping %s', argv[1:])
    sys.exit(1)
  finally:
    os.close(fd)

def write_in_background(data, openTimeout=30):
  # FPPD waits on playlist and media callbacks without a timeout, so a callback blocked here would stall
  # FPPD's playlist handling. Hand the wait to a child process and let FPPD carry on.
  if os.fork() > 0:
    sys.exit(0)
  # New session so the child isn't caught by signals sent to FPPD's process group. Stdio goes to
  # /dev/null because PHP's shell_exec (used for --update) reads stdout until every holder closes it.
  os.setsid()
  devnull = os.open(os.devnull, os.O_RDWR)
  for stdFd in (0, 1, 2):
    os.dup2(devnull, stdFd)
  os.close(devnull)
  fd = open_fifo_for_write(openTimeout)
  if fd is None:
    logging.error('Engine did not open the FIFO within %ss - dropping %s', openTimeout, argv[1:])
    sys.exit(1)
  write_fifo(fd, data)
  logging.debug('Background write done')
  sys.exit(0)

def shutdown_engine(data):
  # Shutdown stays synchronous - FPPD and the uninstaller expect the engine to be gone when this returns
  fd = open_fifo_for_write(10)
  if fd is None:
    logging.error('Engine did not open the FIFO within 10s - dropping %s', argv[1:])
    sys.exit(1)
  write_fifo(fd, data)

  timeout = 5
  startTime = time.monotonic()
  logging.info(' Waiting for Engine to shutdown (timeout: %ss)', timeout)

  # Poll the socket lock until it's released
  while time.monotonic() - startTime < timeout:
    if not engine_running():
      elapsed = time.monotonic() - startTime
      logging.info(' Engine shutdown after %.2fs', elapsed)
      return
    time.sleep(0.05)  # Sleep 50ms between attempts
  logging.warning('Engine shutdown timeout after %ss', timeout)

if len(argv) >= 4:
  logging.info('Args %s %s %s', argv[1], argv[2], argv[3])
else:
  logging.info('Args %s', argv[1])

fifoLines = build_lines()

# Always try to start the Engine since it does the real work for all commands
logging.debug('Checking for socket lock by %s', updater_path)
if engine_running():
  logging.debug('Lock found - %s is already running', updater_path)
  launchResult = 'running'
else:
  logging.debug('Lock not found')
  # Short circuit if Engine isn't running and command is to shut it down
  if isShutdown or argv[1] == '--stop':
    logging.info('Exit, but not running')
    sys.exit()
  launchResult = launch_engine()

# Always setup FIFO - the engine also creates it, but may not have got that far yet
ensure_fifo()

# Initialize a newly launched engine, or refresh it when FPPD starts.
if launchResult == 'started' or argv[1:] == ['--type', 'lifecycle', 'startup']:
  logging.info('Initializing engine')
  fifoLines.insert(0, 'INIT')

if not fifoLines:
  logging.debug('Nothing to send')
  sys.exit()

fifoData = ''.join(line + '\n' for line in fifoLines).encode('UTF-8')

if isShutdown:
  shutdown_engine(fifoData)
elif launchResult == 'launching':
  # The engine can't be reading yet - skip straight to waiting in the background
  write_in_background(fifoData)
else:
  # Normal case: the engine is reading, so write now and exit
  fifoFd = open_fifo_for_write(0)
  if fifoFd is None:
    write_in_background(fifoData)
  write_fifo(fifoFd, fifoData)
logging.debug('Processing done')
