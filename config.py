import os
import logging

config = {
'DynRDSEnableRDS': '1',
'DynRDSPSUpdateRate': '4',
'DynRDSPSStyle': '{T}|{A}[|{P} of {C}]|Merry|Christ-|   -mas!',
'DynRDSRTUpdateRate': '8',
'DynRDSRTSize': '32',
'DynRDSRTStyle': '{T}[ by {A}][|Track {P} of {C}  ]Merry Christmas!',
'DynRDSPty': '2',
'DynRDSPICode': '819b',
'DynRDSTransmitter': 'None',
'DynRDSFrequency': '100.1',
'DynRDSPreemphasis': '75us',

'DynRDSQN8066Gain': '0',
'DynRDSQN8066SoftClipping': '0',
'DynRDSQN8066AGC': '0',
'DynRDSQN8066ChipPower': '122',
'DynRDSQN8066PIPWM': 0,
'DynRDSQN8066AmpPower': '0',

'DynRDSStart': 'FPPDStart',
'DynRDSStop': 'Never',
'DynRDSCallbackLogLevel': 'INFO',
'DynRDSEngineLogLevel': 'INFO',
'DynRDSmpcEnable': '0',
'DynRDSAdvPISoftwareI2C': '0',
'DynRDSAdvPIPWMPin': '18,2',
'DynRDSAdvBBBPWMPin': 'P9_16,1,B',
'DynRDSmqttEnable': '0',

'DynRDSSi4713GPIOReset': '4',
'DynRDSSi4713TuningCap': '0',
'DynRDSSi4713ChipPower': '115',
'DynRDSSi4713TestAudio': ''
}

def read_config_from_file():
  configfile = os.getenv('CFGDIR', '/home/fpp/media/config') + '/plugin.Dynamic_RDS'
  try:
    with open(configfile, 'r', encoding='UTF-8') as f:
      for confline in f:
        (confkey, confval) = confline.split(' = ')
        config[confkey] = confval.replace('"', '').strip()
  except IOError:
    logging.warning('No config file found, using defaults.')
  except Exception:
    logging.exception('read_config')
