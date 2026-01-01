import logging
import os
import re
import subprocess
import sys

from config import config


PWM_FULL_RE = re.compile(
    r"(PWM\d+)(?:_CHAN(\d+)|_(\d+))",
    re.IGNORECASE
)

def createPWM() -> 'basicPWM':
  # Check if PWM is enabled
  if config['DynRDSQN8066PIPWM'] != '1':
    return basicPWM()

  platform = os.getenv('FPPPLATFORM', '')
  match platform:
    case 'Raspberry Pi':
      if ',' in config['DynRDSAdvPIPWMPin']:
        logging.info('Using hardware PWM config: %s', config['DynRDSAdvPIPWMPin'])
        return hardwarePWM(int(config['DynRDSAdvPIPWMPin'].split(',', 1)[0]))
      logging.info('Using software PWM pin: %s', config['DynRDSAdvPIPWMPin'])
      return softwarePWM(int(config['DynRDSAdvPIPWMPin']))
    case 'BeagleBone Black':
      logging.info('Using BBB hardware PWM config: %s', config['DynRDSAdvBBBPWMPin'])
      return hardwareBBBPWM(config['DynRDSAdvBBBPWMPin'])
    case _:
      logging.warning('Unknown platform: %s, PWM disabled', platform)
      return basicPWM()

class basicPWM:
  def __init__(self):
    self.active = False

  def startup(self, _period=10000, dutyCycle=0): # pylint: disable=unused-argument
    self.active = True

  def update(self, dutyCycle=0):
    pass

  def shutdown(self):
    self.active = False

  def status(self):
    # TODO: String about PWM status?
    pass

class hardwarePWM(basicPWM):
  def __init__(self, pwmGPIOPin=18):
    pwmInfo = self._getPWMInfoFromPinctrl(pwmGPIOPin)
    if pwmInfo is None:
      logging.error('Unable to determine PWM channel for GPIO%s', pwmGPIOPin)
      sys.exit(-1)

    self.pwmToUse = pwmInfo
    if os.path.isdir('/sys/class/pwm/pwmchip0') and os.access('/sys/class/pwm/pwmchip0/export', os.W_OK):
      logging.info('Initializing hardware PWM channel %s on GPIO%s', self.pwmToUse, pwmGPIOPin)
    else:
      raise RuntimeError('Unable to access /sys/class/pwm/pwmchip0 or export')

    if not os.path.isdir(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}'):
      logging.debug('Exporting hardware PWM channel %s', self.pwmToUse)
      with open('/sys/class/pwm/pwmchip0/export', 'w', encoding='UTF-8') as p:
        p.write(f'{self.pwmToUse}\n')

    super().__init__()

  def _getPWMInfoFromPinctrl(self, gpioPin=18):
    try:
      result = subprocess.run(
                 ["pinctrl", "get", str(gpioPin)],
                 capture_output=True,
                 text=True,
                 check=True,
               )
    except (subprocess.CalledProcessError, FileNotFoundError):
      return None

    m = PWM_FULL_RE.search(result.stdout)
    if not m:
      return None

    return m.group(2) or m.group(3)
    # "pwm": m.group(1).lower()

  def startup(self, period=18300, dutyCycle=0):
    logging.debug('Starting hardware PWM channel %s with period of %s', self.pwmToUse, period)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/period', 'w', encoding='UTF-8') as p:
      p.write(f'{period}\n')
    self.update(dutyCycle)
    logging.info('Enabling hardware PWM channel %s', self.pwmToUse)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/enable', 'w', encoding='UTF-8') as p:
      p.write('1\n')
    super().startup()

  def update(self, dutyCycle=0):
    logging.info('Updating hardware PWM channel %s duty cycle to %s', self.pwmToUse, dutyCycle*61)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/duty_cycle', 'w', encoding='UTF-8') as p:
      p.write(f'{dutyCycle*61}\n')
    super().update()

  def shutdown(self):
    logging.debug('Shutting down hardware PWM%s', self.pwmToUse)
    self.update() #Duty Cycle to 0
    logging.info('Disabling hardware PWM channel %s', self.pwmToUse)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/enable', 'w', encoding='UTF-8') as p:
      p.write('0\n')
    super().shutdown()

class softwarePWM(basicPWM):
  def __init__(self, pinToUse=7):
    logging.info('Initializing software PWM on GPIO pin %s (board pin %s)', self._board_to_bcm(pinToUse), pinToUse)
    global PWMLED
    from gpiozero import PWMLED
    # Convert board pin to BCM GPIO number
    bcm_pin = self._board_to_bcm(pinToUse)
    self.pinToUse = pinToUse
    self.bcm_pin = bcm_pin
    self.pwm = None

    # Create PWMLED device (starts at 0% duty cycle, off)
    self.pwm = PWMLED(bcm_pin, initial_value=0)
    super().__init__()

  def _board_to_bcm(self, board_pin):
    """Convert board pin number to BCM GPIO number."""
    # Mapping for 40-pin Raspberry Pi header (board -> BCM)
    board_to_bcm_map = {
      7: 4,   8: 14,  10: 15,  11: 17,  12: 18,  13: 27,
      15: 22, 16: 23, 18: 24,  19: 10,  21: 9,   22: 25,
      23: 11, 24: 8,  26: 7,   27: 0,   28: 1,   29: 5,
      31: 6,  32: 12, 33: 13,  35: 19,  36: 16,  37: 26,
      38: 20, 40: 21
    }

    if board_pin not in board_to_bcm_map:
      raise ValueError(f'Invalid board pin number: {board_pin}')

    return board_to_bcm_map[board_pin]

  def startup(self, period=10000, dutyCycle=0):
    # gpiozero uses frequency in Hz, convert from period in microseconds
    # frequency = 1 / (period / 1,000,000)
    frequency = 1_000_000 / period
    logging.debug('Starting software PWM on GPIO %s (board pin %s) with frequency %.2f Hz',self.bcm_pin, self.pinToUse, frequency)
    self.pwm.frequency = frequency
    initial_value = (dutyCycle / 3) / 100
    logging.info('Setting software PWM on GPIO %s initial duty cycle to %.2f%%', self.bcm_pin, dutyCycle / 3)
    self.pwm.value = initial_value
    super().startup()

  def update(self, dutyCycle=0):
    value = (dutyCycle / 3) / 100
    logging.info('Updating software PWM on GPIO %s duty cycle to %.2f%%', self.bcm_pin, dutyCycle / 3)
    self.pwm.value = value
    super().update()

  def shutdown(self):
    logging.debug('Shutting down software PWM on GPIO %s (board pin %s)', self.bcm_pin, self.pinToUse)
    self.pwm.off()
    logging.info('Cleaning up software PWM on GPIO %s', self.bcm_pin)
    # gpiozero handles cleanup automatically, but explicitly close
    self.pwm.close()
    super().shutdown()

class hardwareBBBPWM(basicPWM):
  def __init__(self, pwmInfo='P9_16,1,B'):
    (self.pinToUse, self.pwmToUse, self.ABToUse) = pwmInfo.split(',', 2)
    logging.info('Initializing hardware PWM on pin %s', self.pinToUse)
    if self.pwmToUse == '0':
      self.pwmToUse = '48300200'
    elif self.pwmToUse == '2':
      self.pwmToUse = '48304200'
    else: # Make 1 the default case
      self.pwmToUse = '48302200'
    self.ABToUse = '0' if self.ABToUse == 'A' else '1'

    if os.path.isfile(f'/sys/devices/platform/ocp/ocp:{self.pinToUse}_pinmux/state'):
      logging.info('Configuring pin %s for PWM', self.pinToUse)
      with open(f'/sys/devices/platform/ocp/ocp:{self.pinToUse}_pinmux/state', 'w', encoding='UTF-8') as p:
        p.write('pwm\n')
    else:
      raise RuntimeError(f'Unable to access /sys/devices/platform/ocp/ocp:{self.pinToUse}_pinmux/state')

    with os.scandir('/sys/class/pwm/') as chips:
      for chip in chips:
        if chip.is_symlink() and self.pwmToUse in os.readlink(chip):
          self.pwmToUse = chip.name
          logging.debug('PWM hardware is %s', self.pwmToUse)
          break

    if not os.path.isdir(f'/sys/class/pwm/{self.pwmToUse}/pwm{self.ABToUse}'):
      logging.debug('Exporting hardware %s/pwm%s', self.pwmToUse, self.ABToUse)
      with open(f'/sys/class/pwm/{self.pwmToUse}/export', 'w', encoding='UTF-8') as p:
        p.write(f'{self.ABToUse}\n')

    super().__init__()

  def startup(self, period=18300, dutyCycle=0):
    logging.debug('Starting hardware %s/pwm%s with period of %s', self.pwmToUse, self.ABToUse, period)
    with open(f'/sys/class/pwm/{self.pwmToUse}/pwm{self.ABToUse}/period', 'w', encoding='UTF-8') as p:
      p.write(f'{period}\n')
    self.update(dutyCycle)
    logging.info('Enabling hardware %s/pwm%s', self.pwmToUse, self.ABToUse)
    with open(f'/sys/class/pwm/{self.pwmToUse}/pwm{self.ABToUse}/enable', 'w', encoding='UTF-8') as p:
      p.write('1\n')
    super().startup()

  def update(self, dutyCycle=0):
    logging.info('Updating hardware %s/pwm%s duty cycle to %s', self.pwmToUse, self.ABToUse, dutyCycle*61)
    with open(f'/sys/class/pwm/{self.pwmToUse}/pwm{self.ABToUse}/duty_cycle', 'w', encoding='UTF-8') as p:
      p.write(f'{dutyCycle*61}\n')
    super().update()

  def shutdown(self):
    logging.debug('Shutting down hardware %s/pwm%s', self.pwmToUse, self.ABToUse)
    self.update() #Duty Cycle to 0
    logging.info('Disabling hardware %s/pwm%s', self.pwmToUse, self.ABToUse)
    with open(f'/sys/class/pwm/{self.pwmToUse}/pwm{self.ABToUse}/enable', 'w', encoding='UTF-8') as p:
      p.write('0\n')
    super().shutdown()
