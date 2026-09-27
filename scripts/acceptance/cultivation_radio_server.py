"""Opt-in loopback test receiver. Never imported by the application runtime."""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Full
from threading import Event, Thread
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]

def main(directory):
    directory = Path(directory).resolve()
    if not directory.is_dir() or not directory.name.startswith('radio-browser-'):
        raise SystemExit('Isolated radio test directory required')
    os.environ.update(APP_ENV='development', DATABASE_URL='sqlite:///' + (directory/'central.db').as_posix(),
        COMAN_DATABASE_URL='sqlite:///' + (directory/'central.db').as_posix(),
        CULTIVATION_EDGE_PATH=str(directory/'edge.db'), AI_ALLOW_CLOUD_FALLBACK='false',
        SANDBOX_STARTUP_SEED_ENABLED='false', SUPABASE_URL='', SUPABASE_JWT_SECRET='',
        SUPABASE_SERVICE_ROLE_KEY='', CULTIVATION_RADIO_CONFIG='')
    sys.path.insert(0, str(ROOT))
    from cultivation_intelligence_browser import configure, seed
    configure()
    from sqlalchemy import create_engine
    from modules.coman.models import Base
    from backend.app.database import get_engine
    from modules.cultivation.radio.codecs import decode_bthome
    from modules.cultivation.radio.config import Receiver, RadioConfig
    from modules.cultivation.radio.runtime import RadioRuntime
    from modules.cultivation.gateway import configured_edge
    from backend.app.routers import cultivation_radio
    from backend.app.routers.cultivation_intelligence_workspace import router as workspace
    from fastapi import FastAPI
    import uvicorn
    engine = get_engine()
    # Exercise the actual additive migration chain, including permission tables.
    # Import order must not define the authorization schema of this fixture.
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(ROOT / 'alembic.ini'))
    cfg.set_main_option('script_location', str(ROOT / 'migrations'))
    command.upgrade(cfg, 'head')
    seed(directory)
    scope = json.loads((directory/'scope.json').read_text())
    fake = directory/'receiver'
    fake.write_bytes(b'not executable; in-process test capture only')
    packages = directory/'packages'
    (packages/'bleak').mkdir(parents=True)
    (packages/'bleak'/'__init__.py').write_text('')
    receiver = Receiver('ble','ble','2.4 GHz Bluetooth LE',str(fake),hashlib.sha256(fake.read_bytes()).hexdigest(),str(packages))
    class Capture:
        def __init__(self, _receiver):
            self.queue, self.stopped, self.ready = Queue(maxsize=128), Event(), True
        def start(self):
            def emit():
                while not self.stopped.wait(.5):
                    for address, data, name in [('AABBCCDDEEFF','4002C40903BF13','Synthetic canopy sensor'),
                                                ('112233445566','41AABB','Encrypted fixture')]:
                        try:
                            self.queue.put_nowait(decode_bthome(address, bytes.fromhex(data), datetime.now(timezone.utc), name=name, rssi=-51))
                        except Full:
                            pass
            Thread(target=emit, daemon=True).start()
        def stop(self): self.stopped.set()
        def alive(self): return not self.stopped.is_set()
    runtime = RadioRuntime(engine, RadioConfig(scope['organization_id'],scope['facility_id'],(receiver,),5), capture_factory=Capture, edge_factory=configured_edge)
    cultivation_radio.get_radio_runtime = lambda: runtime
    @asynccontextmanager
    async def lifespan(_):
        runtime.start()
        try: yield
        finally: await asyncio.to_thread(runtime.stop)
    app = FastAPI(lifespan=lifespan)
    app.include_router(cultivation_radio.router, prefix='/api/v1')
    app.include_router(workspace, prefix='/api/v1')
    @app.get('/fixture')
    def fixture(): return scope
    uvicorn.run(app, host='127.0.0.1', port=8019, access_log=False)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-synthetic-loopback', action='store_true', required=True)
    parser.add_argument('--directory', required=True)
    arguments = parser.parse_args()
    main(arguments.directory)
