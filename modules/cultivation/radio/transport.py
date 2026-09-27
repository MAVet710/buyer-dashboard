"""Pinned receive-only child processes. Local stdout, never a network endpoint."""
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Full
from threading import Thread
import json
import os
import subprocess
import sys
from .codecs import decode_bthome, decode_wh31, RadioInputError

def command(receiver):
    receiver.verify()
    if receiver.kind == 'ble':
        if sys.platform != 'win32':
            raise RadioInputError('passive_backend_not_verified')
        script = Path(__file__).resolve().parents[3] / 'scripts' / 'cultivation_radio_ble.py'
        return [receiver.executable, '-I', str(script), '--packages', receiver.packages]
    # Decoder 113 is AmbientWeather WH31E/B. No broad/default decoder list,
    # implicit config, remote SDR, raw capture files, shell or network output.
    return [receiver.executable, '-c', '0', '-d', str(receiver.device_index),
            '-f', str(receiver.frequency), '-R', '0', '-R', '113', '-F', 'json', '-M', 'utc']

class NativeCapture:
    def __init__(self, receiver):
        self.receiver = receiver
        self.queue = Queue(maxsize=128)
        self.dropped = 0
        self.ready = False
        self.failed = False
        self.process = None
        self.job = None

    def start(self):
        env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH'}}
        self.process = subprocess.Popen(command(self.receiver), shell=False, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if os.name == 'nt':
            from .process_guard import KillOnCloseJob
            self.job = KillOnCloseJob(self.process)
        Thread(target=self._read, name='cultivation-radio-pipe', daemon=True).start()

    def _read(self):
        try:
            while self.process and self.process.stdout:
                data = self.process.stdout.readline(4097)
                if not data:
                    break
                if len(data) > 4096:
                    self.failed = True
                    break
                row = json.loads(data)
                now = datetime.now(timezone.utc)
                if self.receiver.kind == 'ble':
                    if row.get('type') == 'ready' and row.get('mode') == 'passive':
                        self.ready = True
                        continue
                    if row.get('type') == 'error':
                        self.failed = True
                        break
                    if row.get('type') != 'advertisement':
                        continue
                    try:
                        event = decode_bthome(row.get('address'), bytes.fromhex(row.get('data', '')), now,
                                              name=row.get('name', ''), rssi=row.get('rssi'))
                    except (ValueError, TypeError):
                        continue
                else:
                    try:
                        event = decode_wh31(row, now)
                    except RadioInputError:
                        continue
                    self.ready = True
                try:
                    self.queue.put_nowait(event)
                except Full:
                    self.dropped += 1
        except Exception:
            self.failed = True
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()

    def stop(self):
        if self.job:
            self.job.close()
            self.job = None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.process and self.process.stdout:
            self.process.stdout.close()

    def alive(self):
        return self.process is not None and self.process.poll() is None and not self.failed
