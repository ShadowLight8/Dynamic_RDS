#!/usr/bin/python3

import logging
import json
import os
import errno
import atexit
import socket
import sys
import subprocess
import unicodedata
from time import sleep
from datetime import date, datetime, timedelta
from urllib.request import urlopen
from urllib.parse import quote

from config import config, read_config_from_file
from QN8066 import QN8066
from basicMQTT import basicMQTT, pahoMQTT

def logUnhandledException(eType, eValue, eTraceback):
  logging.error("Unhandled exception", exc_info=(eType, eValue, eTraceback))
sys.excepthook = logUnhandledException

@atexit.register
def cleanup():
  try:
    logging.debug('Cleaning up fifo')
    os.unlink(fifo_path)
  except:
    pass
  try:
    transmitter.basicPWM.shutdown()
    if mqtt.connected:
      mqtt.disconnect()
  except:
    pass
  logging.info('Exiting')

# ==================================
# Configuration defaults and loading
# ==================================

def read_config():
  read_config_from_file()

  # TODO: Move this QN8066 specific code to that class? Like a config tweak in QN8066?
  # Convert DynRDSQN8066Gain into DynRDSQN8066InputImpedance, DynRDSQN8066DigitalGain, and DynRDSQN8066BufferGain
  totalGain = int(config['DynRDSQN8066Gain']) + 15
  config['DynRDSQN8066DigitalGain'] = totalGain % 3

  if totalGain < 24:
    config['DynRDSQN8066InputImpedance'] = 3 - totalGain // 6
    config['DynRDSQN8066BufferGain'] = totalGain % 6 // 3
  else:
    config['DynRDSQN8066InputImpedance'] = 0
    config['DynRDSQN8066BufferGain'] = totalGain % 18 // 3

  if not (os.path.exists('/bin/mpc') or os.path.exists('/usr/bin/mpc')):
    config['DynRDSmpcEnable'] = 0

  logging.getLogger().setLevel(config['DynRDSEngineLogLevel'])
  logging.info('Config %s', config)

# ===============================
# Processing FPP Data to RDS Data
# ===============================

def updateRDSData():
  # Take the data from FPP and the configuration to build the actual RDS string
  logging.info('New RDS Data')
  logging.debug('RDS Values %s', rdsValues)

  # TODO: DynRDSRTSize functionally works, but I think this should source from the RTBuffer class post initialization
  transmitter.updateRDSData(rdsStyleToString(config['DynRDSPSStyle'], 8), rdsStyleToString(config['DynRDSRTStyle'], int(config['DynRDSRTSize'])))

  if config['DynRDSmqttEnable'] == '1':
    mqttStatus = {}
    mqttStatus['PStext'] = transmitter.PStext
    mqttStatus['RTtext'] = transmitter.RTtext
    mqttStatus['PSfragments'] = transmitter.PS.fragments
    mqttStatus['RTfragments'] = transmitter.RT.fragments
    mqttStatus['RDSValues'] = rdsValues
    mqtt.publish('status', json.dumps(mqttStatus, indent=8))

def rdsStyleToString(rdsStyle, groupSize):
  outputRDS = []
  squStart = -1
  skip = 0

  try:
    for i, v in enumerate(rdsStyle):
      #print("i {} - v {} - squStart {} - skip {} - outputRDS {}".format(i,v,squStart,skip,outputRDS))
      if skip:
        skip -= 1
      elif v == '\\' and i < len(rdsStyle) - 1:
        skip += 1
        outputRDS.append(rdsStyle[i+1])
      elif v == '[':
        squStart = len(outputRDS) # Track on the outputRDS where the square bracket started in case we have to clean up
      elif v == ']' and squStart != -1: # End of square bracket mode, append to output and reset
        squStart = -1
      elif v == '|':
        chunkLength = groupSize - sum(len(s) for s in outputRDS) % groupSize
        if chunkLength != groupSize:
          outputRDS.append(' ' * chunkLength)
      elif v == '{' and i < len(rdsStyle) - 2 and rdsStyle[i+2] == '}':
        if squStart != -1 and not rdsValues.get(rdsStyle[i:i+3],''): # In square brackets and value is empty?
          del outputRDS[squStart:] # Remove output back to start of square bracket group
          skip += rdsStyle.index(']', i + 3) - i - 1 # Using index to throw if no ] by the end of rdsStyle - Done building in this case
        else:
          skip += 2
          # Normalize Unicode characters to their nearest ascii characters
          # Other character substitutions could be done here
          outputRDS.append(unicodedata.normalize('NFKD', rdsValues.get(rdsStyle[i:i+3], '')).encode('ascii', 'ignore').decode())
      else:
        outputRDS.append(v)
  except ValueError:
    pass # Expected when index doesn't find a ]
  except Exception:
    logging.exception('rdsStyleToString')

  outputRDS = ''.join(outputRDS)
  logging.debug('RDS Data [%s]', outputRDS)
  return outputRDS

# ===============
# Main code start
# ===============

# Setup logging
script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format='%(asctime)s:%(name)s:%(levelname)s:%(message)s')
logging.basicConfig(filename=script_dir + '/Dynamic_RDS_Engine.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')

# Adding in excessive log level below debug for very noisy items
# Allow for debug to be reasonable
# Debug is as deep as most people would want
EXCESSIVE = 5

def excessive(msg, *args, **kwargs):
  if logging.getLogger().isEnabledFor(EXCESSIVE):
    logging.log(EXCESSIVE, msg, *args, **kwargs)

logging.addLevelName(5, 'EXCESSIVE')
logging.EXCESSIVE = EXCESSIVE
logging.excessive = excessive
logging.Logger.excessive = excessive

logging.info('--- %s', date.today())

# Establish lock via socket or exit if failed
try:
  lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
  lock_socket.bind('\0Dynamic_RDS_Engine')
  logging.debug('Lock created')
except:
  logging.error('Unable to create lock. Another instance of Dynamic_RDS_Engine.py running?')
  sys.exit(1)

# Setup fifo
fifo_path = script_dir + "/Dynamic_RDS_FIFO"
try:
  logging.debug('Setting up read side of fifo %s', fifo_path)
  os.mkfifo(fifo_path)
except OSError as oe:
  if oe.errno != errno.EEXIST:
    raise
  logging.debug('Fifo already exists')

# Global RDS Values
rdsValues = {'{T}': '', '{A}': '', '{B}': '', '{G}': '', '{N}': '','{L}': '', '{C}': '', '{P}': ''}

# TODO: Check for existance of After Hours plugin by dir
# TODO: Check for existance of mpc program to get status

# =========
# Main Loop
# =========
transmitter = None
mqtt = None
activePlaylist = False
nextMPCUpdate = datetime.now()

# Check if new information is in the FIFO and process accordingly
with open(fifo_path, 'r', encoding='UTF-8') as fifo:
  while True:
    line = fifo.readline().rstrip()
    if len(line) > 0:
      logging.debug('line %s', line)
      if line == 'EXIT':
        logging.info('Processing exit')
        transmitter.shutdown() # TODO: Can fail if transmitter wasn't set - Can fix with an if statement or look into using Transmitter base class initially
        mqtt.disconnect()
        sys.exit()

      elif line == 'RESET':
        logging.info('Processing reset')
        read_config()
        mqtt.publish('config', json.dumps(config, indent=8))
        transmitter.reset()
        if config['DynRDSStart'] == "FPPDStart":
          transmitter.startup()

      elif line == 'INIT': # From --list with callback.py
        logging.info('Processing init')
        read_config()

        transmitter = None
        if config['DynRDSTransmitter'] == "QN8066":
          transmitter = QN8066()
        elif config['DynRDSTransmitter'] == "Si4713":
          transmitter = None # To be implemented later

        if transmitter is None:
          logging.error('Transmitter not set. Check Transmitter Type.')
          continue

        if config['DynRDSmqttEnable'] == "1":
          mqtt = pahoMQTT()
        else:
          mqtt = basicMQTT()
        mqtt.connect()
        mqtt.publish('ready', '1')
        mqtt.publish('config', json.dumps(config, indent=8))

        updateRDSData()

        if config['DynRDSStart'] == "FPPDStart":
          transmitter.startup()

      elif line == 'UPDATE':
        read_config()
        mqtt.publish('config', json.dumps(config, indent=8))
        if (transmitter is not None and transmitter.active):
          for key in rdsValues:
            rdsValues[key] = ''
          updateRDSData()
          transmitter.update()

      elif line == 'START':
        logging.info('Processing start')
        if config['DynRDSStart'] == "PlaylistStart" or not transmitter.active:
          transmitter.startup()
        activePlaylist = True

      elif line == 'STOP':
        logging.info('Processing stop')
        for key in rdsValues:
          rdsValues[key] = ''
        updateRDSData()
        activePlaylist = False

        if config['DynRDSStop'] == "PlaylistStop":
          transmitter.shutdown()
          logging.info('Transmitter stopped')

      elif line.startswith('MAINLIST'):
        logging.info('Processing MainPlaylist')
        playlist_name = line[8:] # TODO: Need to keep track of last playlist name to reduce overhead?
        if playlist_name != '':
          logging.debug('Playlist Name: %s', playlist_name)
          playlist_length = 1
          if '.' not in playlist_name: # Case where a sequence is directly run from the scheduler or status page, it ends in .fseq and . is not allowed in regular playlist names
            try:
              with urlopen(f'http://localhost/api/playlist/{quote(playlist_name)}') as response:
                data = response.read()
                playlist_length = len(json.loads(data)['mainPlaylist'])
            except Exception:
              logging.exception("Playlist Length")
          logging.debug('Playlist Length: %s', playlist_length)
          rdsValues['{C}'] = str(playlist_length)
        else:
          rdsValues['{C}'] = ''

      elif line[0] == 'P':
        logging.debug('Processing playlist position')
        rdsValues['{P}'] = line[1:]
        updateRDSData() # Always follows MAINLIST, so only a single update is needed

      # rdsValues that need additional parsing
      elif line[0] == 'L':
        logging.debug('Processing length')
        if line[1:] != '0':
          rdsValues['{L}'] = f'{int(line[1:])//60}:{int(line[1:])%60:02d}'
        else:
          rdsValues['{L}'] = ''
        #tracklength = max(int(line[1:10]) - max(int(config['DynRDSPSUpdateRate']), int(config['DynRDSRTUpdateRate'])), 1)
        #logging.debug('Length %s', int(tracklength))

        # TANL is always sent together with L being last item, so we only need to update the RDS Data once with the new values
        # TODO: This will likely change as more data is added, so a new way will have to be determined
        updateRDSData()
        #activePlaylist = True # TODO: Is this needed still?
        transmitter.status()

      # All of the rdsValues that are stored as is
      else:
        rdsValues['{'+line[0]+'}'] = line[1:]

    elif transmitter is not None and transmitter.active and config['DynRDSEnableRDS'] == "1":
      transmitter.sendNextRDSGroup()
      # TODO: Determine when track length is done to reset RDS
      # TODO: Could add 1 sec to length, so normally track change will update data rather than time expiring. Reset should only happen when playlist is stopped?

    if not activePlaylist and transmitter is not None and transmitter.active and config['DynRDSmpcEnable'] == "1" and datetime.now() > nextMPCUpdate:
      logging.debug('Processing mpc')
      nextMPCUpdate = datetime.now() + timedelta(seconds=12)
      # TODO: Error handling might be needed here if the mpc execution has an issue
      # TODO: Future idea to handle multiple fields from mpc, but I've not seen them used yet. [{A}%artist%][{T}%title%][{N}%track%]
      mpcLatest = subprocess.run(['mpc', 'current', '-f', '%title%'], stdout=subprocess.PIPE, check=False).stdout.decode('utf-8').strip()
      if rdsValues['{T}'] != mpcLatest:
        rdsValues['{T}'] = mpcLatest
        updateRDSData()

    if transmitter is None or not transmitter.active:
      logging.debug('Sleeping...')
      sleep(3)
