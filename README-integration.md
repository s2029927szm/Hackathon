# Food Compass 前后端对接

在仓库根目录 PowerShell 运行：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn "app(1):app" --host 127.0.0.1 --port 8001
```

打开 http://127.0.0.1:8001/ 。首页使用 FoodCompass-Web 的设计，静态资源与 API 同源。
监控页：/monitor；原后端客户端：/legacy；纯本地前端演示：/?demo。
双击 HTML 仍使用本地演示；单独使用 http.server 时请加 ?demo。

## 操作流程

1. 完成语言、忌口、口味与目标选择，点击 Let’s explore，调用 step1-probe。
2. 对返回的探针卡逐张 Like/Pass。可 Undo，也可重新滑同一道菜更新选择。
3. 所有探针均选择后，点击 Get expert ranking，调用 step2-finalize-and-rank。
4. 结果按后端共识分数排列，保留预算等筛选，并排除后端标记违反忌口的菜品。
5. 修改个人偏好后点击 Restart；提交排名时也会检查偏好是否变化。
6. 错误显示在页面上，可重试；刷新页面需要重新生成探针。收藏的后端菜品从 /api/dishes 恢复。

模型默认地址 http://localhost:11434/v1，模型 gemma4:31b。可在启动前设置
OPENAI_BASE_URL、MODEL_ID、MODEL_TIMEOUT（秒，默认 120）。关闭 SDK 自动重试，避免失败时重复等待。
模型不可用时沿用原后端启发式探针与确定性评分回退，不能视为真实模型推理。
一次完整流程最多调用模型八次，可能等待数分钟。

## 数据与范围

- 后端以 dishes_50.json 为准。新增 backend.js 在 app.js、enhancements.js 之后加载。
- 后端没有菜品照片、餐厅、完整碳水/脂肪数据：统一示意图、示例数据说明及缺失值标记；距离沿用后端模拟值。
- 探针可能故意包含忌口食材；界面提示这一行为。最终列表按已标记忌口过滤。
- 食材字符串匹配不构成完整过敏原数据库。多人、聊天、餐厅转盘、日记及健身功能保持原演示范围。
- 新前端通过 session_id 隔离推荐会话；旧客户端兼容 current 会话。
- 监控页仍为原型全局共享看板，仅适合单人演示；Undo 的实时历史可能保留旧事件。
- 会话存于内存，服务重启失效；不适合多进程或生产多人部署。

## 验证

语法检查：node --check FoodCompass-Web/app.js、enhancements.js、backend.js；
python -m py_compile "app(1).py" generate_dishes.py。
接口回归脚本：.venv\Scripts\python verify_integration.py（模型调用被替换为立即失败，专门检查原回退路径，不调用真实模型）。
浏览器人工验收请用 /?qa，覆盖说明文档的引导、弹窗、滑卡/Undo、转盘、响应式布局，再单独检查无 qa 时的收藏持久化。

回归脚本另需安装开发依赖：.venv\Scripts\python -m pip install -r requirements-dev.txt。
实际浏览器检查发现并修正 Windows GBK 控制台打印 emoji 导致回退接口报 500 的问题。

浏览器实际验证：引导到探针卡、Like 计数与 Undo 恢复通过。完整 API 回退路径检查通过；真实模型服务当前未连接。


浏览器端完整流程也已完成：五张探针 Like/Undo 后提交，成功显示 50 道 Expert picks，共识分数排序；页面截图 integration-preview.png。浏览器未捕获到控制台 error。真实服务不可用，此次使用后端回退评分。

2026-10-28 新版转盘重新对接：加载顺序 app.js → enhancements.js → solo-fix.js → backend.js。
后端模式下单人转盘使用符合忌口及当前筛选的排名前六道菜；不足六道的空扇区不可选。
尚未生成排名或个人偏好已变化时，不抽取旧结果，请先完成探针并生成排名。
纯演示（?demo 或 file://）保留原六道示例菜，图片及多人功能仍为演示。
新增前端契约检查：node verify_frontend.cjs。

菜品图片映射：在 app(1).py 的 DISH_IMAGE_GROUPS 按菜名维护，目录、探针、排名 API 均包含 image、image_url、image_kind、image_note。
前端卡片、详情与转盘读取后端 image。现有同类图片仅为示意图，缺少合适资源的菜使用 dish-placeholder.svg；不再统一使用 tofu.jpg。
修改后需重启 FastAPI，并刷新浏览器；重启会清除内存会话，需要重新生成推荐。

界面以 FoodCompass-Web 原设计为准：移除适配层新增的 Backend recommendations 面板及自定义 Expert picks 结果页。
使用原 Let’s explore 提交偏好，使用原 View picks 提交探针选择或查看结果；结果页保留原排序和收藏操作。
监控仍可直接访问 /monitor。菜品数据来自后端，因此菜名、价格和图片不保证与原本地演示样例一致。

监控页视觉更新：monitor(1).html 使用白底、高对比度深色文字、低饱和度状态配色及统一圆角线条 SVG 图标。
Original.png / Dynamic.png 位于仓库根目录，分别用于基础画像、动态画像及融合节点；新增两条图片资源路由。
/monitor 与 /monitor.html 均显示同一监控页。后台固定探针标签和字幕改为英文，模型响应文案要求英文；兼容历史中英双语标签。
保持 /api/monitor-state 结构、600ms 轮询、状态机、评分公式和融合/分发动画触发条件不变。
验证：node verify_monitor.cjs（monitor-test-state.json 为测试数据）；API 回归、桌面及 390px 窄屏检查通过。
monitor-preview.png 是完成状态的测试数据排版预览，不代表当前真实模型结果。

实时监控联动修复：新版前端补齐原 index(1).html 的 page_step / price_slider 事件。
- Meet Pico 开始新流程时重置看板；各 Continue 依次同步页面号、忌口、菜系和目标。
- 开始探针时仅重置推断与评分状态，保留已经提交的基础轨道；再发送完整基础画像。
- Like/Pass 和 Undo 使用 swipe_snapshot 同步完整的当前选择，不累计重复或已撤销的历史。
- 请求专家排名前等待已有同步事件完成；结果页、转盘和应用筛选后同步价格范围与实际显示数量。
- monitor 对 pending / 空列表也重新渲染，清理旧探针、滑卡、推断、融合及排名内容。
- 保留旧客户端 single_swipe 接口，新增事件不改变评分逻辑或模型调用过程。
node verify_frontend.cjs、node verify_monitor.cjs、verify_integration.py 均通过；浏览器实际操作 Continue 确认节点和字幕实时变化。
看板仍沿用原全局单演示状态；使用一个 index 操作窗口配合 monitor 展示，多个 index 操作窗口会共同更新同一看板。

2026-10-28 FoodPic 图片已全部绑定：50 个编号及完整菜名校验一致，副本位于 FoodCompass-Web/assets/dishes，映射见同目录 manifest.json。bind_foodpic.py 可在更新源图片后重新绑定。所有 50 个静态图片 URL 及探针、排名响应检查通过。


监控页演示节奏与文案更新：
- 初始各区域白底，偏好、探针、反馈、推断结果、排名和筛选计数均无预填数据；由当前演示操作填充。
- 基础画像、推断画像、画像融合、专家评估及排名分别激活柔和的绿、紫、粉紫、杏色及蓝色动态背景；整体背景随流程激活浅色渐变。
- 看板首次观察到当前 run_id 的融合完成后，播放 1.2 秒融合动画；随后合并画像持续彩色边框动画，保留 10 秒，再展示分发动画；1.4 秒分发后展示最新专家和排名状态。
- 此节奏只作用于监控展示，不延迟实际模型评分；后台已提前完成的状态会在演示门控结束后显示。减少动态效果的系统设置会关闭动画，保留状态颜色和展示顺序。
- 新演示 run_id / 重置会清空门控计时和阶段高亮，避免新旧会话串用。
- 文案改用 Declared / Inferred Preference Profile、Profile Fusion、Specialist Reviewers、Consensus Ranking；页面号和 Prompt 编号退出主要标题，活动条改为 Current Activity。
- monitor-initial-preview.png 为初始状态；monitor-fusion-hold-preview.png、monitor-stages-preview.png 使用测试数据展示融合和完成布局，不代表实际模型结果。
验证：verify_monitor.cjs 覆盖 1199/1200/11199/11200/12599/12600 毫秒边界及重置；前端契约、API 回归通过；浏览器确认初始全白、持续边框动画、分发门控和窄屏无溢出。
