import logging
import sys
from threading import Timer
from time import sleep
from gpiozero import DigitalOutputDevice

from config import config
from basicI2C import basicI2C
from Transmitter import Transmitter

class Si4713(Transmitter):
  def __init__(self):
    logging.info('Initializing Si4713 transmitter')
    super().__init__()
    self.I2C = basicI2C(0x63)  # Si4713 default I2C address
    self.totalCircularBuffers = 0

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

    logging.info('Executing Reset with Pin %s', config['DynRDSSi4713GPIOReset'])
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
    logging.info('Si47%02d - FW %d.%d - Chip Rev %d',
                 revData[1], revData[2], revData[3], revData[8])
    if revData[1] != 13:
      logging.error('Part Number value is %02d instead of 13. Is this a Si4713 chip?', revData[1])
      sys.exit(-1)

    # TODO: Make a function to use in status?
    self._send_command(self.CMD_TX_RDS_BUFF, [0, 0, 0, 0, 0, 0, 0], True)
    rdsBuffData = self.I2C.read(0x00, 6, True)
    logging.info('Circular Buffer: %d/%d, Fifo Buffer: %d/%d',
                  rdsBuffData[3], rdsBuffData[2] + rdsBuffData[3],
                  rdsBuffData[5], rdsBuffData[4] + rdsBuffData[5])
    self.totalCircularBuffers = rdsBuffData[2] + rdsBuffData[3]

    # Enable stereo, pilot, and RDS
    self._set_property(self.PROP_TX_COMPONENT_ENABLE, 0x0007)

    # Set pre-emphasis
    if config['DynRDSPreemphasis'] == "50us":
      self._set_property(self.PROP_TX_PREEMPHASIS, 1)  # 50 us
    else:
      self._set_property(self.PROP_TX_PREEMPHASIS, 0)  # 75 us

    # Configure RDS
    self._set_property(self.PROP_TX_RDS_PS_MIX, 0x05)  # Mix mode
    self._set_property(self.PROP_TX_RDS_PS_REPEAT_COUNT, 9)  # Repeat 3 times
    # TODO: Timing guidance is needed
    # MIX @ 5 and REPEAT @ 9 - PS ~4 sec, RT ~5.5 sec
    # Lowering MIX still speed up RT refresh
    # Lowering REP will speed up PS, Raising REP will slow down PS
    # TODO: Decide on bit 11 - 0=FIFO and BUFFER use PTY and TP as when written, 1=Force to be this setting
    self._set_property(self.PROP_TX_RDS_PS_MISC, 0b0001100000001000 | int(config['DynRDSPty'])<<5)

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
    # TODO: Review before Si4713 support is done
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
      self._updatePS(PSdata)
      self._updateRT(RTdata)
      # Initial burst of RT groups to get it displayed quickly
      logging.debug('RT group burst')
      self._set_property(self.PROP_TX_RDS_PS_MIX, 0x02)  # Mix mode
      Timer(1, lambda: [logging.debug('RT group burst done'), self._set_property(self.PROP_TX_RDS_PS_MIX, 0x05)]).start()

  def _updatePS(self, psText):
    logging.debug('Si4713 _updatePS')
    if len(psText) > 96:
      logging.warning('PS text too long: %d (max 96) - truncating', len(psText))
      psText = psText[:96]

    # Ensure psText is a multiple of 8 in length
    psText = psText.ljust((len(psText) + 7) // 8 * 8)
    logging.info('PS \'%s\'', psText)

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
    logging.debug('Si4713 _updateRT')

    # Calculate max number of complete BCD groups * 4 chars per group, down to the nearest 32, back to characters
    rtMaxLength = self.totalCircularBuffers // 3 * 4 // 32 * 32
    logging.debug('RT length: %d, Abs Max Length: %d', len(rtText), rtMaxLength)

    if len(rtText) > rtMaxLength:
      rtText = rtText[:rtMaxLength]
      logging.warning('RT text too long: %d (max %d) - truncating', len(rtText), rtMaxLength)

    # Pad the last group so transmitting takes the same time as prior blocks
    if len(rtText) % 32 != 0:
        rtText = rtText.ljust((len(rtText) + 31) // 32 * 32)

    logging.info('RT \'%s\'', rtText.replace('\r','<0d>'))

    # Empty circular buffer
    self._send_command(self.CMD_TX_RDS_BUFF, [0b00000010, 0, 0, 0, 0, 0, 0])

    segmentOffset = 0
    ab_flag = True
    for i in range(0, len(rtText), 4):
      if i % 32 == 0:
        ab_flag = not ab_flag
        segmentOffset = 0

      rtBytes = [0b00000100, 0b00100000, ab_flag<<4 | segmentOffset]
      rtBytes.extend(list(rtText[i:i+4].encode('ascii')))
      # TODO: Can add to buffer twice as a way to slow down update speed
      self._send_command(self.CMD_TX_RDS_BUFF, rtBytes)
      rdsBuffData = self.I2C.read(0x00, 6)
      segmentOffset += 1
    logging.info('Circular Buffer: %d/%d', rdsBuffData[3], rdsBuffData[2] + rdsBuffData[3])

  def sendNextRDSGroup(self):
    logging.excessive('Si4713 sendNextRDSGroup')
    sleep(0.25)
