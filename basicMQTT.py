import logging
import time

class basicMQTT:
  def __init__(self):
    self.connected = False

  def connect(self):
    self.connected = True

  def publish(self):
    pass

  def disconnect(self):
    self.connected = False

  def status(self):
    pass

class pahoMQTT:
  # Command line to monitor: mosquitto_sub -v -d -h localhost -t "#"
  def __init__(self):
    global paho
    import paho.mqtt.client as paho
    # Pull MQTTHost, then get all children's values
    # api/settings/MQTTHost
    # { "name": "MQTTHost", "description": "Broker Host", "tip": "Hostname or IP of your MQTT broker", "restart": 2, "type": "text", "size": 32, "maxlength": 64, "children": { "*": [ "MQTTPort", "MQTTClientId", "MQTTPrefix", "MQTTUsername", "MQTTPassword", "MQTTCaFile", "MQTTFrequency", "MQTTSubscribe" ] }, "value": "localhost" }
    super().__init__()

  def connect(self):
    self.client = paho.Client()
    self.client.on_connect = self.on_connect
    self.client.connect_async('localhost', 1883)
    self.client.loop_start()

  def publish(self):
    self.client.publish('falcon/player/FPP-DevPi/Dynamic_RDS/ready', '1', qos=1)

  def disconnect(self):
    self.client.loop_stop()

  def status(self):
    pass

  def on_connect(self, client, userdata, flags, rc):
    print('On_Connect')
    self.connected = True

  def on_publish(self):
    pass

print('Init')
test = pahoMQTT()
print('Connect')
test.connect()
#print('Sleep')
#time.sleep(5)
print('Publish')
test.publish()
print('Sleep')
time.sleep(5)
print('Disconnect')
test.disconnect()
print('Done')
