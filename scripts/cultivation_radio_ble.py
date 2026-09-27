"""Standalone passive Windows receiver. No GATT, scan requests or equipment control."""
import argparse
import asyncio
import json
from pathlib import Path
import signal
import sys
import time

UUID = '0000fcd2-0000-1000-8000-00805f9b34fb'

def emit(value):
    print(json.dumps(value, separators=(',', ':')), flush=True)

async def main(packages):
    if sys.platform != 'win32':
        emit({'type': 'error', 'code': 'passive_backend_not_verified'})
        return 2
    path = Path(packages)
    if not path.is_absolute() or not (path / 'bleak' / '__init__.py').is_file():
        emit({'type': 'error', 'code': 'bluetooth_runtime_missing'})
        return 2
    sys.path.insert(0, str(path))
    try:
        from bleak import BleakScanner
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for kind in (signal.SIGINT, signal.SIGTERM):
            signal.signal(kind, lambda *_: loop.call_soon_threadsafe(stop.set))
        interval = 0
        count = 0
        def received(device, advertisement):
            nonlocal interval, count
            payload = advertisement.service_data.get(UUID)
            if payload is None or not 1 <= len(payload) <= 128:
                return
            current = int(time.monotonic())
            if interval != current:
                interval, count = current, 0
            count += 1
            if count > 100:
                return
            address = str(device.address).replace(':', '').upper()
            if len(address) != 12 or any(c not in '0123456789ABCDEF' for c in address):
                return
            emit({'type': 'advertisement', 'address': address, 'data': bytes(payload).hex(),
                  'name': str(advertisement.local_name or '')[:64], 'rssi': advertisement.rssi})
        scanner = BleakScanner(received, service_uuids=[UUID], scanning_mode='passive')
        await scanner.start()
        emit({'type': 'ready', 'mode': 'passive', 'profile': 'bthome_v2'})
        try:
            await stop.wait()
        finally:
            await scanner.stop()
        return 0
    except Exception:
        emit({'type': 'error', 'code': 'receiver_unavailable'})
        return 2

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--packages', required=True)
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(main(args.packages)))
    except (KeyboardInterrupt, BrokenPipeError):
        pass
