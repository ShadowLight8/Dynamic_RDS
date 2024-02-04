import logging
import sys
import os
from time import sleep
from datetime import datetime

from config import config
from basicI2C import basicI2C
from basicPWM import basicPWM, hardwarePWM, softwarePWM, hardwareBBBPWM
from Transmitter import Transmitter

class QN8066(Transmitter):
  def __init__(self):
    logging.info('Initializing QN8066 transmitter')
    super().__init__()
    self.I2C = basicI2C(0x21)
    self.PS = self.PSBuffer(self, ' ', int(config['DynRDSPSUpdateRate']))
    self.RT = self.RTBuffer(self, ' ', int(config['DynRDSRTUpdateRate']))
    self.basicPWM = basicPWM()

  def startup(self):
    logging.info('Starting QN8066 transmitter')

    tempReadValue = self.I2C.read(0x06, 1)[0]>>2
    if tempReadValue != 0b1101:
      logging.error('Chip ID value is %s instead of 13. Is this a QN8066 chip?', tempReadValue)
      sys.exit(-1)

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

    # Reset aud_pk
    self.I2C.write(0x24, [0b10000000 | int(max(24,(int(config['DynRDSQN8066ChipPower']) - 70.2) // 0.91))])
    self.I2C.write(0x24, [0b00000000 | int(max(24,(int(config['DynRDSQN8066ChipPower']) - 70.2) // 0.91))])

    self.update()
    super().startup()

    # With everything started up, select and enable needed PWM type
    if os.getenv('FPPPLATFORM', '') == 'Raspberry Pi':
      if config['DynRDSQN8066PIPWM'] == '1':
        if config['DynRDSAdvPIPWMPin'] in {'18,2' , '12,4'}:
          self.basicPWM = hardwarePWM(0)
          self.basicPWM.startup(18300, int(config['DynRDSQN8066AmpPower']))
        elif config['DynRDSAdvPIPWMPin'] in {'13,4' , '19,2'}:
          self.basicPWM = hardwarePWM(1)
          self.basicPWM.startup(18300, int(config['DynRDSQN8066AmpPower']))
        else:
          self.basicPWM = softwarePWM(int(config['DynRDSAdvPIPWMPin']))
          self.basicPWM.startup(10000, int(config['DynRDSQN8066AmpPower']))
      #else:
        #self.basicPWM.startup()
    elif os.getenv('FPPPLATFORM', '') == 'BeagleBone Black':
      self.basicPWM = hardwareBBBPWM(config['DynRDSAdvBBBPWMPin'])
      self.basicPWM.startup(18300, int(config['DynRDSQN8066AmpPower']))
    #else:
      #self.basicPWM.startup()

  def update(self):
    # Try without 0x25 0b01111101 - TX Freq Dev of 86.25KHz
    # Try without 0x26 0b00111100 - RDS Freq Dev of 21KHz

    # TODO: New option to configure soft clip level 3db is the default (also 4.5db, 6db, and 9db)
    self.I2C.write(0x27, [0b00111010], True)

    # Stop Auto Gain Correction (AGC), which introduces obvious poor sounding audio changes
    if config['DynRDSQN8066AGC'] == '0':
      self.I2C.write(0x6e, [0b10110111], True)
    # TODO: Else if it is re-enabled

    # TX gain changes and input impedance
    self.I2C.write(0x28, [int(config['DynRDSQN8066SoftClipping'])<<7 | int(config['DynRDSQN8066BufferGain'])<<4 | int(config['DynRDSQN8066DigitalGain'])<<2 | int(config['DynRDSQN8066InputImpedance'])], True)
    #self.I2C.write(0x28, [0b01011011])

    # PWM get updated
    self.basicPWM.update(int(config['DynRDSQN8066AmpPower']))

  def shutdown(self):
    logging.info('Stopping QN8066 transmitter')
    # Exit TX, Enter standby
    self.I2C.write(0x00, [0b00100011])
    super().shutdown()

    # With everything stopped, shutdown PWM
    self.basicPWM.shutdown()

  def reset(self, resetdelay=1):
    # Used to restart the transmitter
    self.shutdown()
    del self.I2C
    self.I2C = basicI2C(0x21)
    sleep(resetdelay)
    self.startup()

  def status(self):
    aud_pk = self.I2C.read(0x1a, 1)[0]>>3 & 0b1111
    fsm = self.I2C.read(0x0a,1)[0]>>4
    # TODO: Check frequency? 0x19 1:0 + 0x1b
    # TODO: Add PWM status if active - Might move elsewhere if PWM gets located to a single file

    logging.info('Status - State %s (expect 10) - Audio Peak %s (target <= 14)', fsm, aud_pk)

    # Reset aud_pk
    self.I2C.write(0x24, [0b10000000 | int(max(24,(int(config['DynRDSQN8066ChipPower']) - 70.2) // 0.91))])
    self.I2C.write(0x24, [0b00000000 | int(max(24,(int(config['DynRDSQN8066ChipPower']) - 70.2) // 0.91))])
    super().status()

  def updateRDSData(self, PSdata, RTdata):
    logging.debug('QN8066 updateRDSData')
    super().updateRDSData(PSdata, RTdata)
    self.PS.updateData(PSdata)
    self.RT.updateData(RTdata)

  def sendNextRDSGroup(self):
    # If more advanced mixing of RDS groups is needed, this is where it would occur
    logging.excessive('QN8066 sendNextRDSGroup')
    self.PS.sendNextGroup()
    self.RT.sendNextGroup()

  def transmitRDS(self, rdsBytes):
    # Specific to QN 8036 and 8066 chips
    rdsStatusByte = self.I2C.read(0x01, 1)[0]
    rdsSendToggleBit = rdsStatusByte >> 1 & 0b1
    rdsSentStatusToggleBit = self.I2C.read(0x1a, 1)[0] >> 2 & 0b1
    logging.excessive('Transmit %s - Send Bit %s - Status Bit %s', ' '.join('0x{:02x}'.format(a) for a in rdsBytes), rdsSendToggleBit, rdsSentStatusToggleBit)
    self.I2C.write(0x1c, rdsBytes)
    self.I2C.write(0x01, [rdsStatusByte ^ 0b10])
    # RDS specifications indicate 87.6ms to send a group
    # sleep is a bit less, plus time to read the status toggle bit
    sleep(0.087)
    if (self.I2C.read(0x1a, 1)[0] >> 2 & 1) == rdsSentStatusToggleBit:
      i = 0
      while (self.I2C.read(0x1a, 1)[0] >> 2 & 1) == rdsSentStatusToggleBit:
        logging.excessive('Waiting for rdsSentStatusToggleBit to flip')
        sleep(0.01)
        i += 1
        if i > 50:
          logging.error('rdsSentStatusToggleBit failed to flip')
          # RDS has failed to update, reset the QN8066
          self.reset()
          break

  class PSBuffer(Transmitter.RDSBuffer):
    # Sends RDS type 0B groups - Program Service
    # Fragment size of 8, Groups send 2 characters at a time
    def __init__(self, outer, data, delay=4):
      super().__init__(data, 8, 2, delay)
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
      rdsBytes = [self.pi_byte1, self.pi_byte2, 0b1000<<2 | self.pty>>3, (0b00111 & self.pty)<<5 | self.ab<<4 | self.currentGroup]
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size]))
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 1]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 2 else 0x20)
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 2]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 3 else 0x20)
      rdsBytes.append(ord(self.fragments[self.currentFragment][self.currentGroup * self.group_size + 3]) if len(self.fragments[self.currentFragment]) - self.currentGroup * self.group_size >= 4 else 0x20)

      self.outer.transmitRDS(rdsBytes)
      self.currentGroup += 1
      if self.currentGroup * self.group_size >= len(self.fragments[self.currentFragment]):
        self.currentGroup = 0
