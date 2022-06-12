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
  try:
    # TODO: Do we need to set both to fully turn off?
    # TODO: Handle case where PWM isn't being used cleanly
    logging.debug('Stopping PWM')
    with open("/sys/class/pwm/pwmchip0/pwm0/duty_cycle", 'w') as p:
      p.write("0\n")
    logging.info('Disabling PWM')
    with open("/sys/class/pwm/pwmchip0/pwm0/enable", 'w') as p:
      p.write("0\n")
  except:
    pass
  logging.info('Exiting')

# ===============
# Basic I2C Class
# ===============
# Used by the Transmitter child classes (if they are i2c), but could also be used on its own if needed
# Assuming SMBus of 1 on most modern hardware - Can check /dev/i2c-* for available buses
class basicI2C(object):
  def __init__(self, address, bus=1):
    self.address = address
    # TODO: Need to test this
    if os.path.isfile('/dev/ic2-0'):
      bus = 0
    self.bus = smbus.SMBus(bus)
    sleep(1)

  def write(self, address, values, isFatal = False):
    # Simple i2c write - Always takes an list, even for 1 byte
    logging.excessive('I2C write at 0x{0:02x} of {1}'.format(address, ' '.join('0x{:02x}'.format(a) for a in values)))
    for i in range(8):
      try:
        self.bus.write_i2c_block_data(self.address, address, values)
      except Exception:
        logging.exception("write_i2c_block_data error")
        if i >= 1:
          sleep(i * .25)
        continue
      else:
        break
    else:
      logging.error("failed to write after multiple attempts")
      if isFatal:
        exit(-1)

  def read(self, address, num_bytes, isFatal = False):
    # Simple i2c read - Always returns a list
    for i in range(8):
      try:
        retVal = self.bus.read_i2c_block_data(self.address, address, num_bytes)
        logging.excessive('I2C read at 0x{0:02x} of {1} byte(s) returned {2}'.format(address, num_bytes, ' '.join('0x{:02x}'.format(a) for a in retVal)))
        return retVal
      except Exception:
        logging.exception("read_i2c_block_data error")
        if i >= 1:
          sleep(i * .25)
        continue
      else:
        break
    else:
      logging.error("failed to read after multiple attempts")
      if isFatal:
        exit(-1)

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
    self.active = False

  def startup(self):
    # Common elements for starting up the transmitter for broadcast
    self.active = True

  def shutdown(self):
    # Common elements for shutting down the transmitter from broadcast
    self.active = False

  def reset(self, resetdelay=1):
    # Used to restart the transmitter
    self.shutdown()
    sleep(resetdelay * 1000)
    self.startup()

  def status(self):
    # Expected to be defined by child class
    pass

  def updateRDSData(self, PSdata, RTdata):
    # Expected to be defined by child class
    pass

  def sendNextRDSGroup(self):
    # Expected to be defined by child class
    pass

  # =============================================
  # RDS Buffer Class (Inner class of Transmitter)
  # =============================================
  # This holds a string of RDS data to send, how much can be displayed at a time, how many chars per RDS group, and how long between updates
  # Typically, two instances are created by a transmitter, one for the PS groups and one for the RT groups
  # Data - Entire string to show on RDS Screen over time - updateData called once per track, resets all counters
  # Fragment - What's on a single RDS Screen - Holds 8 for PS or 32/64 chars for RT - sendNextGroup tracks time to determine when to move to next fragment
  # Group - Single RDS Data Packet - Holds 2 or 4 chars - sendNextGroup called multiple times per second

  class RDSBuffer:
    def __init__(self, data='', frag_size=0, group_size=0, delay=4):
      logging.debug('RDSBuffer init')
      self.frag_size = frag_size
      self.group_size = group_size
      self.delay = delay
      self.pi_byte1 = int('0x' + config['DynRDSPICode'][0:2], 16)
      self.pi_byte2 = int('0x' + config['DynRDSPICode'][2:4], 16)
      self.pty = int(config['DynRDSPty'])
      self.updateData(data)

    def updateData(self, data):
      logging.debug('RDSBuffer updateData')
      self.fragments = []
      self.currentFragment = 0
      self.lastFragmentTime = datetime.now()
      self.currentGroup = 0
      for i in range(0, len(data), self.frag_size):
        self.fragments.append(data[i : i + self.frag_size])

    def sendNextGroup(self):
      # Expected to be defined by child class
      pass

class QN80xx(Transmitter):
  def __init__(self):
    super().__init__()
    self.I2C = basicI2C(0x21)
    self.PS = self.PSBuffer(self, ' ', int(config['DynRDSPSUpdateRate']))
    self.RT = self.RTBuffer(self, ' ', int(config['DynRDSRTUpdateRate']))

  def startup(self):
    logging.info('Starting QN80xx transmitter')

    tempReadValue = self.I2C.read(0x06, 1)[0]>>2
    if (tempReadValue != 0b1101): # TODO: Test this condition
      logging.error('Chip ID value is {} instead of 13. Is this a QN8066 chip?'.format(tempReadValue))
      exit(-1)

    #tempReadValue = self.I2C.read(0x0a, 1)[0]>>4
    #if (tempReadvalue != 0): # TO TEST
    #  logging.warning('Chip state is {} instead of 0 (Standby). Was startup already run?'.format(tempReadValue))

    # Reset everything
    self.I2C.write(0x00, [0b11100011], True)
    sleep(0.2)

    # Setup expected clock source and div
    self.I2C.write(0x02, [0b00010000], True)
    self.I2C.write(0x07, [0b11101000, 0b00001011], True)

    # Set frequency from config
    # (Frequency - 60) / 0.05
    tempFreq = int((float(config['DynRDSFrequency'])-60)/0.05)
    self.I2C.write(0x19, [0b00100000 | tempFreq>>8], True)
    self.I2C.write(0x1b, [0b11111111 & tempFreq], True)

    # Enable RDS TX and set pre-emphasis
    if config['DynRDSPreemphasis'] == "50us":
      self.I2C.write(0x01, [0b00000000 | int(config['DynRDSEnableRDS'])<<6])
    else:
      self.I2C.write(0x01, [0b00000001 | int(config['DynRDSEnableRDS'])<<6])

    # Exit standby, enter TX
    self.I2C.write(0x00, [0b00001011], True)
    sleep(0.2)

    # Try without 0x25 0b01111101 - TX Freq Dev of 86.25KHz
    # Try without 0x26 0b00111100 - RDS Freq Dev of 21KHz

    # TODO: Try disable timer for PA off when no audio to see if this is useful - Does it auto power back up? RDS stalled?
    # TODO: Pull in soft clip from config
    self.I2C.write(0x27, [0b00111010], True)

    # Stop Auto Gain Correction (AGC), which introduces obvious poor sounding audio changes
    if config['DynRDSQN8066AGC'] == '0':
      self.I2C.write(0x6e, [0b10110111], True)

    # TX gain changes and input impedance
    self.I2C.write(0x28, [int(config['DynRDSQN8066SoftClipping'])<<7 | int(config['DynRDSQN8066BufferGain'])<<4 | int(config['DynRDSQN8066DigitalGain'])<<2 | int(config['DynRDSQN8066InputImpedance'])], True)
    #self.I2C.write(0x28, [0b01011011])

    # Reset aud_pk
    # TODO: Add support for DynRDSQN8066ChipPower
    self.I2C.write(0x24, [0b11111111])
    self.I2C.write(0x24, [0b01111111])

    super().startup()

    # With everything started up, enable PWM

    # Check that PWM configured in /boot/config.txt and can be written to
    if os.path.isdir('/sys/class/pwm/pwmchip0') and os.access('/sys/class/pwm/pwmchip0/export', os.W_OK):
      logging.debug('Setting up PWM')
      # Export PWM commands if needed
      if not os.path.isdir('/sys/class/pwm/pwmchip0/pwm0'):
        logging.debug('Exporting PWM')
        with open('/sys/class/pwm/pwmchip0/export', 'w') as p:
          p.write('0\n')

      logging.debug('Setting PWM period')
      with open('/sys/class/pwm/pwmchip0/pwm0/period', 'w') as p:
        p.write('18300\n')

      logging.debug('Setting PWM duty cycle')
      with open('/sys/class/pwm/pwmchip0/pwm0/duty_cycle', 'w') as p:
        p.write('{0}\n'.format(int(config['DynRDSQN8066AmpPower']) * 61))

      logging.info('Enabling PWM')
      with open('/sys/class/pwm/pwmchip0/pwm0/enable', 'w') as p:
        p.write('1\n')

  def shutdown(self):
    logging.info('Stopping QN80xx transmitter')
    # Exit TX, Enter standby
    self.I2C.write(0x00, [0b00100011])
    super().shutdown()

    # With everything stopped, disable PWM
    logging.debug('Stopping PWM')
    with open("/sys/class/pwm/pwmchip0/pwm0/duty_cycle", 'w') as p:
      p.write("0\n")

    logging.info('Disabling PWM')
    with open("/sys/class/pwm/pwmchip0/pwm0/enable", 'w') as p:
      p.write("0\n")

  def status(self):
    self.aud_pk = self.I2C.read(0x1a, 1)[0]>>3 & 0b1111
    self.fsm = self.I2C.read(0x0a,1)[0]>>4
    # Check frequency? 0x19 1:0 + 0x1b
    # TODO: Add PWM status if active

    logging.info('Status - State {} (expect 10) - Audio Peak {} (target <= 14)'.format(self.fsm, self.aud_pk))

    # Reset aud_pk
    self.I2C.write(0x24, [0b11111111]);
    self.I2C.write(0x24, [0b01111111]);
    super().status()

  def updateRDSData(self, PSdata, RTdata):
    logging.debug('QN80xx updateRDSData')
    self.PS.updateData(PSdata)
    self.RT.updateData(RTdata)

  def sendNextRDSGroup(self):
    # If more advanced mixing of RDS groups is needed, this is where it would occur
    logging.excessive('QN80xx sendNextRDSGroup')
    self.PS.sendNextGroup()
    self.RT.sendNextGroup()

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
      # Include outer for the common transmitRDS function that both PSBuffer and RTBuffer use
      # TODO: Not sure if this is the best way yet
      self.outer = outer

    def updateData(self, data):
      super().updateData(data)
      # Adjust last fragment to make all 8 characters long
      self.fragments[-1] = self.fragments[-1].ljust(self.frag_size)
      logging.info('Updated PS Fragments {}'.format(self.fragments))

    def sendNextGroup(self):
      #logging.debug('PSBuffer sendNextGroup')
      if self.currentGroup == 0 and (datetime.now() - self.lastFragmentTime).total_seconds() >= self.delay:
        self.currentFragment = (self.currentFragment + 1) % len(self.fragments)
        self.lastFragmentTime = datetime.now()
        logging.debug('Send PS Fragment \'{}\''.format(self.fragments[self.currentFragment]))

      # TODO: Seems like this could be improved
      rdsBytes = [self.pi_byte1, self.pi_byte2, 0b10<<2 | self.pty>>3, (0b00111 & self.pty)<<5 | self.currentGroup, self.pi_byte1, self.pi_byte2]
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]))

      self.outer.transmitRDS(rdsBytes)
      self.currentGroup = (self.currentGroup + 1) % (self.frag_size // self.group_size)

  class RTBuffer(Transmitter.RDSBuffer):
    # Sends RDS type 2A groups - RadioText
    # Max fragment size of 64, Groups send 4 characters at a time
    def __init__(self, outer, data, delay=7):
      self.ab = 0
      super().__init__(data, int(config['DynRDSRTSize']), 4, delay)
      self.outer = outer

    def updateData(self, data):
      super().updateData(data)
      # Add 0x0d to end of last fragment to indicate RT is done
      # TODO: This isn't quite correct - Should put 0x0d where a break is indicated in the rdsStyleText
      if len(self.fragments[-1]) < self.frag_size:
        self.fragments[-1] += chr(0x0d)
      self.ab = not self.ab
      logging.info('Updated RT Fragments {}'.format(self.fragments))

    def sendNextGroup(self):
      # Will block for ~80-90ms for RDS Group to be sent
      # Check time, if it has been long enough AND a full RT fragment has been sent, move to next fragment
      # Flip A/B bit, send next group, if last group set full RT sent flag
      # Need to make sure full RT group has been sent at least once before moving on
      if self.currentGroup == 0 and (datetime.now() - self.lastFragmentTime).total_seconds() >= self.delay:
        self.currentFragment = (self.currentFragment + 1) % len(self.fragments)
        self.lastFragmentTime = datetime.now()
        self.ab = not self.ab
        logging.debug('Send RT Fragment \'{}\''.format(self.fragments[self.currentFragment].replace('\r','\\r')))

      # TODO: Seems like this could be improved
      rdsBytes = [self.pi_byte1, self.pi_byte2, 0b1000<<2 | self.pty>>3, (0b00111 & self.pty)<<5 | self.ab<<4 | self.currentGroup]
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 2 else 0x20)
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 2]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 3 else 0x20)
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 3]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 4 else 0x20)

      self.outer.transmitRDS(rdsBytes)
      self.currentGroup += 1
      if self.currentGroup * self.group_size >= len(self.fragments[self.currentFragment]):
        self.currentGroup = 0

# ==================================
# Configuration defaults and loading
# ==================================

def read_config():
  global config
  config = {
    'DynRDSEnableRDS': 'True',
    'DynRDSPSUpdateRate': '4',
    'DynRDSPSStyle': 'Merry|Christ-|  -mas!|{T}|{A}|[{N} of 8]',
    'DynRDSRTUpdateRate': '8',
    'DynRDSRTSize': '32',
    'DynRDSRTStyle': 'Merry Christmas!|{T}[ by {A}]|[Track {N} of 8]',
    'DynRDSPty': '2',
    'DynRDSPICode': '819b',
    'DynRDSTransmitter': 'None',
    'DynRDSFrequency': '100.1',
    'DynRDSPreemphasis': '75us',
    'DynRDSQN8066ChipPower': '113',
    'DynRDSQN8066AmpPower': '0',
    'DynRDSQN8066InputImpedance': '0',
    'DynRDSQN8066DigitalGain': '0',
    'DynRDSQN8066BufferGain': '0',
    'DynRDSQN8066SoftClipping': '0',
    'DynRDSQN8066AGC': '0',
    'DynRDSStart': 'FPPDStart',
    'DynRDSStop': 'Never',
    'DynRDSCallbackLogLevel': 'INFO',
    'DynRDSEngineLogLevel': 'INFO'

    #'DynRDSGPIONumReset': '4',
    #'DynRDSAntCap': '32',
  }

  configfile = os.getenv('CFGDIR', '/home/fpp/media/config') + '/plugin.Dynamic_RDS'
  try:
    with open(configfile, 'r') as f:
      for line in f:
        (key, val) = line.split(' = ')
        config[key] = val.replace('"', '').strip()
  except IOError:
    logging.warning('No config file found, using defaults.')
 
  logging.getLogger().setLevel(config['DynRDSEngineLogLevel'])
  logging.info('Config %s', config)

# ===============================
# Processing FPP Data to RDS Data
# ===============================

def updateRDSData():
  # Take the data from FPP and the configuration to build the actual RDS string
  logging.info('Updating RDS Data')
  logging.debug('RDS Values %s', rdsValues)

  # TODO: DynRDSRTSize functionally works, but I think this should source from the RTBuffer class post initialization
  transmitter.updateRDSData(rdsStyleToString(config['DynRDSPSStyle'], 8), rdsStyleToString(config['DynRDSRTStyle'], int(config['DynRDSRTSize'])))

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
          outputRDS.append(rdsValues.get(rdsStyle[i:i+3], ''))
      else:
        outputRDS.append(v)
  except ValueError:
    pass # Expected when index doesn't find a ]

  outputRDS = ''.join(outputRDS)
  logging.debug('RDS Data [%s]', outputRDS)
  return outputRDS

# ===============
# Main code start
# ===============

# Setup logging
script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
#logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format='%(asctime)s:%(name)s:%(levelname)s:%(message)s')
logging.basicConfig(filename=script_dir + '/Dynamic_RDS_Engine.log', level=logging.DEBUG, format='%(asctime)s:%(name)s:%(levelname)s:%(message)s')

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
rdsValues = {'{T}': '', '{A}': '', '{N}': '', '{L}': ''}

# =========
# Main Loop
# =========
transmitter = None

# Check if new information is in the FIFO and process accordingly
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
        if config['DynRDSStart'] == "FPPDStart":
          transmitter.startup()

      elif line == 'INIT': # From --list with callback.py
        logging.info('Processing init')
        read_config()

        transmitter = None
        if config['DynRDSTransmitter'] == "QN8066":
          transmitter = QN80xx()
        elif config['DynRDSTransmitter'] == "Si4713":
          transmitter = None; # To be implemented later

        if transmitter == None:
          logger.error('Transmitter not set. Check Transmitter Type.')
          continue;

        updateRDSData()

        if config['DynRDSStart'] == "FPPDStart":
          transmitter.startup()

      elif line == 'START':
        logging.info('Processing start')
        if config['DynRDSStart'] == "PlaylistStart" or not transmitter.active:
          transmitter.startup()

      elif line == 'STOP':
        logging.info('Processing stop')
        for key in rdsValues:
          rdsValues[key] = ''
        updateRDSData()

        if config['DynRDSStop'] == "PlaylistStop":
          transmitter.shutdown()
          logging.info('Transmitter stopped')

      # rdsValues that need additional parsing
      elif line[0] == 'L':
        logging.debug('Processing length')
        rdsValues['{'+line[0]+'}'] = '{}:{:02d}'.format(int(line[1:])//60, int(line[1:])%60)
        #tracklength = max(int(line[1:10]) - max(int(config['DynRDSPSUpdateRate']), int(config['DynRDSRTUpdateRate'])), 1)
        #logging.debug('Length %s', int(tracklength))

        # TANL is always sent together with L being last item, so we only need to update the RDS Data once with the new values
        # TODO: This will likely change as more data is added, so a new way will have to be determined
        updateRDSData()
        transmitter.status()

      # All of the rdsValues that are stored as is
      else:
        rdsValues['{'+line[0]+'}'] = line[1:]

    elif transmitter != None and transmitter.active and config['DynRDSEnableRDS'] == "1":
      transmitter.sendNextRDSGroup()
      # TODO: Determine when track length is done to reset RDS
      # TODO: Could add 1 sec to length, so normally track change will update data rather than time expiring. Reset should only happen when playlist is stopped?

    else:
      logging.debug('Sleeping...')
      sleep(3)
