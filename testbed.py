#!/usr/bin/python3

import logging
import sys
import smbus
import re
from time import sleep
from datetime import datetime

class basicI2C(object):

# ===========================================================================
# Next 3 functions from Adafruit_I2C Class
# ===========================================================================

  def getPiRevision(self):
    "Gets the version number of the Raspberry Pi board"
    # Revision list available at: http://elinux.org/RPi_HardwareHistory#Board_Revision_History
    try:
      with open('/proc/cpuinfo', 'r') as infile:
        for line in infile:
          # Match a line of the form "Revision : 0002" while ignoring extra
          # info in front of the revsion (like 1000 when the Pi was over-volted).
          match = re.match('Revision\s+:\s+.*(\w{4})$', line)
          if match and match.group(1) in ['0000', '0002', '0003']:
            # Return revision 1 if revision ends with 0000, 0002 or 0003.
            return 1
          elif match:
            # Assume revision 2 if revision ends with any other 4 chars.
            return 2
        # Couldn't find the revision, assume revision 0 like older code for compatibility.
        return 0
    except:
      return 0

  def getPiI2CBusNumber(self):
    # Gets the I2C bus number /dev/i2c#
    return 1 if self.getPiRevision() > 1 else 0

  def __init__(self, address, busnum=-1, debug=False):
    self.address = address
    # By default, the correct I2C bus is auto-detected using /proc/cpuinfo
    # Alternatively, you can hard-code the bus version below:
    # self.bus = smbus.SMBus(0); # Force I2C0 (early 256MB Pi's)
    # self.bus = smbus.SMBus(1); # Force I2C1 (512MB Pi's)
    self.bus = smbus.SMBus(busnum if busnum >= 0 else self.getPiI2CBusNumber())
    self.debug = debug

  def write(self, address, values):
    # Simple i2c write - Always takes an array, even for 1 byte
    logging.debug('I2C write at 0x{0:02x} of {1}'.format(address, ' '.join('0x{:02x}'.format(a) for a in values)))
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
      exit(-1)

  def read(self, address, num_bytes):
    # Simple i2c read
    for _ in range(3):
      try:
        retVal = self.bus.read_i2c_block_data(self.address, address, num_bytes)
        logging.debug('I2C read at 0x{0:02x} of {1} byte(s) returned {2}'.format(address, num_bytes, ' '.join('0x{:02x}'.format(a) for a in retVal)))
        return retVal
      except Exception:
        logging.exception("read_i2c_block_data error")
        continue
      else:
        break
    else:
      logging.error("failed to read after 3 attempts")
      exit(-1)

# ======================
# RDS Transmit Functions
# ======================

def MOCK_transmitRDS(rdsBytes):
  logging.verbose('MOCK Transmit {0}'.format(' '.join('0x{:02x}'.format(a) for a in rdsBytes)))
  sleep(0.0876)

def transmitRDS(rdsBytes):
  rdsStatusByte = transmitter.read(0x01, 1)[0]
  rdsSendToggleBit = rdsStatusByte >> 1 & 0b1
  rdsSentStatusToggleBit = transmitter.read(0x1a, 1)[0] >> 2 & 0b1
  logging.verbose('Transmit {0} - Send Bit {1} - Status Bit {2}'.format(' '.join('0x{:02x}'.format(a) for a in rdsBytes), rdsSendToggleBit, rdsSentStatusToggleBit))
  transmitter.write(0x1c, rdsBytes)
  transmitter.write(0x01, [rdsStatusByte ^ 0b10])
  # RDS specification indicates 87.6ms to send a group
  # sleep is a bit less, plus time to read the status toggle bit
  # In testing, loop is only executed once about every 30 seconds
  sleep(0.0865)
  while (transmitter.read(0x1a, 1)[0] >> 2 & 1) == rdsSentStatusToggleBit:
    logging.verbose('Waiting for rdsSentStatusToggleBit to flip')
    sleep(0.001)
    # TODO: If we hit this more than a few times, something is wrong....how to reset? Maybe a max number of tries, then move on?

# ================
# RDS Buffer Class
# ================
# This holds the current entire RDS data to send, how much can be displayed at a time, how many chars per RDS group, and how long between updates
# Data - Entire string to show on RDS Screen over time - updateData called once per track, resets all counters
# Fragment - What's on a single RDS Screen - Hold 8 for PS or 32/64 chars for RT - sendNextGroup tracks time to determine when to move to next fragment
# Group - Single RDS Data Packet - Holds 2 or 4 chars - sendNextGroup called multiple times per second

class RDSBuffer(object):
  def __init__(self, data='', frag_size=0, group_size=0, delay=4):
    self.frag_size = frag_size
    self.group_size = group_size
    self.delay = delay
    self.updateData(data)

  def updateData(self, data):
    self.fragments = []
    self.currentFragment = 0
    self.lastFragmentTime = datetime.now()
    self.currentGroup = 0
    for i in range(0, len(data), self.frag_size):
      self.fragments.append(data[i : i + self.frag_size]) 
    # TODO: Improve how we cut up the data (smart split) - Align with spaces, etc
    # TODO: Maybe provide an option between strict split and smart split

class PSBuffer(RDSBuffer):
  # Sends RDS type 0B groups - Program Service
  # Fragment size of 8, Groups send 2 characters at a time
  def __init__(self, data, delay=4):
    super(PSBuffer, self).__init__(data, 8, 2, delay)

  def updateData(self, data):
    super(PSBuffer, self).updateData(data)
    # Adjust last fragment to make all 8 characters long
    self.fragments[-1] = self.fragments[-1].ljust(self.frag_size)
    logging.info('Updated PS Data {}'.format(self.fragments))
    logging.info('PS Fragment \'{}\''.format(self.fragments[self.currentFragment]))

  def sendNextGroup(self):
    if self.currentGroup == 0 and (datetime.now() - self.lastFragmentTime).total_seconds() >= self.delay:
      self.currentFragment = (self.currentFragment + 1) % len(self.fragments)
      self.lastFragmentTime = datetime.now()
      logging.info('PS Fragment \'{}\''.format(self.fragments[self.currentFragment]))

    # TODO: Seems like this could be improved
    rdsBytes = [pi_byte1, pi_byte2, 0b10<<2 | pty>>3, (0b00111 & pty)<<5 | self.currentGroup, pi_byte1, pi_byte2]
    rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
    rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]))

    # Will block for ~87.6ms for RDS Group to be sent
    #MOCK_transmitRDS([pi_byte1, pi_byte2, 0b10<<2 | pty>>3, (0b00111 & pty)<<5 | self.currentGroup, pi_byte1, pi_byte2, ord(char1), ord(char2)])
    transmitRDS(rdsBytes)
    self.currentGroup = (self.currentGroup + 1) % (self.frag_size // self.group_size)
    print (self.currentGroup)

class RTBuffer(RDSBuffer):
  # Sends RDS type 2A groups - RadioText
  # Max fragment size of 64, Groups send 4 characters at a time
  def __init__(self, data, delay=7):
    self.ab = 0
    super(RTBuffer, self).__init__(data, 32, 4, delay)

  def updateData(self, data):
    super(RTBuffer, self).updateData(data)
    # Add 0x0d to end of last fragment to indicate RT is done
    if len(self.fragments[-1]) < self.frag_size:
      self.fragments[-1] += chr(0x0d)
    self.ab = not self.ab
    logging.info('Updated RT Data {}'.format(self.fragments))
    logging.info('RT Fragment \'{}\''.format(self.fragments[self.currentFragment].replace('\r','\\r')))

  def sendNextGroup(self):
    # Will block for ~80-90ms for RDS Group to be sent
    # Check time, if it has been long enough AND a full RT fragment has been sent, move to next fragment
    # Flip A/B bit, send next group, if last group set full RT sent flag
    # Need to make sure full RT group has been sent at least once before moving on
    if self.currentGroup == 0 and (datetime.now() - self.lastFragmentTime).total_seconds() >= self.delay:
      self.currentFragment = (self.currentFragment + 1) % len(self.fragments)
      self.lastFragmentTime = datetime.now()
      self.ab = not self.ab
      logging.info('RT Fragment \'{}\''.format(self.fragments[self.currentFragment].replace('\r','\\r')))

    # TODO: Seems like this could be improved
    #RDS_RT = [pi_byte1, pi_byte2, gtype<<4 | b0<<3 | tp<<2 | pty>>3, ((pty & 4) + (pty & 2) + (pty & 1))<<5 | ab<<4 | c<<3, ord('I'), ord(' '), ord('g'), ord('o')]
    rdsBytes = [pi_byte1, pi_byte2, 0b1000<<2 | pty>>3, (0b00111 & pty)<<5 | self.ab<<4 | self.currentGroup]
    rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
    rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 2 else 0x20)
    rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 2]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 3 else 0x20)
    rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 3]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 4 else 0x20)

    # Will block for ~87.6ms for RDS Group to be sent
    #MOCK_transmitRDS([pi_byte1, pi_byte2, 0b1000<<2 | pty>>3, (0b00111 & pty)<<5 | self.ab<<4 | self.currentGroup, ord(char1), ord(char2), ord(char3), ord(char4)])
    transmitRDS(rdsBytes)

    self.currentGroup += 1
    if self.currentGroup * self.group_size >= len(self.fragments[self.currentFragment]):
      self.currentGroup = 0

# ====================
# Main line code start
# ====================

# Swap which line is commented for a ton of logging
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s:%(name)s:%(levelname)s:%(message)s')

# Adding in verbose log level between debug and info
# Allow for debug to be really detailed
# Verbose is as deep as most people would want
VERBOSE = 15

def verbose(msg, *args, **kwargs):
  if logging.getLogger().isEnabledFor(VERBOSE):
    logging.log(VERBOSE, msg, *args, **kwargs)

logging.addLevelName(15, 'VERBOSE')
logging.VERBOSE = VERBOSE
logging.verbose = verbose
logging.Logger.verbose = verbose

logging.getLogger().setLevel(logging.VERBOSE);

logging.info('--------');

transmitter = basicI2C(0x21)

# Start RDS
try:
  if not (transmitter.read(0x01, 1)[0]>>6 & 1):
    transmitter.write(0x01, [0x41])
    sleep(0.5)
except Exception:
  logging.error('Failed to initialize transmitter')
  exit(-1)

# RDS Global Values
pi_byte1 = 0x81
pi_byte2 = 0x9b
pty = 0b00010

startTime = datetime.now()
startRTTime = datetime.now()

testGroups = ['1234567890123456', 'Happy   Hallo-     -ween']
curTestGroup = 0
testRTGroups = ['ABCD', 'BCDEFGHIJKLMNOPQRSTUVWXYZABCDEFG', 'CDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJ']
curTestRTGroup = 0

PS = PSBuffer('12345678', 4) # Change every 4 seconds
RT = RTBuffer('ABCDEFGHIJKLMNOP', 7) # Change every 7 seconds

while 1:
  PS.sendNextGroup()
  if (datetime.now() - startTime).total_seconds() >= 12: # PS Data being sent change every 12 seconds
    curTestGroup = (curTestGroup + 1) % len(testGroups)
    PS.updateData(testGroups[curTestGroup])
    startTime = datetime.now()
  RT.sendNextGroup()
  if (datetime.now() - startRTTime).total_seconds() >= 21: # RT Data being sent change every 21 seconds
    curTestRTGroup = (curTestRTGroup + 1) % len(testRTGroups)
    RT.updateData(testRTGroups[curTestRTGroup])
    startRTTime = datetime.now()

# Next steps
# Get Init process down
#   Set Frequency
#   Set RDS TX
#   Set Volume
#   Anything else?
# Figure out PWM pin
#   Determine duty cycle at various levels
#   How to do on Pi?

# Notes from testing
# Single RT group send not working on WioTerminal_Radio - Could be a bug on radio side
