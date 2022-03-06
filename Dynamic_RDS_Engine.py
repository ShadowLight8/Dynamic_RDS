#!/usr/bin/python3

import logging
import json
import os
import errno
import atexit
import socket
import sys
import smbus
from time import sleep
from datetime import datetime

@atexit.register
def cleanup():
  try:
    logging.debug('Cleaning up fifo')
    os.unlink(fifo_path)
  except:
    pass

# ===============
# Basic I2C Class
# ===============
# Used by the Transmitter child classes (if they are i2c), but could also be used on its own if needed
# TODO: Assuming SMBus of 1 on most modern hardware - Test what happens if this fails to setup a fall back to SMBus(0), maybe a config option?
class basicI2C(object):
  def __init__(self, address, bus=1):
    self.address = address
    self.bus = smbus.SMBus(bus)

  def write(self, address, values):
    # Simple i2c write - Always takes an list, even for 1 byte
    logging.excessive('I2C write at 0x{0:02x} of {1}'.format(address, ' '.join('0x{:02x}'.format(a) for a in values)))
    for _ in range(3):
      try:
        self.bus.write_i2c_block_data(self.address, address, values)
      except Exception:
        logging.exception("write_i2c_block_data error")
        continue
      else:
        break
    else:
      logging.error("failed to write after 3 attempts")
      # TODO: What is we get here?
      #exit(-1)

  def read(self, address, num_bytes):
    # Simple i2c read - Always returns a list
    for _ in range(3):
      try:
        retVal = self.bus.read_i2c_block_data(self.address, address, num_bytes)
        logging.excessive('I2C read at 0x{0:02x} of {1} byte(s) returned {2}'.format(address, num_bytes, ' '.join('0x{:02x}'.format(a) for a in retVal)))
        return retVal
      except Exception:
        logging.exception("read_i2c_block_data error")
        continue
      else:
        break
    else:
      logging.error("failed to read after 3 attempts")
      #exit(-1)

# ===================
# Transmitter Classes
# ===================
# Generic representation of a Transmitter with a common interface
# Includes a common RDSBuffer class
# Specific implementations of both are expected by child classes

# Transmitter
#   RDSBuffer
#
# QN80xx (Transmitter)
#   PSBuffer (RDSBuffer)
#   RTBuffer (RDSBuffer)

class Transmitter:
  def __init__(self):
    # Common class init
    #logging.debug('Transmitter __init__')
    self.active = False

  def startup(self):
    # Common elements for starting up the transmitter for broadcast
    #logging.debug('Transmitter startup')
    self.active = True

  def shutdown(self):
    # Common elements for shutting down the transmitter from broadcast
    #logging.debug('Transmitter shutdown')
    self.active = False

  def reset(self, resetdelay=1):
    # Used to restart the transmitter
    #logging.debug('Transmitter reset')
    self.shutdown()
    sleep(resetdelay * 1000)
    self.startup()

  def status(self):
    # Used to log/print current transmitter status
    logging.debug('Transmitter status')
    #print('status')

  def updateRDSData(self, PSdata='', RTdata=''):
    # Must be defined by child class
    #logging.debug('Transmitter updateRDSData')
    pass

  def sendNextRDSGroup(self):
    # Must be defined by child class
    #logging.debug('Transmitter sendNextRDSGroup')
    pass

  # =============================================
  # RDS Buffer Class (Inner class of Transmitter)
  # =============================================
  # This holds a string of RDS data to send, how much can be displayed at a time, how many chars per RDS group, and how long between updates
  # Typically two are created by a specific transmitter, one for sending out the PS groups and one for the RT groups
  # Data - Entire string to show on RDS Screen over time - updateData called once per track, resets all counters
  # Fragment - What's on a single RDS Screen - Holds 8 for PS or 32/64 chars for RT - sendNextGroup tracks time to determine when to move to next fragment
  # Group - Single RDS Data Packet - Holds 2 or 4 chars - sendNextGroup called multiple times per second

  class RDSBuffer:
    def __init__(self, data='', frag_size=0, group_size=0, delay=4):
      #logging.debug('RDSBuffer __init__')
      self.frag_size = frag_size
      self.group_size = group_size
      self.delay = delay
      self.updateData(data)

    def updateData(self, data):
      #logging.debug('RDSBuffer updateData')
      self.fragments = []
      self.currentFragment = 0
      self.lastFragmentTime = datetime.now()
      self.currentGroup = 0
      for i in range(0, len(data), self.frag_size):
        self.fragments.append(data[i : i + self.frag_size])
      # TODO: Improve how we cut up the data (smart split) - Align with spaces, etc
      #       In context of an FPP Plugin, have main script function deal with this and keep transmitter impl simple - Main function already has to put together the data from FPP

    def sendNextGroup(self):
      # Must be defined by child class
      #logging.debug('RDSBuffer sendNextGroup')
      pass

class QN80xx(Transmitter):
  def __init__(self):
    super().__init__()
    self.I2C = basicI2C(0x21)
    self.PS = self.PSBuffer(self, ' ', 4)
    self.RT = self.RTBuffer(self, ' ', 7)

  def startup(self):
    tempReadValue = self.I2C.read(0x06, 1)[0]>>2
    if (tempReadValue != 0b1101): # TO TEST
      logging.error('Chip ID value is {} instead of 13. Is this a QN8066 chip?'.format(tempReadValue))
      exit(-1)
    #tempReadValue = self.I2C.read(0x0a, 1)[0]>>4
    #if (tempReadvalue != 0): # TO TEST
    #  logging.warning('Chip state is {} instead of 0 (Standby). Was startup already run?'.format(tempReadValue))

    # Reset everything
    self.I2C.write(0x00, [0b11100011])
    sleep(0.2)

    # Setup expected clock source and div
    self.I2C.write(0x02, [0b00010000])
    self.I2C.write(0x07, [0b11101000, 0b00001011])

    # Set frequency from config
    # (Frequency - 60) / 0.05
    tempFreq = int((float(config['Frequency'])-60)/0.05)
    self.I2C.write(0x19, [0b00100000 | tempFreq>>8])
    self.I2C.write(0x1b, [0b11111111 & tempFreq])

    # Enable RDS TX and set pre-emphasis
    if config['Preemphasis'] == "50us":
      self.I2C.write(0x01, [0b01000000])
    else:
      self.I2C.write(0x01, [0b01000001])

    # Exit standby, enter TX
    self.I2C.write(0x00, [0b00001011])
    sleep(0.2)

    # Try without 0x25 0b01111101 - TX Freq Dev of 86.25KHz
    # Try without 0x26 0b00111100 - RDS Freq Dev of 21KHz

    # Disable timer for PA off when no audio
    # TODO: Pull in soft clip from config
    self.I2C.write(0x27, [0b00111001])

    # Try without 0x28 0b01001011 - TX gain changes and input impedance
    self.I2C.write(0x6e, [0b10110111]) # Stops AGC, which introduces obvious audio changes
    self.I2C.write(0x28, [0b01011011])

    #try:
      #if not (self.I2C.read(0x01, 1)[0]>>6 & 1):
      #  self.I2C.write(0x01, [0x41])
      #  sleep(0.5)
    #except Exception:
      #logging.error('Failed to initialize transmitter')
      #exit(-1)
    super().startup()

  def shutdown(self):
    # Exit TX, Enter standby
    self.I2C.write(0x00, [0b00100011])
    super().startup()

  def status(self):
    self.aud_pk = self.I2C.read(0x1a, 1)[0]>>3 & 0b1111
    self.fsm = self.I2C.read(0x0a,1)[0]>>4
    # Check frequency? 0x19 1:0 + 0x1b

    logging.info('Status - State {} (expect 10) - Audio Peak {} (target <= 8)'.format(self.fsm, self.aud_pk))

    # Reset aud_pk
    self.I2C.write(0x24, [0b11111111]);
    self.I2C.write(0x24, [0b01111111]);
    super().status()

  def updateRDSData(self, PSdata, RTdata):
    #super().updateRDSData(data) - Not sure if this will be needed
    #logging.debug('QN80xx updateRDSData')
    self.PS.updateData(PSdata)
    self.RT.updateData(RTdata)

  def sendNextRDSGroup(self):
    #super().sendNextGroup() - Not sure if this will be needed
    # If more advanced mixing of RDS groups is needed, this is where it would occur
    #logging.debug('QN80xx sendNextRDSGroup')
    self.PS.sendNextGroup()
    self.RT.sendNextGroup()

  def MOCK_transmitRDS(self, rdsBytes):
    # Useful for testing
    logging.excessive('MOCK Transmit {0}'.format(' '.join('0x{:02x}'.format(a) for a in rdsBytes)))
    sleep(0.0876)

  def transmitRDS(self, rdsBytes):
    # Specific to QN 8036 and 8066 chips
    rdsStatusByte = self.I2C.read(0x01, 1)[0]
    rdsSendToggleBit = rdsStatusByte >> 1 & 0b1
    rdsSentStatusToggleBit = self.I2C.read(0x1a, 1)[0] >> 2 & 0b1
    logging.excessive('Transmit {0} - Send Bit {1} - Status Bit {2}'.format(' '.join('0x{:02x}'.format(a) for a in rdsBytes), rdsSendToggleBit, rdsSentStatusToggleBit))
    self.I2C.write(0x1c, rdsBytes)
    self.I2C.write(0x01, [rdsStatusByte ^ 0b10])
    # RDS specifications indicate 87.6ms to send a group
    # sleep is a bit less, plus time to read the status toggle bit
    # In testing, loop is only executed once about every 30 seconds
    sleep(0.0865)
    while (self.I2C.read(0x1a, 1)[0] >> 2 & 1) == rdsSentStatusToggleBit:
      logging.excessive('Waiting for rdsSentStatusToggleBit to flip')
      sleep(0.001)
      # TODO: If we hit this more than a few times, something is wrong....how to reset? Maybe a max number of tries, then move on?

  class PSBuffer(Transmitter.RDSBuffer):
    # Sends RDS type 0B groups - Program Service
    # Fragment size of 8, Groups send 2 characters at a time
    def __init__(self, outer, data, delay=4):
      super().__init__(data, 8, 2, delay)
      # Include outer for the common transmitRDS function that both PSBugger and RTBuffer use
      # TODO: Not sure if this is the best way yet
      self.outer = outer
      #logging.debug('PSBuffer __init__')

    def updateData(self, data):
      super().updateData(data)
      # Adjust last fragment to make all 8 characters long
      #logging.debug('PSBuffer updateData')
      self.fragments[-1] = self.fragments[-1].ljust(self.frag_size)
      logging.info('Updated PS Fragments {}'.format(self.fragments))
      #logging.info('Current PS Fragment \'{}\''.format(self.fragments[self.currentFragment]))

    def sendNextGroup(self):
      #logging.debug('PSBuffer sendNextGroup')
      if self.currentGroup == 0 and (datetime.now() - self.lastFragmentTime).total_seconds() >= self.delay:
        self.currentFragment = (self.currentFragment + 1) % len(self.fragments)
        self.lastFragmentTime = datetime.now()
        logging.info('Send PS Fragment \'{}\''.format(self.fragments[self.currentFragment]))

      # TODO: Seems like this could be improved
      rdsBytes = [pi_byte1, pi_byte2, 0b10<<2 | pty>>3, (0b00111 & pty)<<5 | self.currentGroup, pi_byte1, pi_byte2]
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]))

      # Will block for ~87.6ms for RDS Group to be sent
      #MOCK_transmitRDS([pi_byte1, pi_byte2, 0b10<<2 | pty>>3, (0b00111 & pty)<<5 | self.currentGroup, pi_byte1, pi_byte2, ord(char1), ord(char2)])
      self.outer.transmitRDS(rdsBytes)
      self.currentGroup = (self.currentGroup + 1) % (self.frag_size // self.group_size)

  class RTBuffer(Transmitter.RDSBuffer):
    # Sends RDS type 2A groups - RadioText
    # Max fragment size of 64, Groups send 4 characters at a time
    def __init__(self, outer, data, delay=7):
      self.ab = 0
      super().__init__(data, 32, 4, delay)
      self.outer = outer

    def updateData(self, data):
      super().updateData(data)
      # Add 0x0d to end of last fragment to indicate RT is done
      if len(self.fragments[-1]) < self.frag_size:
        self.fragments[-1] += chr(0x0d)
      self.ab = not self.ab
      logging.info('Updated RT Fragments {}'.format(self.fragments))
      #logging.info('RT Fragment \'{}\''.format(self.fragments[self.currentFragment].replace('\r','\\r')))

    def sendNextGroup(self):
      # Will block for ~80-90ms for RDS Group to be sent
      # Check time, if it has been long enough AND a full RT fragment has been sent, move to next fragment
      # Flip A/B bit, send next group, if last group set full RT sent flag
      # Need to make sure full RT group has been sent at least once before moving on
      if self.currentGroup == 0 and (datetime.now() - self.lastFragmentTime).total_seconds() >= self.delay:
        self.currentFragment = (self.currentFragment + 1) % len(self.fragments)
        self.lastFragmentTime = datetime.now()
        self.ab = not self.ab
        logging.info('Send RT Fragment \'{}\''.format(self.fragments[self.currentFragment].replace('\r','\\r')))

      # TODO: Seems like this could be improved
      #RDS_RT = [pi_byte1, pi_byte2, gtype<<4 | b0<<3 | tp<<2 | pty>>3, ((pty & 4) + (pty & 2) + (pty & 1))<<5 | ab<<4 | c<<3, ord('I'), ord(' '), ord('g'), ord('o')]
      rdsBytes = [pi_byte1, pi_byte2, 0b1000<<2 | pty>>3, (0b00111 & pty)<<5 | self.ab<<4 | self.currentGroup]
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 2 else 0x20)
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 2]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 3 else 0x20)
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 3]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 4 else 0x20)

      # Will block for ~87.6ms for RDS Group to be sent
      #MOCK_transmitRDS([pi_byte1, pi_byte2, 0b1000<<2 | pty>>3, (0b00111 & pty)<<5 | self.ab<<4 | self.currentGroup, ord(char1), ord(char2), ord(char3), ord(char4)])
      self.outer.transmitRDS(rdsBytes)

      self.currentGroup += 1
      if self.currentGroup * self.group_size >= len(self.fragments[self.currentFragment]):
        self.currentGroup = 0

# ==================================
# Configuration defaults and loading
# ==================================

# TODO for PLUGIN: Clean up default values
# TODO for PLUGIN: Make sure all defaults support working out of the box
def read_config():
	global config
	config = {
		'Start': 'FPPDStart',
		'Stop': 'Never',
		'GPIONumReset': '4',
		'Frequency': '100.10',
		'Power': '113',
		'Preemphasis': '75us',
		'AntCap': '32',
		'EnableRDS': 'True',
		'StationDelay': '4',
		'StationText': 'Happy   Hallo-     -ween',
		'StationTitle': 'True',
		'StationArtist': 'True',
		'StationTrackNumPre': '',
		'StationTrackNum': 'True',
		'StationTrackNumSuf': 'of 4',
		'RDSTextDelay': '7',
		'RDSTextText': 'Happy Halloween!!',
		'RDSTextTitle': 'True',
		'RDSTextArtist': 'True',
		'RDSTextTrackNumPre': 'Track ',
		'RDSTextTrackNum': 'True',
		'RDSTextTrackNumSuf': 'of 4',
		'Pty': '2',
		'LoggingLevel': 'DEBUG'
	}

	configfile = os.getenv('CFGDIR', '/home/fpp/media/config') + '/plugin.Dynamic_RDS'
	try:
		with open(configfile, 'r') as f:
        		for line in f:
                		(key, val) = line.split(' = ')
	                	config[key] = val.replace('"', '').strip()
	except IOError:
		logging.warning('No config file found, using defaults.')
	logging.getLogger().setLevel(config['LoggingLevel'])
	logging.info('Config %s', config)

# ===============================
# Processing FPP Data to RDS Data
# ===============================

def updateRDSData():
	# Take the data from FPP and the configuration to build the actual RDS string
	# TODO: Maybe provide an option between strict split and smart split
	logging.info('Updating RDS Data')
	logging.debug('Title %s', title)
	logging.debug('Artist %s', artist)
	logging.debug('Tracknum %s', tracknum)
	logging.debug('Length %s', tracklength)

	# TODO: Add ability for transmitting tracklength
	
	tmp_StationTitle = title if config['StationTitle'] == 'True' else ''
	tmp_StationArtist = artist if config['StationArtist'] == 'True' else ''
	tmp_StationTrackNum = ''
	if config['StationTrackNum'] == 'True' and tracknum != '0' and tracknum !='':
		tmp_StationTrackNum = '{} {} {}'.format(config['StationTrackNumPre'], tracknum, config['StationTrackNumSuf']).strip()

	tmp_RDSTextTitle = title if config['RDSTextTitle'] == 'True' else ''
	tmp_RDSTextArtist = artist if config['RDSTextArtist'] == 'True' else ''
	tmp_RDSTextTrackNum = ''
	if config['RDSTextTrackNum'] == 'True' and tracknum != '0' and tracknum !='':
		tmp_RDSTextTrackNum = '{} {} {}'.format(config['RDSTextTrackNumPre'], tracknum, config['RDSTextTrackNumSuf']).strip()

	PSstr = '{s: <{sw}}{t: <{tw}}{a: <{aw}}{n: <{nw}}'.format( \
		s=config['StationText'], sw=nearest(config['StationText'], 8), \
		t=tmp_StationTitle, tw=nearest(tmp_StationTitle, 8), \
		a=tmp_StationArtist, aw=nearest(tmp_StationArtist, 8), \
		n=tmp_StationTrackNum, nw=nearest(tmp_StationTrackNum, 8))

	RTstr = '{s: <{sw}}{t: <{tw}}{a: <{aw}}{n: <{nw}}'.format( \
		s=config['RDSTextText'], sw=nearest(config['RDSTextText'], 32), \
		t=tmp_RDSTextTitle, tw=nearest(tmp_RDSTextTitle,32), \
		a=tmp_RDSTextArtist, aw=nearest(tmp_RDSTextArtist,32), \
		n=tmp_RDSTextTrackNum, nw=nearest(tmp_RDSTextTrackNum, 32))

	logging.info('Updated PS Data [%s]', PSstr)
	logging.info('Updated RT Data [%s]', RTstr)

	transmitter.updateRDSData(PSstr, RTstr)

def nearest(str, size):
	# -(-X // Y) functions as ceiling division
	return -(-len(str) // size) * size

# ===============
# Main code start
# ===============

# Setup logging
script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
#logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format='%(asctime)s:%(name)s:%(levelname)s:%(message)s')
logging.basicConfig(filename=script_dir + '/Dynamic_RDS_Engine.log', level=logging.DEBUG, format='%(asctime)s:%(name)s:%(levelname)s:%(message)s')

# Adding in excessive log level below debug for very noisy items
# Allow for debug to be reasonable
# Debug is as deep as most people would want
EXCESSIVE = 5

def excessive(msg, *args, **kwargs):
  if logging.getLogger().isEnabledFor(EXCESSIVE):
    logging.log(EXCESSIVE, msg, *args, **kwargs)

logging.addLevelName(15, 'EXCESSIVE')
logging.EXCESSIVE = EXCESSIVE
logging.excessive = excessive
logging.Logger.excessive = excessive

logging.info('--------');

# Establish lock via socket or exit if failed
try:
	lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
	lock_socket.bind('\0Dynamic_RDS_Engine')
	logging.debug('Lock created')
except:
	logging.error('Unable to create lock. Another instance of Dynamic_RDS_Engine.py running?')
	exit(1)

# Setup fifo
fifo_path = script_dir + "/Dynamic_RDS_FIFO"
try:
	logging.debug('Setting up read side of fifo %s', fifo_path)
	os.mkfifo(fifo_path)
except OSError as oe:
	if oe.errno != errno.EEXIST:
		raise
	else:
		logging.debug('Fifo already exists')

# Global RDS Values
title = ''
artist = ''
tracknum = ''
tracklength = 0

# Get config populated and/or loaded
config = {}
read_config()

# RDS Global Values
# TODO: These need to come from config
pi_byte1 = 0x81
pi_byte2 = 0x9b
pty = 0b00010

# TODO: Based on config init the correct transmitter
transmitter = QN80xx()
updateRDSData()

# =========
# Main Loop
# =========

# Check if new information is in the FIFO and process accordingly
# ?(Always or when no new info)? send the next RDS groups each loop
with open(fifo_path, 'r') as fifo:
	while True:
		line = fifo.readline().rstrip()
		if len(line) > 0:
			logging.debug('line %s', line)
			if line == 'EXIT':
				logging.info('Processing exit')
				transmitter.shutdown()
				exit()

			elif line == 'RESET':
				logging.info('Processing reset')
				read_config()
				transmitter.reset()
				if config['Start'] == "FPPDStart":
					#print('start after reset')
					transmitter.startup()

			elif line == 'INIT':
				logging.info('Processing init')
				# TODO: Setup non-transmitter items, assuming this isn't defaultly done - Don't think this will be anything yet
				if config['Start'] == "FPPDStart":
					#print('start transmitter after init')
					transmitter.startup()

			elif line == 'START':
				logging.info('Processing start')
				if config['Start'] == "PlaylistStart":
					#print('start transmitter with playlist start')
					transmitter.startup()

			elif line == 'STOP':
				logging.info('Processing stop')
				# Reset RDS data to the default
				title = ''
				artist = ''
				tracknum = ''
				tracklength = '0'
				updateRDSData()

				if config['Stop'] == "PlaylistStop":
					transmitter.shutdown()
					logging.info('Radio stopped')

			elif line[0] == 'T':
				logging.debug('Processing title')
				title = line[1:]

			elif line[0] == 'A':
				logging.debug('Processing artist')
				artist = line[1:]

			elif line[0] == 'N':
				logging.debug('Processing track number')
				tracknum = line[1:]

			elif line[0] == 'L':
				logging.debug('Processing length')
				tracklength = max(int(line[1:10]) - max(int(config['StationDelay']), int(config['RDSTextDelay'])), 1)
				logging.debug('Length %s', int(tracklength))

				# TANL is always sent together with L being last item, so we only need to update the RDS Data once with the new values
				updateRDSData()
				# TODO: Maybe updateRDSData should be part of the transmitter class? Not sure yet
				transmitter.status()

			else:
				logging.error('Unknown fifo input %s', line)

		else:
			transmitter.sendNextRDSGroup()
			# TODO: Determine when track length is done to reset RDS
			# TODO: Could add 1 sec to length, so normally track change will update data rather than time expiring. Reset should only happen when playlist is stopped?
