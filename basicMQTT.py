#!/usr/bin/python3

import logging
import json
from urllib.request import urlopen
from urllib.parse import quote

class basicMQTT:
  def __init__(self):
    self.connected = False

  def connect(self):
    self.connected = True

  def publish(self, subtopic, value, qos=1, retain=True):
    pass

  def disconnect(self):
    self.connected = False

  def status(self):
    pass

class pahoMQTT(basicMQTT):
  # Command line to monitor: mosquitto_sub -v -d -h localhost -t "#"
  def __init__(self):
    global paho
    import paho.mqtt.client as paho

    # Pull in FPP setting needed for MQTT via API
    self.MQTTSettings = {}
    self.MQTTSettings['HostName'] = self.readAPISetting('HostName')['value']

    mqttInfo = self.readAPISetting('MQTTHost')
    self.MQTTSettings['MQTTHost'] = mqttInfo['value']

    for setting in mqttInfo['children']['*']:
      settingInfo = self.readAPISetting(setting)
      self.MQTTSettings[setting] = settingInfo['value'] if 'value' in settingInfo else ''

    logging.debug('MQTT Settings %s', self.MQTTSettings)

    self.topicBase = f'falcon/player/{self.MQTTSettings["HostName"]}/plugin/Dynamic_RDS'
    if self.MQTTSettings["MQTTPrefix"] != '':
      self.topicBase = f'{self.MQTTSettings["MQTTPrefix"]}/{self.topicBase}'

    self.client = paho.Client()
    self.client.enable_logger()
    super().__init__()

  def connect(self):
    self.client.on_connect = self.on_connect
    if self.MQTTSettings['MQTTUsername'] != '':
      self.client.username_pw_set(self.MQTTSettings['MQTTUsername'], self.MQTTSettings['MQTTPassword'])
    self.client.will_set(f'{self.topicBase}/ready', '-1', 0, True)
    self.client.connect_async(self.MQTTSettings['MQTTHost'], self.MQTTSettings['MQTTPort'])
    self.client.loop_start()

  def publish(self, subtopic, value, qos=1, retain=True):
    self.client.publish(f'{self.topicBase}/{subtopic}', value, qos, retain)

  def disconnect(self):
    self.publish('ready', '0')
    self.client.loop_stop()
    self.client.disconnect()
    super().disconnect()

  def status(self):
    pass

  def on_connect(self, client, userdata, flags, rc):
    # TODO: Maybe something to log here?
    super().connect()

  def on_publish(self):
    pass

  def readAPISetting(self, settingName):
    try:
      with urlopen(f'http://localhost/api/settings/{quote(settingName)}') as response:
        return json.loads(response.read())
    except Exception:
      logging.exception("readAPISetting %s", settingName)
    return ''
