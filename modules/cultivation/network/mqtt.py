"""Supervised TLS subscriber; credentials never enter process arguments or logs."""
from pathlib import Path
from queue import Queue,Full
from threading import Thread
import json
import os
import subprocess
from .contracts import NetworkError

class MqttCapture:
    def __init__(self,host_config,settings):
        self.config=host_config;self.settings=settings
        self.queue=Queue(maxsize=64)
        self.ready=False;self.failed=False;self.error=None;self.dropped=0
        self.process=None;self.job=None

    def start(self):
        self.config.verify_mqtt()
        script=Path(__file__).resolve().parents[3]/'scripts'/'cultivation_network_mqtt.py'
        env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','PATH'}}
        self.process=subprocess.Popen([self.config.python,'-I',str(script),'--packages',self.config.packages],
            shell=False,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            if os.name=='nt':
                from ..radio.process_guard import KillOnCloseJob
                self.job=KillOnCloseJob(self.process)
            self.process.stdin.write((json.dumps(self.settings)+'\n').encode())
            self.process.stdin.flush();self.process.stdin.close();self.settings=None
            Thread(target=self._read,name='cultivation-network-mqtt-reader',daemon=True).start()
        except Exception:
            self.stop();raise NetworkError('mqtt_runtime_unavailable') from None
        return self

    def _read(self):
        try:
            while self.process and self.process.stdout:
                line=self.process.stdout.readline(131073)
                if not line:break
                if len(line)>131072:raise NetworkError('message_limit')
                row=json.loads(line)
                if not isinstance(row,dict):raise NetworkError('malformed_message')
                if row.get('type')=='ready':self.ready=True
                elif row.get('type') in ('error','disconnected'):
                    self.error=row.get('code') if row.get('code') in {'authorization_failed','subscription_failed','message_limit'} else 'connection_unavailable'
                    self.failed=True;break
                elif row.get('type')=='uplink':
                    try:self.queue.put_nowait(row)
                    except Full:self.dropped+=1
        except Exception:self.failed=True;self.error='mqtt_stream_failed'
        finally:
            self.ready=False
            if self.process and self.process.poll() is None:self.process.terminate()

    def alive(self):
        return self.process is not None and self.process.poll() is None and not self.failed

    def stop(self):
        self.ready=False
        if self.job:self.job.close();self.job=None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill();self.process.wait(timeout=2)
        if self.process and self.process.stdout:self.process.stdout.close()
        self.settings=None
