"""Start the exam's loopback-only, no-login JupyterLab entry point."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
BASE_URL = 'http://127.0.0.1:8889/'
EXAM_URL = BASE_URL + 'lab/tree/' + urllib.parse.quote('practical/实操填空模拟考试.ipynb')
NOTEBOOK = ROOT / '实操填空模拟考试.ipynb'

def available():
    path = 'api/contents/' + urllib.parse.quote('practical/实操填空模拟考试.ipynb') + '?content=0'
    try:
        # This request deliberately sends no token, password, or cookies.
        with urllib.request.urlopen(BASE_URL + path, timeout=1) as response:
            data = json.load(response)
            return data.get('name') == '实操填空模拟考试.ipynb' and data.get('type') == 'notebook'
    except (urllib.error.URLError, OSError, ValueError):
        return False

def start():
    if available():
        return
    runtime = ROOT / '.jupyter-runtime'
    runtime.mkdir(exist_ok=True, mode=0o700)
    data_dir = runtime / 'data'
    config_dir = runtime / 'config'
    data_dir.mkdir(exist_ok=True, mode=0o700)
    config_dir.mkdir(exist_ok=True, mode=0o700)
    env = dict(os.environ)
    env['JUPYTER_RUNTIME_DIR'] = str(runtime)
    env['JUPYTER_DATA_DIR'] = str(data_dir)
    env['JUPYTER_CONFIG_DIR'] = str(config_dir)
    env['PYTHON_PRACTICAL_EXAM_DIR'] = str(ROOT)
    # Trust the delivered Notebook in the same private Jupyter data directory.
    # A failed trust command must not prevent the local exam server from starting.
    try:
        subprocess.run([sys.executable, '-m', 'jupyter', 'trust', str(NOTEBOOK)],
                       env=env, cwd=PROJECT_ROOT, check=False, timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass
    args = [sys.executable, '-m', 'jupyterlab',
            '--ServerApp.ip=127.0.0.1', '--ServerApp.port=8889', '--ServerApp.port_retries=0',
            '--ServerApp.root_dir=' + str(PROJECT_ROOT), '--ServerApp.open_browser=False',
            '--ServerApp.allow_remote_access=False', '--IdentityProvider.token=',
            '--PasswordIdentityProvider.hashed_password=',
            '--PasswordIdentityProvider.password_required=False',
            "--ServerApp.jpserver_extensions={'jupyter_ai':False}"]
    with (runtime / 'jupyter-exam.log').open('ab') as log:
        proc = subprocess.Popen(args, cwd=PROJECT_ROOT, env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=log, start_new_session=True)
    for _ in range(60):
        if available():
            return
        if proc.poll() is not None:
            raise RuntimeError('考试入口启动失败。请查看同目录 jupyter-exam.log；8889 端口可能已被占用。')
        time.sleep(0.25)
    raise RuntimeError('考试入口尚未启动完成，请查看同目录 jupyter-exam.log。')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    options = parser.parse_args()
    start()
    print('考试入口已就绪（仅本机，免密码和 token）：' + EXAM_URL)
    if not options.no_browser:
        subprocess.run(['open', EXAM_URL], check=True)
