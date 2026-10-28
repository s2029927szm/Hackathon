"""Build a portable Windows x64 package that bundles the Python runtime and all dependencies.

Run with the project virtual environment so the tested dependency versions are bundled:
    .venv\\Scripts\\python package_windows_portable.py
"""
from pathlib import Path
import importlib.metadata
import os
import shutil
import subprocess
import sys
import zipfile

root = Path(__file__).resolve().parent
base = Path(sys.base_prefix)
assert sys.prefix != sys.base_prefix, 'Run with .venv\\Scripts\\python'
out = root / 'dist'
stage = out / 'FoodCompass'
archive = out / 'FoodCompass-Windows-Portable.zip'
tag = f'{sys.version_info.major}{sys.version_info.minor}'
if stage.exists():
    shutil.rmtree(stage)
runtime = stage / 'python'
runtime.mkdir(parents=True)

# CPython runtime (python.org build) without tests, Tk/IDLE, headers, docs or the base site-packages.
for name in ['python.exe', 'pythonw.exe', 'python3.dll', f'python{tag}.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt']:
    shutil.copy2(base / name, runtime / name)
shutil.copytree(base / 'DLLs', runtime / 'DLLs',
                ignore=lambda d, names: [n for n in names if n.startswith(('_test', '_ctypes_test', '_tkinter', 'tcl', 'tk'))])
def stdlib_ignore(directory, names):
    skipped = {'__pycache__'}
    if Path(directory) == base / 'Lib':
        skipped |= {'site-packages', 'test', 'idlelib', 'tkinter', 'turtledemo'}
    return [n for n in names if n in skipped]
shutil.copytree(base / 'Lib', runtime / 'Lib', ignore=stdlib_ignore)
shutil.copytree(Path(sys.prefix) / 'Lib' / 'site-packages', runtime / 'Lib' / 'site-packages',
                ignore=shutil.ignore_patterns('__pycache__'))
# The ._pth file isolates the runtime from any Python on the target PC and puts the project root on sys.path.
(runtime / f'python{tag}._pth').write_text('Lib\nDLLs\nLib\\site-packages\n..\nimport site\n', encoding='ascii')

# Project files (FoodPic/ source photos are already copied into FoodCompass-Web/assets/dishes).
files = ['app(1).py', 'dishes_50.json', 'index(1).html', 'monitor(1).html', 'Original.png', 'Dynamic.png',
         'generate_dishes.py', 'verify_integration.py', 'verify_frontend.cjs', 'verify_monitor.cjs',
         'monitor-test-state.json', 'apollo_gemma.py', 'run_apollo_gemma.ps1', 'reset-monitor.ps1',
         'requirements.txt', 'requirements-dev.txt', 'README-integration.md', 'AGENTS.md']
for name in files:
    shutil.copy2(root / name, stage / name)
shutil.copytree(root / 'FoodCompass-Web', stage / 'FoodCompass-Web', ignore=shutil.ignore_patterns('__pycache__'))
versions = sorted(f'{d.metadata["Name"]}=={d.version}' for d in importlib.metadata.distributions())
(stage / 'requirements-lock.txt').write_text('\n'.join(versions) + '\n', encoding='utf-8')
for path in (root / 'windows').iterdir():
    if not path.is_file():
        continue
    data = path.read_bytes()
    if path.suffix in {'.cmd', '.txt', '.ini'}:
        data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        if path.suffix != '.cmd' and not data.startswith(b'\xef\xbb\xbf'):
            data = b'\xef\xbb\xbf' + data  # BOM so older Notepad detects UTF-8
    (stage / path.name).write_bytes(data)

python = runtime / 'python.exe'
compiled = subprocess.run([str(python), '-m', 'compileall', '-q', '-j', '0', '--invalidation-mode', 'checked-hash',
                           str(runtime / 'Lib')], capture_output=True, text=True)
if compiled.returncode:
    print('compileall warnings:', compiled.stdout[-2000:], compiled.stderr[-2000:])
# Import the app with a hostile environment: no Python on PATH, bogus PYTHONHOME/PYTHONPATH.
env = {'SYSTEMROOT': os.environ['SYSTEMROOT'], 'PATH': os.environ['SYSTEMROOT'] + r'\System32',
       'PYTHONHOME': r'C:\missing', 'PYTHONPATH': r'C:\missing'}
probe = subprocess.run([str(python), '-X', 'utf8', '-c',
                        'import importlib, sys; app = importlib.import_module("app(1)"); '
                        'print(sys.prefix, len(app.ALL_DISHES), [p for p in sys.path if "Python312" in p])'],
                       cwd=stage, env=env, capture_output=True, text=True)
assert probe.returncode == 0, probe.stderr
print('Runtime probe:', probe.stdout.strip())
shutil.rmtree(stage / '__pycache__', ignore_errors=True)

stored = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.whl', '.zip'}
paths = sorted(p for p in stage.rglob('*') if p.is_file())
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for path in paths:
        z.write(path, path.relative_to(out).as_posix(),
                zipfile.ZIP_STORED if path.suffix.lower() in stored else zipfile.ZIP_DEFLATED)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
longest = max(len(p.relative_to(out).as_posix()) for p in paths)
print(f'Created {archive}: {archive.stat().st_size / 2**20:.1f} MB, {len(paths)} files; '
      f'longest path inside ZIP {longest} chars; CRC verified.')
