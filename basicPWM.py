#import RPi.GPIO as GPIO
import os
import logging

class basicPWM:
  def __init__(self):
    self.active = False

  def startup(self):
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
    logging.info('Updating hardware PWM%s duty cycle to %s', self.pwmToUse, dutyCycle)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/duty_cycle', 'w', encoding='UTF-8') as p:
      p.write(f'{dutyCycle}\n')
    super().update()

  def shutdown(self):
    logging.debug('Shutting down hardware PWM%s', self.pwmToUse)
    self.update() #Duty Cycle to 0
    logging.info('Disabling hardware PWM%s', self.pwmToUse)
    with open(f'/sys/class/pwm/pwmchip0/pwm{self.pwmToUse}/enable', 'w', encoding='UTF-8') as p:
      p.write('0\n')
    super().shutdown()

class softwarePWM(basicPWM):
#GPIO.setmode(GPIO.BOARD)
# Setup on Pin 7 / GPIO 4
#GPIO.setup(7, GPIO.OUT)
#GPIO.output(7, 0)
#pwm = GPIO.PWM(7, 18000)
#pwm.start(0) #Duty cycle at 0
#pwm.ChangeDutyCycle(40/3)
#pwm.stop()
#GPIO.cleanup()
  def __init__(self):
    super().__init__()

  def startup(self):
    super().startup()

  def update(self):
    super().update()

  def shutdown(self):
    super().shutdown()

# If QN8066
# If Enable Pi PWM enabled & Amp Power > 0 & Software Pin selected

