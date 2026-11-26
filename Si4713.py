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
    self.resetPin = None # Will claim in startup(), release in shutdown()
    # RT A/B flag of the last fragment loaded. Kept across updates so new text starts with the opposite
    # flag - radios only clear the RT display when the flag changes (NRSC-4-B 6.1.5.3)
    self.rtAB = False
    # RT text currently in the chip's circular buffer, None when the buffer is empty or unknown
    self.loadedRT = None

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

  # Each RT message is a fixed 32-character fragment (known limitation: DynRDSRTSize is ignored).
  # A full 32 chars plus the 0x0D terminator needs a 9th 2A group, so every fragment gets 9 slots
  RT_FRAG_SIZE = 32
  RT_GROUPS_PER_FRAG = 9

  def _wait_for_cts(self, timeout=100):
    # Poll status-only reads until CTS is set (AN332 6.1). Each iteration is ~1ms.
    # The loop covers a busy chip (read succeeds, CTS=0); an empty read means basicI2C
    # already retried and the chip isn't answering, so give up immediately.
    for _ in range(timeout):
      response = self.I2C.readRaw(1)
      if not response:
        return False
      if response[0] & self.STATUS_CTS:
        return True
      sleep(0.001)
    logging.warning('Si4713 CTS timeout after ~%d ms', timeout)
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

  def _claimResetPin(self):
    # Idempotent: startup() can be called on an already-active transmitter
    if self.resetPin is None:
      self.resetPin = DigitalOutputDevice(int(config['DynRDSSi4713GPIOReset']), initial_value=False)

  def _releaseResetPin(self):
    if self.resetPin is not None:
      self.resetPin.off()
      self.resetPin.close()
      self.resetPin = None

  def startup(self):
    logging.info('Starting Si4713 transmitter')
    logging.info('Executing Reset with Pin %s', config['DynRDSSi4713GPIOReset'])
    # RST must stay driven high while the chip is running; a released pin can float or be pulled
    # low and silently reset the chip. Held until shutdown().
    self._claimResetPin()
    self.resetPin.off()
    sleep(0.01)
    self.resetPin.on()
    sleep(0.11)

    # Power up in transmit mode (Crystal oscillator and Analog audio input)
    self.I2C.write(self.CMD_POWER_UP, [0b00010010, 0b01010000], True)
    sleep(0.5) # Wait for power up
    if not self._wait_for_cts():
      logging.error('Si4713 failed to be read after power up')
      sys.exit(-1)

    # Verify chip by getting revision
    self._send_command(self.CMD_GET_REV, [], True)
    revData = self.I2C.readRaw(9, True)
    logging.info('Si47%02d - FW %d.%d - Chip Rev %d',
                 revData[1], revData[2], revData[3], revData[8])
    if revData[1] != 13:
      logging.error('Part Number value is %02d instead of 13. Is this a Si4713 chip?', revData[1])
      sys.exit(-1)

    # TODO: Make a function to use in status?
    self._send_command(self.CMD_TX_RDS_BUFF, [0, 0, 0, 0, 0, 0, 0], True)
    rdsBuffData = self.I2C.readRaw(6, True)
    logging.info('Circular Buffer: %d/%d, Fifo Buffer: %d/%d',
                  rdsBuffData[3], rdsBuffData[2] + rdsBuffData[3],
                  rdsBuffData[5], rdsBuffData[4] + rdsBuffData[5])
    self.totalCircularBuffers = rdsBuffData[2] + rdsBuffData[3]

    # Enable pilot, stereo, and RDS (if enabled)
    if config['DynRDSEnableRDS'] == "1":
      self._set_property(self.PROP_TX_COMPONENT_ENABLE, 0x0007)
    else:
      self._set_property(self.PROP_TX_COMPONENT_ENABLE, 0x0003)

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
    try:
      if self.active:
        self._send_command(self.CMD_POWER_DOWN, [])
    finally:
      self._releaseResetPin()
      # Held in reset, the chip loses its RDS buffers - startup() must reload them
      self.loadedRT = None
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
    status_data = self.I2C.readRaw(8)

    if status_data and status_data[0] & self.STATUS_CTS:
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

    # Same text already cycling on the chip (e.g. a settings save) - reloading would toggle A/B and
    # make radios clear and redraw identical text
    if rtText == self.loadedRT:
      logging.debug('RT unchanged, not reloading buffer')
      return
    requestedRT = rtText # Before truncation, so the check above matches the next identical update

    # Each 2A group takes 3 circular buffer blocks (B, C, D) and each fragment takes 9 groups
    rtMaxLength = self.totalCircularBuffers // 3 // self.RT_GROUPS_PER_FRAG * self.RT_FRAG_SIZE
    logging.debug('RT length: %d, Abs Max Length: %d', len(rtText), rtMaxLength)

    if len(rtText) > rtMaxLength:
      logging.warning('RT text too long: %d (max %d) - truncating', len(rtText), rtMaxLength)
      rtText = rtText[:rtMaxLength]

    # Every message under 64 chars needs a 0x0D terminator (IEC 62106) - each fragment is its own
    # message, so each gets one. Trailing spaces are stripped first so radios don't show the padding
    fragments = []
    for i in range(0, len(rtText), self.RT_FRAG_SIZE):
      fragments.append(rtText[i:i + self.RT_FRAG_SIZE].rstrip() + '\r')
    if not fragments:
      fragments.append('\r')

    logging.info('RT %s', [f.replace('\r', '<0d>') for f in fragments])

    # Empty circular buffer
    loaded = self._send_command(self.CMD_TX_RDS_BUFF, [0b00000010, 0, 0, 0, 0, 0, 0])

    # Known limitation: the chip doesn't report which fragment is on air, so with several old
    # fragments the first new one can still match the flag on air. With an odd fragment count the
    # buffer also wraps from the last fragment to the first with the same flag. A single fragment
    # (the common case) always gets a toggle on new text and never toggles while it repeats.
    rdsBuffData = []
    for fragment in fragments:
      self.rtAB = not self.rtAB
      # Pad to whole 4-char segments - the chars after 0x0D in its segment are ignored by radios
      fragment = fragment.ljust((len(fragment) + 3) // 4 * 4)
      segmentCount = len(fragment) // 4
      # Fill all 9 slots so every fragment is on air for the same time. A short fragment repeats its
      # own segments rather than sending segments past the 0x0D
      for slot in range(self.RT_GROUPS_PER_FRAG):
        segment = slot % segmentCount
        rtBytes = [0b00000100, 0b00100000, self.rtAB<<4 | segment]
        rtBytes.extend(list(fragment[segment * 4:segment * 4 + 4].encode('ascii')))
        loaded = self._send_command(self.CMD_TX_RDS_BUFF, rtBytes) and loaded
        rdsBuffData = self.I2C.readRaw(6)
    # Only skip a later identical update if every write made it - otherwise retry it next time
    self.loadedRT = requestedRT if loaded else None
    if rdsBuffData:
      logging.info('Circular Buffer: %d/%d', rdsBuffData[3], rdsBuffData[2] + rdsBuffData[3])

  def sendNextRDSGroup(self):
    logging.excessive('Si4713 sendNextRDSGroup')
    sleep(0.25)
