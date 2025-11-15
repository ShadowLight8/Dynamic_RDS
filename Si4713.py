import logging
import sys
import os
from time import sleep
from datetime import datetime
from gpiozero import DigitalOutputDevice

from config import config
from basicI2C import basicI2C
from Transmitter import Transmitter

class Si4713(Transmitter):
  def __init__(self):
    logging.info('Initializing Si4713 transmitter')
    super().__init__()
    self.I2C = basicI2C(0x63)  # Si4713 default I2C address
    self.PS = self.PSBuffer(self, ' ', int(config['DynRDSPSUpdateRate']))
    self.RT = self.RTBuffer(self, ' ', int(config['DynRDSRTUpdateRate']))

  # Si4713 Commands
  CMD_POWER_UP = 0x01
  CMD_GET_REV = 0x10
  CMD_POWER_DOWN = 0x11
  CMD_SET_PROPERTY = 0x12
  CMD_GET_PROPERTY = 0x13
  CMD_TX_TUNE_FREQ = 0x30
  CMD_TX_TUNE_POWER = 0x31
  CMD_TX_TUNE_MEASURE = 0x32
  CMD_TX_TUNE_STATUS = 0x33
  CMD_TX_ASQ_STATUS = 0x34
  CMD_TX_RDS_BUFF = 0x35
  CMD_TX_RDS_PS = 0x36
  CMD_GET_INT_STATUS = 0x14

  # Si4713 Properties
  PROP_TX_COMPONENT_ENABLE = 0x2100
  PROP_TX_AUDIO_DEVIATION = 0x2101
  PROP_TX_PILOT_DEVIATION = 0x2102
  PROP_TX_RDS_DEVIATION = 0x2103
  PROP_TX_PREEMPHASIS = 0x2106
  PROP_TX_RDS_PI = 0x2C01
  PROP_TX_RDS_PS_MIX = 0x2C02
  PROP_TX_RDS_PS_MISC = 0x2C03
  PROP_TX_RDS_PS_REPEAT_COUNT = 0x2C04
  PROP_REFCLK_FREQ = 0x0201

  # Status bits
  STATUS_CTS = 0x80

  def _wait_for_cts(self, timeout=100):
    iterations = timeout  # Each iteration is ~1ms
    for _ in range(iterations):
      if self.I2C.read(0x00, 1)[0] & self.STATUS_CTS:
        return True
      sleep(0.001)
    return False

  def _send_command(self, cmd, args = None, isFatal = False):
    args = args or []
    self.I2C.write(cmd, args, isFatal)
    return self._wait_for_cts()

  def _set_property(self, prop, value):
    """Set a property on the Si4713"""
    args = [
      0x00,  # Reserved
      (prop >> 8) & 0xFF,  # Property high byte
      prop & 0xFF,  # Property low byte
      (value >> 8) & 0xFF,  # Value high byte
      value & 0xFF  # Value low byte
    ]
    return self._send_command(self.CMD_SET_PROPERTY, args)

  def startup(self):
    logging.info('Starting Si4713 transmitter')

    logging.debug('Executing Reset with Pin %s', config['DynRDSSi4713GPIOReset'])
    with DigitalOutputDevice(int(config['DynRDSSi4713GPIOReset'])) as resetPin:
      resetPin.on()
      sleep(0.01)
      resetPin.off()
      sleep(0.01)
      resetPin.on()
      sleep(0.11)

    # Power up in transmit mode (Crystal oscillator and Analog audio input)
    self.I2C.write(self.CMD_POWER_UP, [0b00010010, 0b01010000], True)
    sleep(0.11) # Wait for power up
    if not self._wait_for_cts():
      logging.error('Si4713 failed to be read after power up')
      sys.exit(-1)

    # Verify chip by getting revision
    self._send_command(self.CMD_GET_REV, [], True)
    revData = self.I2C.read(0x00, 9, True)
    logging.info(f'Si4713 Part Number: 47{revData[1]:02d}, Firmware: {revData[2]}.{revData[3]}, '
                 f'Patch ID: {revData[4]}.{revData[5]}, Component: {revData[6]}.{revData[7]}, '
                 f'Chip Revision: {revData[8]}')
    if revData[1] != 13:
      logging.error('Part Number value is %02d instead of 13. Is this a Si4713 chip?', revData[1])
      sys.exit(-1)

    # TODO: Make a function to use in status?
    self._send_command(self.CMD_TX_RDS_BUFF, [0, 0, 0, 0, 0, 0, 0], True)
    rdsBuffData = self.I2C.read(0x00, 6, True)
    logging.debug(f'Circular Buffer: {rdsBuffData[3]}/{rdsBuffData[2]}, Fifo Buffer: {rdsBuffData[5]}/{rdsBuffData[4]}')

    # Set reference clock (32.768 kHz crystal)
    #self._set_property(self.PROP_REFCLK_FREQ, 32768)

    # Enable stereo, pilot, and RDS
    self._set_property(self.PROP_TX_COMPONENT_ENABLE, 0x0007)

    # Set audio deviation (68.25 kHz)
    #self._set_property(self.PROP_TX_AUDIO_DEVIATION, 6825)

    # Set pilot deviation (6.75 kHz)
    #self._set_property(self.PROP_TX_PILOT_DEVIATION, 675)

    # Set RDS deviation (2 kHz)
    #self._set_property(self.PROP_TX_RDS_DEVIATION, 200)

    # Set pre-emphasis
    if config['DynRDSPreemphasis'] == "50us":
      self._set_property(self.PROP_TX_PREEMPHASIS, 1)  # 50 us
    else:
      self._set_property(self.PROP_TX_PREEMPHASIS, 0)  # 75 us

    # Configure RDS
    #self._set_property(self.PROP_TX_RDS_PS_MIX, 0x03)  # Mix mode
    #self._set_property(self.PROP_TX_RDS_PS_MISC, 0x1808)  # Standard settings
    #self._set_property(self.PROP_TX_RDS_PS_REPEAT_COUNT, 3)  # Repeat 3 times

    # Set frequency from config
    tempFreq = int(float(config['DynRDSFrequency']) * 100)  # Convert to 10 kHz units
    args = [
      0x00,  # Reserved
      (tempFreq >> 8) & 0xFF,  # Frequency high byte
      tempFreq & 0xFF  # Frequency low byte
    ]
    self._send_command(self.CMD_TX_TUNE_FREQ, args)
    sleep(0.1)  # Wait for tune

    # Set transmission power
    power = int(config['DynRDSSi4713ChipPower'])
    antcap = int(config['DynRDSSi4713TuningCap'])

    args = [
      0x00,  # Reserved
      0x00,  # Reserved
      power & 0xFF,
      antcap & 0xFF # Antenna cap (0 = auto)
    ]
    self._send_command(self.CMD_TX_TUNE_POWER, args)
    sleep(0.02)

    # Set TX_RDS_PS_MISC
    # TODO: Decide on bit 11 - 0=FIFO and BUFFER use PTY and TP as when written, 1=Force to be this setting
    self._set_property(self.PROP_TX_RDS_PS_MISC, 0b0001100000001000 | int(config['DynRDSPty'])<<5)

    # Set TX_RDS_PI
    self._set_property(self.PROP_TX_RDS_PI, int(config['DynRDSPICode'], 16))

    self.update()
    super().startup()

  def update(self):
    # Si4713 doesn't have AGC or soft clipping settings like QN8066
    # Most audio settings are configured via properties during startup
    pass

  def shutdown(self):
    logging.info('Stopping Si4713 transmitter')
    # Power down the transmitter
    self._send_command(self.CMD_POWER_DOWN, [])
    super().shutdown()

  def reset(self, resetdelay=1):
    # Used to restart the transmitter
    self.shutdown()
    del self.I2C
    self.I2C = basicI2C(0x63)
    sleep(resetdelay)
    self.startup()

  def status(self):
    # Get transmitter status
    self._send_command(self.CMD_TX_TUNE_STATUS, [0x01])  # Clear interrupt
    status_data = self.I2C.read(0x00, 8)

    if status_data[0] & self.STATUS_CTS:
      freq = (status_data[2] << 8) | status_data[3]
      power = status_data[5]
      antenna_cap = status_data[6]
      noise = status_data[7]

      logging.info('Status - Freq: %.1f MHz - Power: %d - Antenna Cap: %d - Noise: %d', 
                   freq / 100.0, power, antenna_cap, noise)

    super().status()

  def updateRDSData(self, PSdata='', RTdata=''):
    logging.debug('Si4713 updateRDSData')
    super().updateRDSData(PSdata, RTdata)
    self.PS.updateData(PSdata)
    self.RT.updateData(RTdata)

  def sendNextRDSGroup(self):
    # If more advanced mixing of RDS groups is needed, this is where it would occur
    logging.excessive('Si4713 sendNextRDSGroup')
    self.PS.sendNextGroup()
    self.RT.sendNextGroup()

  def transmitRDS(self, rdsBytes):
    """
    Transmit RDS group using Si4713's TX_RDS_BUFF command
    rdsBytes: 8-byte array containing the RDS group
    """
    logging.excessive('Transmit %s', ' '.join('0x{:02x}'.format(a) for a in rdsBytes))

    # Si4713 uses CMD_TX_RDS_BUFF to load RDS data
    # Command format: CMD, status, FIFO count, RDS data (8 bytes)
    args = [0x00]  # Clear interrupt
    args.extend(rdsBytes)

    success = self._send_command(self.CMD_TX_RDS_BUFF, args)

    if not success:
      logging.error('Failed to transmit RDS group')
      # RDS has failed to update, reset the Si4713
      self.reset()
      return

    # RDS specifications indicate 87.6ms to send a group
    sleep(0.087)

  class PSBuffer(Transmitter.RDSBuffer):
    # Sends RDS type 0B groups - Program Service
    # Fragment size of 8, Groups send 4 characters at a time
    def __init__(self, outer, data, delay=4):
      super().__init__(data, 8, 4, delay)
      # Include outer for the common transmitRDS function that both PSBuffer and RTBuffer use
      self.outer = outer

    def updateData(self, data):
      super().updateData(data)
      # Adjust last fragment to make all 8 characters long
      self.fragments[-1] = self.fragments[-1].ljust(self.frag_size)
      logging.info('PS %s', self.fragments)

    def sendNextGroup(self):
      if self.currentGroup == 0 and (datetime.now() - self.lastFragmentTime).total_seconds() >= self.delay:
        self.currentFragment = (self.currentFragment + 1) % len(self.fragments)
        self.lastFragmentTime = datetime.now()
        logging.debug('Send PS Fragment \'%s\'', self.fragments[self.currentFragment])

      rdsBytes = [self.currentGroup]
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]))
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 2]))
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 3]))

      self.outer._send_command(self.outer.CMD_TX_RDS_PS, rdsBytes)
      #self.outer.transmitRDS(rdsBytes)
      self.currentGroup = (self.currentGroup + 1) % (self.frag_size // self.group_size)
      #sleep(0.25)

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
      logging.info('RT %s', self.fragments)

    def sendNextGroup(self):
      # Will block for ~80-90ms for RDS Group to be sent
      # Check time, if it has been long enough AND a full RT fragment has been sent, move to next fragment
      # Flip A/B bit, send next group, if last group set full RT sent flag
      # Need to make sure full RT group has been sent at least once before moving on
      if self.currentGroup == 0 and (datetime.now() - self.lastFragmentTime).total_seconds() >= self.delay:
        self.currentFragment = (self.currentFragment + 1) % len(self.fragments)
        self.lastFragmentTime = datetime.now()
        self.ab = not self.ab
        # Change \r (0x0d) to be [0d] for logging so it is visible in case of debugging
        logging.debug('Send RT Fragment \'%s\'', self.fragments[self.currentFragment].replace('\r','<0d>'))

      # TODO: Seems like this could be improved
      rdsBytes = [0b1000<<2 | self.pty>>3, (0b00111 & self.pty)<<5 | self.ab<<4 | self.currentGroup]
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 2 else 0x20)
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 2]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 3 else 0x20)
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 3]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 4 else 0x20)

      #self.outer.transmitRDS(rdsBytes)
      self.currentGroup += 1
      if self.currentGroup * self.group_size >= len(self.fragments[self.currentFragment]):
        self.currentGroup = 0
