FoodCompass Windows 便携版（免安装）

【使用】
1. 把 ZIP 完整解压到任意可写文件夹（不要在压缩包里直接双击）。路径尽量短，例如 D:\FoodCompass。
2. 双击 Start-FoodCompass.cmd，出现网址后自动打开浏览器：
     主页        http://127.0.0.1:8001/
     监控看板    http://127.0.0.1:8001/monitor
     旧版客户端  http://127.0.0.1:8001/legacy
3. 使用期间保持黑色窗口打开；关闭窗口或按 Ctrl+C 即停止服务。

无需安装 Python 或任何依赖：python\ 文件夹已包含 Python 3.12.7（64 位）及 FastAPI、Uvicorn、OpenAI 等全部依赖，
且与目标电脑上已安装的 Python 环境相互隔离。系统要求：Windows 10 / 11 64 位。

【配置】用记事本编辑 foodcompass.ini，保存后重新启动：
- port：端口被占用时改为其他端口，例如 8002。
- host：改为 0.0.0.0 可让同一局域网的设备访问（首次会弹出防火墙提示，需要允许）。
- base_url / model_id：OpenAI 兼容模型接口，默认 http://localhost:11434/v1 与 gemma4:31b。
启动窗口会显示模型能否连接。连不上时页面仍可完整使用，但推荐来自启发式回退，不是真实模型推理。
原电脑通过 SSH 隧道连接模型；隧道不会随包复制，需要在新电脑上重新建立，或把 base_url 改为可访问的模型服务。

【其他】
- Reset-Monitor.cmd：服务运行时重置监控看板。
- Self-Check.cmd：离线运行接口回归测试（不调用模型），显示 PASS 即环境正常。
- 监控页与旧版客户端的样式从网络加载 Tailwind CDN，离线时排版会缺失；主页完全本地运行。
- 纯前端演示无需启动服务：直接打开 FoodCompass-Web\index.html。
- 若出现"无法验证发布者"安全提示，选择"运行"；也可在解压前右键 ZIP → 属性 → 勾选"解除锁定"。
- 多人、餐厅、距离等为演示数据，详见 README-integration.md。开发者可用 python\python.exe 运行项目脚本。

Quick start (English): extract the whole ZIP, double-click Start-FoodCompass.cmd and keep the window open.
The browser opens http://127.0.0.1:8001/ (monitor: /monitor). Port and model settings are in foodcompass.ini.
No Python installation is needed. Requires Windows 10/11 x64.
