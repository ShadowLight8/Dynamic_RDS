import os
import logging

class basicPWM:
  def __init__(self):
    self.active = False

  def startup(self, period=10000, dutyCycle=0):
    self.active = True

  def update(self, dutyCycle=0):
    pass

  def shutdown(self):
    self.active = False

  def status(self):
    # TODO: String about PWM status?
    pass

class hardwarePWM(basicPWM):
  def __init__(self, pwmToUse=0):
    self.pwmToUse = pwmToUse
    if os.path.isdir('/sys/class/pwm/pwmchip0') and os.access('/sys/class/pwm/pwmchip0/export', os.W_OK):
      logging.info('Initializing hardware PWM%s', self.pwmToUse)
    else:
      raise RuntimeError('Unable to access /sys/class/pwm/pwmchip0')

    if not os.path.isdir(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}'):
      logging.debug('Exporting hardware PWM%s', pwmToUse)
      with open('/sys/class/pwm/pwmchip0/export', 'w', encoding='UTF-8') as p:
        p.write(f'{pwmToUse}\n')

    super().__init__()

  def startup(self, period=18300, dutyCycle=0):
    logging.debug('Starting hardware PWM%s with period of %s', self.pwmToUse, period)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/period', 'w', encoding='UTF-8') as p:
      p.write(f'{period}\n')
    self.update(dutyCycle)
    logging.info('Enabling hardware PWM%s', self.pwmToUse)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/enable', 'w', encoding='UTF-8') as p:
      p.write('1\n')
    super().startup()

  def update(self, dutyCycle=0):
    logging.info('Updating hardware PWM%s duty cycle to %s', self.pwmToUse, dutyCycle*61)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/duty_cycle', 'w', encoding='UTF-8') as p:
      p.write(f'{dutyCycle*61}\n')
    super().update()

  def shutdown(self):
    logging.debug('Shutting down hardware PWM%s', self.pwmToUse)
    self.update() #Duty Cycle to 0
    logging.info('Disabling hardware PWM%s', self.pwmToUse)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/enable', 'w', encoding='UTF-8') as p:
      p.write('0\n')
    super().shutdown()

class softwarePWM(basicPWM):
  def __init__(self, pinToUse=7):
    import RPi.GPIO as GPIO
    self.pinToUse = pinToUse
    self.pwm = None
    # TODO: Ponder if import RPi.GPIO as GPIO is a good idea
    logging.info('Initializing software PWM on pin %s', self.pinToUse)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(self.pinToUse, GPIO.OUT)
    GPIO.output(self.pinToUse,0)
    super().__init__()

  def startup(self, period=10000, dutyCycle=0):
    logging.debug('Starting software PWM on pin %s with period of %s', self.pinToUse, period)
    self.pwm = GPIO.PWM(self.pinToUse, period)
    logging.info('Updating software PWM on pin %s initial duty cycle to %s', self.pinToUse, round(dutyCycle/3,2))
    self.pwm.start(dutyCycle/3)
    super().startup()

  def update(self, dutyCycle=0):
    logging.info('Updating software PWM on pin %s duty cycle to %s', self.pinToUse, round(dutyCycle/3,2))
    self.pwm.ChangeDutyCycle(dutyCycle/3)
    super().update()

  def shutdown(self):
    logging.debug('Shutting down software PWM on pin %s', self.pinToUse)
    self.pwm.stop()
    logging.info('Cleaning up software PWM on pin %s', self.pinToUse)
    GPIO.cleanup()
    super().shutdown()

class hardwareBBBPWM(basicPWM):
  def __init__(self, pwmInfo='P9_16,1,B'):
    (self.pinToUse, self.pwmToUse, self.ABToUse) = pwmInfo.split(',', 2)
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

