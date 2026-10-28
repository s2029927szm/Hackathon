"""Portable Windows launcher: reads foodcompass.ini, starts the FastAPI server and opens the browser."""
import configparser
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'app(1).py').is_file():  # allow running from the repository's windows/ folder
    ROOT = ROOT.parent
DEFAULTS = {
    'server': {'host': '127.0.0.1', 'port': '8001', 'open_browser': 'yes'},
    'model': {'base_url': 'http://localhost:11434/v1', 'model_id': 'gemma4:31b', 'timeout': '120'},
}


def load_config():
    config = configparser.ConfigParser()
    config.read_dict(DEFAULTS)
    path = ROOT / 'foodcompass.ini'
    if path.is_file():
        raw = path.read_bytes()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:  # saved as ANSI by an older Notepad
            text = raw.decode('mbcs', errors='replace')
        config.read_string(text, source=str(path))
    return config


def setting(config, section, key, env=None):
    # foodcompass.ini wins; an empty value falls back to the environment, then the default.
    value = config.get(section, key, fallback='').strip()
    if not value and env:
        value = os.environ.get(env, '').strip()
    return value or DEFAULTS[section][key]


def local_url(host, port):
    shown = '127.0.0.1' if host in ('', '0.0.0.0', '::') else host
    return f'http://{shown}:{port}'


def is_foodcompass(url):
    try:
        response = httpx.get(url + '/api/monitor-state', timeout=2, trust_env=False)
        return response.status_code == 200 and 'left_track' in response.json()
    except Exception:
        return False


def port_in_use(url, port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex((httpx.URL(url).host, port)) == 0


def lan_addresses():
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    return sorted({info[4][0] for info in infos} - {'127.0.0.1'})


def check_model(base_url, model_id):
    try:
        response = httpx.get(base_url.rstrip('/') + '/models', timeout=3)
        response.raise_for_status()
        ids = [item.get('id') for item in response.json().get('data', [])]
    except Exception as exc:
        print(f'[model] Not reachable at {base_url} ({exc.__class__.__name__}). The app still works, but '
              'recommendations use the heuristic fallback, not real model inference.', flush=True)
        return
    if model_id in ids:
        print(f'[model] Connected: {model_id} at {base_url}', flush=True)
    else:
        print(f'[model] {base_url} is reachable, but {model_id} is not listed '
              f'(available: {", ".join(map(str, ids[:5])) or "none"}). Check model_id in foodcompass.ini.', flush=True)


def open_when_ready(url):
    for _ in range(120):
        if is_foodcompass(url):
            webbrowser.open(url + '/')
            return
        time.sleep(0.5)


def serve(config):
    host = setting(config, 'server', 'host')
    port = int(setting(config, 'server', 'port', 'FOODCOMPASS_PORT'))
    base_url = setting(config, 'model', 'base_url', 'OPENAI_BASE_URL')
    model_id = setting(config, 'model', 'model_id', 'MODEL_ID')
    os.environ.update(OPENAI_BASE_URL=base_url, MODEL_ID=model_id,
                      MODEL_TIMEOUT=setting(config, 'model', 'timeout', 'MODEL_TIMEOUT'))
    open_browser = config.getboolean('server', 'open_browser', fallback=True)
    url = local_url(host, port)
    if port_in_use(url, port):
        if is_foodcompass(url):
            print(f'FoodCompass is already running at {url}/')
            if open_browser:
                webbrowser.open(url + '/')
            return 0
        print(f'Port {port} is used by another program. Set "port" in foodcompass.ini to a free port, e.g. 8002.')
        return 1
    lines = [f'  App      {url}/', f'  Monitor  {url}/monitor', f'  Legacy   {url}/legacy']
    if host in ('0.0.0.0', '::'):
        lines += [f'  Network  http://{ip}:{port}/' for ip in lan_addresses()]
    print('=' * 64, ' FoodCompass portable - keep this window open while using it', *lines,
          ' Stop: close this window or press Ctrl+C. Settings: foodcompass.ini', '=' * 64, sep='\n', flush=True)
    threading.Thread(target=check_model, args=(base_url, model_id), daemon=True).start()
    if open_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))
    import uvicorn
    uvicorn.run('app(1):app', host=host, port=port)
    return 0


def reset(config):
    url = local_url(setting(config, 'server', 'host'), int(setting(config, 'server', 'port', 'FOODCOMPASS_PORT')))
    try:
        response = httpx.post(url + '/api/live-sync', json={'event_type': 'reset'}, timeout=5, trust_env=False)
        response.raise_for_status()
    except Exception as exc:
        print(f'Could not reset the monitor at {url} ({exc.__class__.__name__}). Start FoodCompass first.')
        return 1
    print('Monitor reset successfully.')
    return 0


def main():
    config = load_config()
    try:
        return reset(config) if sys.argv[1:] == ['reset'] else serve(config)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    sys.exit(main())
