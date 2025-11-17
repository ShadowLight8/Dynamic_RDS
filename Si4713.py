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
  PROP_TX_RDS_PS_MESSAGE_COUNT = 0x2C05
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
    #logging.info(f'Si4713 Part Number: 47{revData[1]:02d}, Firmware: {revData[2]}.{revData[3]}, '
    #             f'Patch ID: {revData[4]}.{revData[5]}, Component: {revData[6]}.{revData[7]}, '
    #             f'Chip Revision: {revData[8]}')
    logging.info('Si47%02d - FW %d.%d - Chip Rev %d',
                 revData[1], revData[2], revData[3], revData[8])
    if revData[1] != 13:
      logging.error('Part Number value is %02d instead of 13. Is this a Si4713 chip?', revData[1])
      sys.exit(-1)

    # TODO: Make a function to use in status?
    self._send_command(self.CMD_TX_RDS_BUFF, [0, 0, 0, 0, 0, 0, 0], True)
    rdsBuffData = self.I2C.read(0x00, 6, True)
    logging.debug('Circular Buffer: %d/%d, Fifo Buffer: %d/%d',
                  rdsBuffData[3], rdsBuffData[2] + rdsBuffData[3],
                  rdsBuffData[5], rdsBuffData[4] + rdsBuffData[5])
    self.totalCircularBuffers = rdsBuffData[2] + rdsBuffData[3]

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
    self._set_property(self.PROP_TX_RDS_PS_MIX, 0x05)  # Mix mode
    #self._set_property(self.PROP_TX_RDS_PS_MISC, 0x1808)  # Standard settings
    self._set_property(self.PROP_TX_RDS_PS_REPEAT_COUNT, 5)  # Repeat 3 times

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
    self.updateRDSData(self.PStext, self.RTtext)

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
    if self.active:
      logging.debug('Si4713 updateRDSData active')
      self._updatePS(PSdata)
      self._updateRT(RTdata)

  def _updatePS(self, psText):
    logging.info('Called _updatePS')
    if len(psText) > 96:
      logging.error('PS text too long: %d (max 96) - truncating', len(psText))
      psText = psText[:96]

    # Ensure psText is a multiple of 8 in length
    psText = psText.ljust((len(psText) + 7) // 8 * 8)
    logging.info('PS %s', psText)

    for block in range(len(psText) // 4):
      start = block * 4
      rdsBytes = [block]
      rdsBytes.append(ord(psText[start]))
      rdsBytes.append(ord(psText[start + 1]))
      rdsBytes.append(ord(psText[start + 2]))
      rdsBytes.append(ord(psText[start + 3]))
      self._send_command(self.CMD_TX_RDS_PS, rdsBytes)

    self._set_property(self.PROP_TX_RDS_PS_MESSAGE_COUNT, (len(psText) // 8))

  def _updateRT(self, rtText):
    logging.info('Called _updateRT')

    #rtText ='012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345'
    rtMaxLength = self.totalCircularBuffers // 3 * 4

    logging.error('Abs Max Length: %d', rtMaxLength)

    logging.error('RT length: %d', len(rtText))

    if len(rtText) > rtMaxLength:
      rtText = rtText[:rtMaxLength]
      logging.error('RT text too long: %d (max %d) - truncating', len(rtText), rtMaxLength)

    logging.error('RT length 2: %d', len(rtText))

    if len(rtText) % 32 != 0:
      if len(rtText) == rtMaxLength:
        rtText = rtText[:-1] + chr(0x0d)
      else:
        rtText = rtText + chr(0x0d) * (4 - len(rtText) % 4)

    logging.debug('Adj RT %d \'%s\'', len(rtText), rtText.replace('\r','<0d>'))

    # Empty circular buffer
    self._send_command(self.CMD_TX_RDS_BUFF, [0b00000010, 0, 0, 0, 0, 0, 0])

    segmentOffset = 0
    ab_flag = 1
    for i in range(0, len(rtText), 4):
      if i % 32 == 0:
        ab_flag = not ab_flag
        segmentOffset = 0

      rtBytes = [0b00000100, 0b00100000, ab_flag<<4 | segmentOffset]
      rtBytes.extend(list(rtText[i:i+4].encode('ascii')))
      logging.info(rtBytes)
      self._send_command(self.CMD_TX_RDS_BUFF, rtBytes)
      rdsBuffData = self.I2C.read(0x00, 6, True)
      logging.debug('Circular Buffer: %d/%d, Fifo Buffer: %d/%d',
                    rdsBuffData[3], rdsBuffData[2] + rdsBuffData[3],
                    rdsBuffData[5], rdsBuffData[4] + rdsBuffData[5])
      segmentOffset += 1

      # Will block for ~80-90ms for RDS Group to be sent
      # Check time, if it has been long enough AND a full RT fragment has been sent, move to next fragment
      # Flip A/B bit, send next group, if last group set full RT sent flag
      # Need to make sure full RT group has been sent at least once before moving on
      #if self.currentGroup == 0 and (datetime.now() - self.lastFragmentTime).total_seconds() >= self.delay:
      #  self.currentFragment = (self.currentFragment + 1) % len(self.fragments)
      #  self.lastFragmentTime = datetime.now()
      #  self.ab = not self.ab
        # Change \r (0x0d) to be [0d] for logging so it is visible in case of debugging


      #if len(self.fragments[-1]) < self.frag_size:
      #  self.fragments[-1] += chr(0x0d)


      # TODO: Seems like this could be improved
      #rdsBytes = [0b1000<<2 | self.pty>>3, (0b00111 & self.pty)<<5 | self.ab<<4 | self.currentGroup]
      #rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
      #rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 2 else 0x20)
      #rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 2]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 3 else 0x20)
      #rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 3]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 4 else 0x20)

      #self.outer.transmitRDS(rdsBytes)
      #self.currentGroup += 1
      #if self.currentGroup * self.group_size >= len(self.fragments[self.currentFragment]):
      #  self.currentGroup = 0









  def sendNextRDSGroup(self):
    # If more advanced mixing of RDS groups is needed, this is where it would occur
    logging.excessive('Si4713 sendNextRDSGroup')
    sleep(0.25)
    #self.PS.sendNextGroup()
    #self.RT.sendNextGroup()

  def transmitRDS(self, rdsBytes):
    """
    Transmit RDS group using Si4713's TX_RDS_BUFF command
    rdsBytes: 8-byte array containing the RDS group
    """
    logging.excessive("Transmit %s", ' '.join(f"0x{b:02X}" for b in rdsBytes))

    # Si4713 uses CMD_TX_RDS_BUFF to load RDS data
    # Command format: CMD, status, FIFO count, RDS data (8 bytes)
    args = [0b00000100]  # Clear interrupt
    args.extend(rdsBytes)

    success = self._send_command(self.CMD_TX_RDS_BUFF, args)
    self._send_command(self.CMD_TX_RDS_BUFF, [0, 0, 0, 0, 0, 0, 0], True)
    rdsBuffData = self.I2C.read(0x00, 6, True)
    logging.debug('Circular Buffer: %d/%d, Fifo Buffer: %d/%d',
                  rdsBuffData[3], rdsBuffData[2] + rdsBuffData[3],
                  rdsBuffData[5], rdsBuffData[4] + rdsBuffData[5])

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
      self.outer = outer
      super().__init__(data, 8, 4, delay)
      # Include outer for the common transmitRDS function that both PSBuffer and RTBuffer use

    def updateData(self, data):
      super().updateData(data)

      if len(self.fragments) > 12:
        logging.error('Too many PS fragments: %d (max 12)', len(self.fragments))
        return

      # Adjust last fragment to make all 8 characters long
      self.fragments[-1] = self.fragments[-1].ljust(self.frag_size)
      logging.info('PS %s', self.fragments)

      self.outer._set_property(self.outer.PROP_TX_RDS_PS_MESSAGE_COUNT, 3)

      group = 0
      for fragment in self.fragments:
        for chunk in range(self.frag_size // self.group_size):
          start = chunk * self.group_size
          rdsBytes = [group]
          rdsBytes.append(ord(fragment[start]))
          rdsBytes.append(ord(fragment[start + 1]))
          rdsBytes.append(ord(fragment[start + 2]))
          rdsBytes.append(ord(fragment[start + 3]))
          self.outer._send_command(self.outer.CMD_TX_RDS_PS, rdsBytes)
          group += 1

    def sendNextGroup(self):
      sleep(0.25)
      return
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

      self.outer.transmitRDS(rdsBytes)
      self.currentGroup += 1
      if self.currentGroup * self.group_size >= len(self.fragments[self.currentFragment]):
        self.currentGroup = 0
