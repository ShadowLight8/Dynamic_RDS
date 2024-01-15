import logging
import os
import sys
from time import sleep
from datetime import datetime

from config import config
from basicI2C import basicI2C
from Transmitter import Transmitter

class QN8066(Transmitter):
  def __init__(self):
    super().__init__()
    self.I2C = basicI2C(0x21)
    self.PS = self.PSBuffer(self, ' ', int(config['DynRDSPSUpdateRate']))
    self.RT = self.RTBuffer(self, ' ', int(config['DynRDSRTUpdateRate']))
    self.activePWM = False

  def startup(self):
    logging.info('Starting QN80xx transmitter')

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

    # With everything started up, enable PWM
    # TODO: Check to see if PWM is enabled and amp power > 0, otherwise skip this
    # Check that PWM configured in /boot/config.txt and can be written to
    if os.path.isdir('/sys/class/pwm/pwmchip0') and os.access('/sys/class/pwm/pwmchip0/export', os.W_OK):
      pwmToUse = 0
      if config['DynRDSAdvPIPWMPin'] in {'13,4' , '19,2'}:
        pwmToUse = 1
      logging.debug(f'Setting up PWM{pwmToUse}')

      # Export PWM commands if needed
      if not os.path.isdir(f'/sys/class/pwm/pwmchip0/pwm{pwmToUse}'):
        logging.debug(f'Exporting PWM{pwmToUse}')
        with open('/sys/class/pwm/pwmchip0/export', 'w', encoding='UTF-8') as p:
          p.write(f'{pwmToUse}\n')

      logging.debug('Setting PWM period to 18300')
      with open(f'/sys/class/pwm/pwmchip0/pwm{pwmToUse}/period', 'w', encoding='UTF-8') as p:
        p.write('18300\n')

      logging.debug('Setting PWM duty cycle to %s', int(config['DynRDSQN8066AmpPower']) * 61)
      with open(f'/sys/class/pwm/pwmchip0/pwm{pwmToUse}/duty_cycle', 'w', encoding='UTF-8') as p:
        p.write(f'{int(config["DynRDSQN8066AmpPower"]) * 61}\n')

      logging.info(f'Enabling PWM{pwmToUse}')
      with open(f'/sys/class/pwm/pwmchip0/pwm{pwmToUse}/enable', 'w', encoding='UTF-8') as p:
        p.write('1\n')
      self.activePWM = True

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

  def shutdown(self):
    logging.info('Stopping QN80xx transmitter')
    # Exit TX, Enter standby
    self.I2C.write(0x00, [0b00100011])
    super().shutdown()

    # With everything stopped, disable PWM
    if self.activePWM:
      logging.debug('Stopping PWM')
      with open("/sys/class/pwm/pwmchip0/pwm0/duty_cycle", 'w', encoding='UTF-8') as p:
        p.write("0\n")

      logging.info('Disabling PWM')
      with open("/sys/class/pwm/pwmchip0/pwm0/enable", 'w', encoding='UTF-8') as p:
        p.write("0\n")
      self.activePWM = False

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
