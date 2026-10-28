"""Build a relocatable source distribution without machine-local environments."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import zipfile

root = Path(__file__).resolve().parent
out = root / 'dist'
out.mkdir(exist_ok=True)
archive = out / 'FoodCompass-Windows.zip'
launcher = r'''@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto run
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if errorlevel 1 goto failed
:run
.venv\Scripts\python.exe -m pip --version >nul 2>nul
if errorlevel 1 .venv\Scripts\python.exe -m ensurepip --upgrade
if errorlevel 1 goto failed
if exist .venv\foodcompass-installed goto serve
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
echo installed>.venv\foodcompass-installed
:serve
set PYTHONUTF8=1
if not defined FOODCOMPASS_PORT set FOODCOMPASS_PORT=8001
echo Open http://127.0.0.1:%FOODCOMPASS_PORT%/ in your browser.
echo Press Ctrl+C to stop the server.
.venv\Scripts\python.exe -m uvicorn "app(1):app" --host 127.0.0.1 --port %FOODCOMPASS_PORT%
if errorlevel 1 goto failed
exit /b 0
:failed
echo Setup or startup failed. Check Python installation, network and port availability.
pause
exit /b 1
'''
readme = '''Food Compass Windows 工程移植包

1. 将整个 ZIP 解压到可写文件夹（不要在压缩包内直接运行）。
2. 安装 Windows 版 Python 3.12（64 位），安装时勾选 Add Python to PATH。
3. 双击 start-windows.cmd。首次运行需要联网，自动创建本机 .venv 并安装锁定版本依赖。
4. 出现 Uvicorn running 后，浏览器打开 http://127.0.0.1:8001/ 。按 Ctrl+C 停止服务。
5. 纯前端离线演示可直接打开 FoodCompass-Web/index.html。

这是源码工程包，不是免安装 EXE；不含 Python 解释器、模型权重及离线依赖安装包。
请勿从原电脑拷贝 .venv；启动脚本会在目标电脑重新建立。

模型默认 localhost:11434/v1，模型名 gemma4:31b。
如模型运行在另一台电脑，可在命令提示符中先设置：
  set OPENAI_BASE_URL=http://模型电脑地址:11434/v1
  set MODEL_ID=gemma4:31b
  start-windows.cmd
原电脑的 SSH 隧道不会随工程复制，需要在目标电脑重新配置。
模型不可用时使用启发式回退，不能当作真实模型推理。
端口冲突时设置 FOODCOMPASS_PORT 为其他端口，例如 8002。

多人为本机模拟；图像、餐厅、距离和营养数据的限制见 README-integration.md。
个人浏览器的收藏与偏好不包含在包中。监控页为共享演示看板。
详细接口和验证说明见 README-integration.md。
'''
files = ['app(1).py','dishes_50.json','generate_dishes.py','index(1).html','monitor(1).html','Original.png','Dynamic.png',
         'requirements.txt','requirements-dev.txt','verify_integration.py','README-integration.md','AGENTS.md']
entries = {name:(root/name).read_bytes() for name in files}
for path in (root/'FoodCompass-Web').rglob('*'):
    if path.is_file() and '__pycache__' not in path.parts:
        entries[path.relative_to(root).as_posix()] = path.read_bytes()
# Lock to the versions exercised by the integration regression run.
versions = sorted(f'{d.metadata["Name"]}=={d.version}' for d in importlib.metadata.distributions())
entries['requirements-lock.txt'] = ('\n'.join(versions)+'\n').encode()
entries['start-windows.cmd'] = launcher.replace('\n','\r\n').encode('ascii')
entries['Windows移植说明.txt'] = readme.encode('utf-8-sig')
manifest = {name:hashlib.sha256(data).hexdigest() for name,data in entries.items()}
entries['SHA256-MANIFEST.json'] = json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name,data in entries.items():
        z.writestr('FoodCompass-Windows/'+name,data)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,digest in manifest.items():
        assert hashlib.sha256(z.read('FoodCompass-Windows/'+name)).hexdigest()==digest
print(f'Created {archive}: {archive.stat().st_size:,} bytes; {len(entries)} files; CRC and SHA256 verified.')
