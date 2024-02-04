import logging
from time import sleep
from datetime import datetime

from config import config

# ===================
# Transmitter Classes
# ===================
# Generic representation of a Transmitter with a common interface
# Includes a common RDSBuffer class
# Specific implementations of both are expected by child classes

# Transmitter
#   RDSBuffer
#
# QN8066 (Transmitter)
#   PSBuffer (RDSBuffer)
#   RTBuffer (RDSBuffer)

class Transmitter:
  def __init__(self):
    # Common class init
    self.active = False

  def startup(self):
    # Common elements for starting up the transmitter for broadcast
    self.active = True

  def update(self):
    # For settings that can be updated dynamically
    pass

  def shutdown(self):
    # Common elements for shutting down the transmitter from broadcast
    self.active = False

  def reset(self, resetdelay=1):
    # Used to restart the transmitter
    self.shutdown()
    sleep(resetdelay)
    self.startup()

  def status(self):
    # Expected to be defined by child class
    pass

  def updateRDSData(self, PSdata='', RTdata=''):
    # Expected to be defined by child class
    self.PStext = PSdata
    self.RTtext = RTdata

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
      self.fragments = []
      self.currentFragment = 0
      self.lastFragmentTime = 0
      self.currentGroup = 0

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
