"""Run the loopback radio software chain; this is not physical RF acceptance."""
from pathlib import Path
import argparse
import json
import os
import socket
import signal
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]

def free(port):
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError('Owned test port already occupied')

def run(evidence):
    for port in (8019, 4191): free(port)
    parent = Path(evidence).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='radio-browser-', dir=parent))
    env = {k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA','COMSPEC','PATHEXT','NUMBER_OF_PROCESSORS','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMW6432'}}
    env.update(APP_ENV='test', DATABASE_URL='sqlite://', COMAN_DATABASE_URL='sqlite://', AI_ALLOW_CLOUD_FALLBACK='false',
               VITE_API_URL='', VITE_SUPABASE_URL='', VITE_SUPABASE_PUBLISHABLE_KEY='', VITE_SUPABASE_ANON_KEY='')
    children, handles, jobs = [], [], []
    result = {'status':'FAILED', 'physical_sensor_used':False, 'evidence':str(directory)}
    def launch(args, name, cwd=ROOT):
        out = (directory/(name+'.log')).open('w',encoding='utf-8'); handles.append(out)
        p = subprocess.Popen(args, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
        children.append(p)
        if os.name == 'nt':
            sys.path.insert(0, str(ROOT))
            os.environ.update(APP_ENV='test',DATABASE_URL='sqlite://',COMAN_DATABASE_URL='sqlite://')
            from modules.cultivation.radio.process_guard import KillOnCloseJob
            jobs.append(KillOnCloseJob(p))
        return p
    def ready(url, p):
        for _ in range(60):
            if p.poll() is not None: raise RuntimeError('Owned fixture process exited')
            try:
                with urlopen(url,timeout=1) as response:
                    if response.status == 200:return
            except Exception: pass
            time.sleep(.5)
        raise RuntimeError('Owned fixture readiness timed out')
    try:
        server = launch([sys.executable,str(ROOT/'scripts/acceptance/cultivation_radio_server.py'), '--allow-synthetic-loopback','--directory',str(directory)],'api')
        ready('http://127.0.0.1:8019/fixture', server)
        command = ['pnpm.cmd' if os.name == 'nt' else 'pnpm','exec','vite','--config','e2e/fixtures/cultivation-radio.config.ts','--configLoader','runner']
        vite = launch(command,'vite',ROOT/'frontend')
        ready('http://127.0.0.1:4191/e2e/fixtures/cultivation-radio.html', vite)
        command = ['pnpm.cmd' if os.name == 'nt' else 'pnpm','exec','playwright','test','e2e/cultivation-radio.spec.ts','--config','playwright.config.ts','--output',str(directory/'browser')]
        with (directory/'playwright.log').open('w',encoding='utf-8') as output:
            test = subprocess.run(command,cwd=ROOT/'frontend',env=env,stdout=output,stderr=subprocess.STDOUT,timeout=240)
        result.update(status='PASSED' if test.returncode==0 else 'FAILED',exit_code=test.returncode)
    except Exception as error:
        result['error_type'] = type(error).__name__
    finally:
        for job in reversed(jobs): job.close()
        for p in reversed(children):
            if os.name != 'nt':
                try: os.killpg(p.pid, signal.SIGTERM)
                except ProcessLookupError: pass
            if p.poll() is None:p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
        for handle in handles:handle.close()
        result['cleanup']={}
        # Closing the job terminates grandchildren asynchronously. Observe exit
        # before judging cleanup, never kill an unrelated port owner.
        deadline = time.monotonic() + 6
        while True:
            for port in (8019,4191):
                with socket.socket() as sock:
                    result['cleanup'][str(port)] = sock.connect_ex(('127.0.0.1',port)) != 0
            if all(result['cleanup'].values()) or time.monotonic() >= deadline:
                break
            time.sleep(.1)
        if not all(result['cleanup'].values()):result['status']='FAILED'
        (directory/'receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
    return 0 if result['status']=='PASSED' else 1

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--evidence-root',required=True)
    sys.exit(run(parser.parse_args().evidence_root))
