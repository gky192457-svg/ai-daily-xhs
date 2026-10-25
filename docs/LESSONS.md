# 踩坑手册 · xhs-ai-daily（2026-10-25 汇总）

本项目全部已知坑与规避方法。**遇到任何异常，先查本文档再动手。**
分三类：A 渲染管线（Pillow）、B 发布链路（Playwright/小红书）、C 流程与数据。

---

## A. 渲染管线（render.py / Pillow）

| # | 坑 | 规避方法 |
| --- | --- | --- |
| A1 | `_vgrad_block` / `_grad_block` / `_rim` 收到浮点 box 坐标，`range(h)` 直接 TypeError | 所有块级函数入口 `x0,y0,x1,y1 = [int(round(v)) for v in box]`（已固化，勿删） |
| A2 | 直接 `ImageDraw` 画半透明填充/描边，最后 `img.convert("RGB")` 会**变实色**（alpha 丢失） | 一律先画到独立 `RGBA` 全透明层，再 `img.alpha_composite(lay)`；辅助函数 `_fill_alpha` / `_stroke` / `_hline_grad` 已封装 |
| A3 | RGBA 图上 `draw.text(fill=(r,g,b,a))` 的 alpha 分量同样会丢失，想要"淡色字"不能靠 alpha | 淡色直接用更暗的 RGB 实值（如钩子小字 `(210,216,238)`、50% 灰 `(130,132,154)`） |
| A4 | Consolas 无中文字形，中文用 `FM()` 出豆腐块 | 中文只走 `FS()`（Noto Sans SC）；`FM()` 仅限纯拉丁/数字。**复发案例**：内页页眉品牌名原用 `FM(18)`，换 6 字品牌名「零阶产品谱」后豆腐块暴露，已改 `FS(18,500)`。品牌名/任何中文一律先确认字体 |
| A5 | 色序 cycle 元素从 5 个改成 4 个后 `cycle[i % 5]` 越界 | 一律 `% len(cycle)` |
| A6 | `wrap_text` 按 `\n` 分段返回多行，取 `[:2]` 截断 | `cover_hook` 主动用 `\n` 精确断两行，不要依赖自动换行（否则 "-42%" 会孤行） |
| A7 | Noto Sans SC 是可变字体，需 `set_variation_by_axes([weight])` 才能换字重 | 统一走 `FS(size, weight)`，失败时已做 try 降级 |

## B. 发布链路（Playwright MCP → 小红书创作平台）

| # | 坑 | 规避方法 |
| --- | --- |
| B1 | `browser_run_code_unsafe` 的 `filename` 参数加载文件会 `SyntaxError: Unexpected token 'const'` | 必须用 `code` 参数，且传 `async (page) => { ... }` 包装形式 |
| B2 | 执行环境**没有 `require`**（`ReferenceError`），读不了 JSON/fs | 数据经 `page.goto('file:///<绝对路径>.json')` 后取 `document.body.innerText` 再 `JSON.parse`（publish_flow.js v2 已实现） |
| B3 | `getByText('上传图文').click()` 命中侧边栏同名隐藏元素，30s 超时（element outside viewport） | 用 `page.evaluate` 遍历所有匹配元素，取 `getBoundingClientRect()` 在视口内的那个 `.click()` |
| B4 | 发布按钮 `<xhs-publish-btn>` 是**封闭 shadow DOM**：`shadowRoot=null`、a11y 树查不到、`elementFromPoint` 只返回 host | 放弃 DOM 定位，用坐标点击 |
| B5 | 红钮坐标**不能目视估算**：曾误判在 x≈930/1315，实际中心 (742,955)（1440×1000 视口） | 用 PIL 扫描截图红色像素（`r>215, g<90, b<110`，限定 y>890 区域）算 bbox 中心；坐标随页面改版会变，改版后重新扫 |
| B6 | 鼠标滚轮对内部滚动容器（`.publish-page`）无效 | 内部容器滚动用 `e.scrollTop = e.scrollHeight`；本例中底部操作栏是 sticky，其实不滚也能点 |
| B7 | **必选「添加内容类型声明 → 笔记含AI合成内容」**，不选则发布按钮点了没反应（无任何报错提示） | 两步 evaluate：先点「添加内容类型声明」展开，再点「笔记含AI合成内容」选项 |
| B8 | 图片上传后需等待处理（约 5–6s）再填标题，否则 input 可能未就绪 | `setInputFiles` 后 `waitForTimeout(6000)` |
| B9 | `getByRole('textbox')` 有多个：标题是 `name='填写标题会有更多赞哦'`，正文是 `.nth(1)` | 分别定位，串行填写 |
| B10 | 点击后校验不能只看弹窗文本（"发布成功"在 shadow 里，`body.innerText` 抓不到） | 以 `page.url().includes('published=true')` 为唯一成功判据 |

## C. 流程与数据

| # | 坑 | 规避方法 |
| --- | --- | --- |
| C1 | JSON schema 演进（新增 `cover_hook`、`title`）后，旧文件缺字段 | render.py 内有 fallback（无 cover_hook 取首条 headline 截断；无 title 取 takeaways[0] 截 18 字）；模板 `samples/2026-10-25.json` 已含全部字段 |
| C2 | caption 暴露自动化工具名（「每天 8:00 用 WorkBuddy 自动整理」） | 自动化 STEP4 硬性禁止；结尾固定「关注我，AI 圈大事不迷路～记得点赞收藏，明天同一时间继续唠！」 |
| C3 | 视觉迭代无存档，来回返工 | 视觉规范冻结在「模板A」（`pipeline/render_template_a.py`），改视觉必须先改模板再同步根目录 render.py |
| C4 | 用户反馈口头化（"淡一点""小一点"） | 落到具体参数并记录在 STYLE.md 定稿记录（v10：小字 17/27px、淡色值、50% 灰、渐变细线 2px） |
| C5 | 发布属外部动作 | 未经用户明确说"发"不发布；发布失败回退为草稿 + 通知，不无限重试 |

---

## 下次动手前的检查清单

**渲染异常时**：A1 坐标取整 → A2 半透明图层 → A3 淡色用实值 → A4 中文字体。
**发布异常时**：B2 数据读取方式 → B3 tab 定位 → B7 AI 声明 → B5 坐标（像素扫描重算）→ B10 published=true 判据。
**数据异常时**：C1 字段 fallback → cover_hook 的 `\n` 断行 → title ≤20 字。
