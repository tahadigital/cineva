"""App-owned service exits even if its owner is abruptly terminated."""
import json, os, socket, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]

class AppLifetimeTests(unittest.TestCase):
    def test_server_exits_when_owner_dies(self):
        with tempfile.TemporaryDirectory(prefix='mavie-lifetime-') as tmp:
            with socket.socket() as s:
                s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
            env = {**os.environ, 'MAVIE_DATA_DIR': tmp}
            code = "import os,subprocess,sys,time; subprocess.Popen([sys.executable,sys.argv[1],'--host','127.0.0.1','--port',sys.argv[2],'--parent-pid',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(90)"
            owner = subprocess.Popen([sys.executable, '-c', code, str(ROOT/'server.py'), str(port)], env=env)
            server_pid = None
            try:
                for _ in range(100):
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=.2) as r:
                            self.assertEqual(json.load(r)['app'], 'mavie')
                        server_pid = int((Path(tmp)/'server.pid').read_text()); break
                    except (OSError, ValueError): time.sleep(.05)
                else: self.fail('Test service did not start')
                owner.kill(); owner.wait(timeout=3)
                for _ in range(100):
                    if not (Path(tmp)/'server.pid').exists(): break
                    time.sleep(.05)
                self.assertFalse((Path(tmp)/'server.pid').exists(), 'App-owned server did not clean up its PID file')
                with self.assertRaises(OSError): urlopen(f'http://127.0.0.1:{port}/api/health', timeout=.3)
            finally:
                if owner.poll() is None: owner.kill(); owner.wait(timeout=3)
                if server_pid and (Path(tmp)/'server.pid').exists():
                    try: os.kill(server_pid, 15)
                    except ProcessLookupError: pass

if __name__ == '__main__': unittest.main()
