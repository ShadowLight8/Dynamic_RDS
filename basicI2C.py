import logging
import os
import smbus
from time import sleep

# ===============
# Basic I2C Class
# ===============
# Used by the Transmitter child classes (if they are i2c), but could also be used on its own if needed
# Assuming SMBus of 1 on most modern hardware - Can check /dev/i2c-* for available buses
class basicI2C(object):
  def __init__(self, address, bus=1):
    self.address = address
    # Bus 1 is Modern RPis, Bus 2 is BBB, Bus 0 is older RPis
    if os.path.exists('/dev/i2c-2') or os.path.exists('/sys/class/i2c-2'):
      bus = 2
    elif os.path.exists('/dev/i2c-0') or os.path.exists('/sys/class/i2c-0'):
      bus = 0
    logging.info('Using i2c bus {}'.format(bus))
    try:
      self.bus = smbus.SMBus(bus)
    except Exception:
        logging.exception("SMBus Init Error")
    sleep(2)

  def write(self, address, values, isFatal = False):
    # Simple i2c write - Always takes an list, even for 1 byte
    logging.excessive('I2C write at 0x{0:02x} of {1}'.format(address, ' '.join('0x{:02x}'.format(a) for a in values)))
    for i in range(8):
      try:
        self.bus.write_i2c_block_data(self.address, address, values)
      except Exception:
        logging.exception("write_i2c_block_data error")
        if i >= 1:
          sleep(i * .25)
        continue
      else:
        break
    else:
      logging.error("failed to write after multiple attempts")
      if isFatal:
        exit(-1)

  def read(self, address, num_bytes, isFatal = False):
    # Simple i2c read - Always returns a list
    for i in range(8):
      try:
        retVal = self.bus.read_i2c_block_data(self.address, address, num_bytes)
        logging.excessive('I2C read at 0x{0:02x} of {1} byte(s) returned {2}'.format(address, num_bytes, ' '.join('0x{:02x}'.format(a) for a in retVal)))
        return retVal
      except Exception:
        logging.exception("read_i2c_block_data error")
        if i >= 1:
          sleep(i * .25)
        continue
      else:
        break
    else:
      logging.error("failed to read after multiple attempts")
      if isFatal:
        exit(-1)