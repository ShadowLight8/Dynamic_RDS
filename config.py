import os

config = {
'DynRDSEnableRDS': '1',
'DynRDSPSUpdateRate': '4',
'DynRDSPSStyle': 'Merry|Christ-|  -mas!|{T}|{A}|[{N} of {C}]',
'DynRDSRTUpdateRate': '8',
'DynRDSRTSize': '32',
'DynRDSRTStyle': 'Merry Christmas!|{T}[ by {A}]|[Track {N} of {C}]',
'DynRDSPty': '2',
'DynRDSPICode': '819b',
'DynRDSTransmitter': 'None',
'DynRDSFrequency': '100.1',
'DynRDSPreemphasis': '75us',
'DynRDSQN8066Gain': '0',
'DynRDSQN8066SoftClipping': '0',
'DynRDSQN8066AGC': '0',
'DynRDSQN8066ChipPower': '122',
'DynRDSQN8066PIHardwarePWM': 0,
'DynRDSQN8066AmpPower': '0',
'DynRDSStart': 'FPPDStart',
'DynRDSStop': 'Never',
'DynRDSCallbackLogLevel': 'INFO',
'DynRDSEngineLogLevel': 'INFO',
'DynRDSmpcEnable': '0',
'DynRDSAdvPISoftwareI2C': '0',
'DynRDSAdvPIPWMPin': '18,2'
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
