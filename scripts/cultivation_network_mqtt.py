"""Isolated read-only Things Stack subscriber. Secret arrives only over stdin."""
from pathlib import Path
import argparse
import json
import re
import ssl
import sys
import threading


def emit(value):
    sys.stdout.write(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n')
    sys.stdout.flush()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--packages',required=True)
    args=parser.parse_args()
    packages=Path(args.packages)
    if not packages.is_absolute() or not (packages/'paho'/'mqtt'/'client.py').is_file():
        return 2
    sys.path.insert(0,str(packages))
    from paho.mqtt import client as mqtt
    # Parent creates its kill-on-close job before providing this configuration.
    line=sys.stdin.buffer.readline(8193)
    if not line or len(line)>8192:return 2
    config=json.loads(line)
    if not isinstance(config,dict) or set(config)!={'host','port','username','password','topic','application_id'}:return 2
    host=config['host'];username=config['username'];topic=config['topic']
    if not isinstance(host,str) or not re.fullmatch(r'(?:(?:[a-z0-9][a-z0-9-]{1,34}[a-z0-9])\.)?(?:eu1|nam1|au1)\.cloud\.thethings\.(?:network|industries)',host):return 2
    if config['port']!=8883 or not re.fullmatch(r'[a-z0-9-]{3,36}@[a-z0-9-]{3,36}',username):return 2
    if topic!='v3/'+username+'/devices/+/up' or config['application_id']!=username.split('@')[0]:return 2
    secret=config['password']
    if not isinstance(secret,str) or not 16<=len(secret)<=1024 or any(c.isspace() for c in secret):return 2
    stopped=threading.Event()
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,protocol=mqtt.MQTTv311,
                       clean_session=True,reconnect_on_failure=False)
    client.username_pw_set(username,secret)
    client.tls_set_context(ssl.create_default_context())
    client.connect_timeout=5
    def connected(c,_data,_flags,reason,_properties):
        if reason.is_failure:
            emit({'type':'error','code':'authorization_failed'});stopped.set();return
        result,_mid=c.subscribe(topic,qos=0)
        if result!=mqtt.MQTT_ERR_SUCCESS:
            emit({'type':'error','code':'subscription_failed'});stopped.set()
    def subscribed(_c,_data,_mid,reasons,_properties):
        if not reasons or any(reason.is_failure for reason in reasons):
            emit({'type':'error','code':'subscription_failed'});stopped.set()
        else:emit({'type':'ready','qos':0})
    def received(_c,_data,message):
        if len(message.payload)>65536:
            emit({'type':'error','code':'message_limit'});stopped.set();return
        try:
            payload=json.loads(message.payload)
            emit({'type':'uplink','topic':message.topic,'payload':payload})
        except (ValueError,UnicodeError,RecursionError):
            emit({'type':'ignored','code':'malformed_message'})
    def disconnected(_c,_data,_flags,_reason,_properties):
        emit({'type':'disconnected'});stopped.set()
    client.on_connect=connected;client.on_subscribe=subscribed
    client.on_message=received;client.on_disconnect=disconnected
    try:
        client.connect(host,8883,keepalive=30)
        client.loop_start()
        while not stopped.wait(1):pass
    finally:
        client.disconnect();client.loop_stop()
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        emit({'type':'error','code':'mqtt_connection_unavailable'})
        raise SystemExit(1) from None
