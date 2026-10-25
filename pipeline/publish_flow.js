// 小红书 AI 日报发布流程固化脚本（Playwright MCP · browser_run_code_unsafe）
// 用法：读取本文件全文，作为 mcp__playwright__browser_run_code_unsafe 的 code 参数传入。
// 依赖：已登录的 playwright profile（~/.workbuddy/playwright-profile）+ 系统 Edge。
// 流程：读今日 JSON(file://) → 打开发布页 → 切「上传图文」→ 注入 6 张图 → 填标题/正文
//       → 选「笔记含AI合成内容」声明 → 点红色「发布」→ 校验 published=true。
//
// v2 修订（2026-10-25 实测）：
//  1. getByText('上传图文').click() 会命中侧边栏隐藏元素并超时 → 改为 evaluate 点页面内可见 tab；
//  2. 新增必选步骤：「添加内容类型声明」→「笔记含AI合成内容」（AI 整理内容必须声明）；
//  3. 发布按钮是封闭 shadow DOM 的 <xhs-publish-btn>，文本/a11y 均不可见；
//     红色「发布」按钮中心实测坐标 = (742, 955)（1440×1000 视口，1440 宽下位于底部栏中部偏右）；
//  4. 不依赖 require（MCP 执行环境没有）：今日数据经 file:// 导航读取。
//
// v3 修订（2026-10-25，日常模板切换为B）：
//  5. 日常渲染器改为 pipeline/render_template_b.py，图片目录为 output_b/（勿取错成 output/）。

async (page) => {
  const d = new Date();
  const date = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  const ws = 'REPLACE_WITH_YOUR_WORKSPACE_PATH';
  const out = ws + '/output_b/';

  await page.setViewportSize({ width: 1440, height: 1000 });

  // 读取今日 JSON（file:// 导航后取 body 文本）
  await page.goto('file:///' + ws + '/' + date + '.json');
  const raw = await page.evaluate(() => document.body.innerText);
  const data = JSON.parse(raw);
  // 标题：优先 data.title（≤20 字），否则 takeaways[0] 截 18 字
  const title = data.title || (data.takeaways && data.takeaways[0] ? data.takeaways[0].slice(0, 18) : 'AI 日报');
  const body = data.caption + '\n\n' + (data.hashtags || []).join(' ');

  // 打开发布页
  await page.goto('https://creator.xiaohongshu.com/publish/publish?source=official', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  // 切「上传图文」：点页面内可见的那个 tab
  await page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('span,div,a,li')).filter(e => e.textContent.trim() === '上传图文');
    const vis = els.find(e => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.top >= 0 && b.left >= 0 && b.bottom <= innerHeight + 60; });
    if (vis) vis.click();
  });
  await page.waitForTimeout(2500);

  // 注入 6 张图（封面第一，顺序固定）
  await page.locator('input[type=file]').first().setInputFiles(
    ['cover.png', 'ai_industry_dev.png', 'ai_latest.png', 'ai_product_manager.png', 'ai_salary.png', 'summary.png'].map(f => out + f)
  );
  await page.waitForTimeout(6000);

  // 标题 + 正文
  await page.getByRole('textbox', { name: '填写标题会有更多赞哦' }).fill(title);
  await page.getByRole('textbox').nth(1).fill(body);
  await page.waitForTimeout(800);

  // AI 内容声明：展开「添加内容类型声明」→ 选「笔记含AI合成内容」
  await page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('div,span')).filter(e => e.textContent.trim() === '添加内容类型声明' && e.getBoundingClientRect().width > 40);
    if (els.length) els[els.length - 1].click();
  });
  await page.waitForTimeout(1200);
  await page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('li,div,span')).filter(e => e.textContent.trim() === '笔记含AI合成内容' && e.getBoundingClientRect().width > 30);
    if (els.length) els[els.length - 1].click();
  });
  await page.waitForTimeout(1200);

  // 点发布：红色按钮中心 (742, 955)
  await page.mouse.click(742, 955);
  await page.waitForTimeout(8000);

  const ok = page.url().includes('published=true');
  return JSON.stringify({ ok, url: page.url(), title, date });
}
