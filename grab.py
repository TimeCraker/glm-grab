"""
GLM Coding 抢购脚本 v2
======================
智谱 GLM Coding 套餐（Lite / Pro / Max）补货时自动抢

v2 优化（2026-06-18 实战后）：
- 多标签并行：开 4 个 tab 同时抢，命中率高 4 倍
- 自动定时启动：设好时间就睡，09:58 自动进入高频模式
- 更宽的按钮文字匹配：覆盖"立即开通"/"抢购"/"抢"等 16 种文案
- 刷新间隔缩短到 400ms（原来 800ms）
- 赢家通吃：一个 tab 抢到 → 其他 tab 立刻关
- 智能识别"今日售罄 vs 等下波补货"

用法：
    python grab.py
    （设好 RESTOCK_TIME 和 TAB_COUNT，去睡觉）
"""

import asyncio
import os
import sys
import itertools
from datetime import datetime
from playwright.async_api import async_playwright

# Windows cmd 默认 GBK 编码会吞掉 emoji/特殊符号导致崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ===================== 你要改的 =====================
PLAN = "Pro"                  # 套餐: "Lite" / "Pro" / "Max"
RESTOCK_TIME = "10:00:00"     # 补货时间（24h 制）
AUTO_START_MIN_BEFORE = 2     # 提前几分钟开始刷（推荐 1-3）
TAB_COUNT = 4                 # 并行 tab 数（推荐 3-5，越多越快但越容易被 ban）
REFRESH_INTERVAL = 0.4        # 页面刷新间隔（秒）
SCAN_INTERVAL = 0.1           # 按钮扫描间隔（秒）
TRIGGER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "GO.txt")
# =================================================


# 购买按钮关键词（覆盖所有可能的文案）
BUY_KEYWORDS = [
    "立即购买", "立即订阅", "立即开通", "立即支付", "立即下单",
    "去购买", "补货购买", "去开通", "去订阅",
    "购买", "订阅", "开通", "下单", "支付",
    "抢购", "立即抢购",
    "Subscribe", "Buy", "Purchase", "Order",
]

# 售罄状态关键词
SOLDOUT_KEYWORDS = ["售罄", "暂时", "已抢光", "抢光", "缺货", "无库存"]


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def is_logged_in(page) -> bool:
    """更可靠的登录检测"""
    url = page.url.lower()
    if any(k in url for k in ["login", "passport", "signin", "auth"]):
        return False
    logged_in_signs = ["text=控制台", "text=个人中心", ".ant-avatar"]
    for sel in logged_in_signs:
        try:
            if await page.locator(sel).count() > 0:
                return True
        except Exception:
            pass
    not_logged_signs = ["text=立即登录", "text=扫码登录", "button:has-text('注册')"]
    for sel in not_logged_signs:
        try:
            if await page.locator(sel).count() > 0:
                return False
        except Exception:
            pass
    return False


async def ensure_monthly_tab(page) -> bool:
    """确保在『连续包月』标签"""
    try:
        monthly_tab = page.locator("text=连续包月").first
        if await monthly_tab.count() > 0:
            await monthly_tab.click(timeout=1000)
            await asyncio.sleep(0.15)
            return True
    except Exception:
        pass
    return False


# 真支付页的 URL 特征（必须满足才认为成功）
PAYMENT_URL_KEYWORDS = [
    "pay", "checkout", "order", "alipay", "wxpay", "tenpay",
    "payment", "确认订单", "下单", "收银台",
]

# 拒绝的 URL 模式（这些是误报或错误目标，绝对不是个人套餐支付页）
REJECTED_URL_KEYWORDS = [
    "team", "团队", "enterprise", "企业",  # 团队版/企业版
    "billing/team", "billing/enterprise",
]


async def is_payment_url(current_url: str, original_url: str) -> bool:
    """
    判断当前 URL 是否是【个人套餐】的真支付页。
    三重检查：
    1) 不能是团队/企业版（这些不是用户要的）
    2) 必须是支付页（域名变了 / 路径含支付关键词）
    3) 必须在 bigmodel.cn 下（避免跳到第三方钓鱼页）
    """
    try:
        from urllib.parse import urlparse
        cur = urlparse(current_url)
        orig = urlparse(original_url)
        full_lower = current_url.lower()

        # 0) 拒绝: URL 含团队/企业关键词 → 绝对误报
        if any(k in full_lower for k in REJECTED_URL_KEYWORDS):
            return False

        # 1) 域名变了 + 是知名支付网关 → 真支付页
        if cur.netloc and orig.netloc and cur.netloc != orig.netloc:
            payment_domains = ["alipay", "wxpay", "tenpay", "pay", "checkout"]
            if any(d in cur.netloc.lower() for d in payment_domains):
                return True
            # 跳到其他非 bigmodel 域名，但不是已知支付网关 → 不算
            return False

        # 2) 仍在 bigmodel.cn 下，但路径含明确支付关键词 + 是个人套餐路径
        if "/glm-coding" in cur.path:
            # 还在 glm-coding 页面 → 没跳转走，误报
            return False
        # 路径里含 order/checkout/pay + 不在 /glm-coding + 不是 team → 真个人支付页
        if any(k in full_lower for k in PAYMENT_URL_KEYWORDS):
            return True

        return False
    except Exception:
        return False


async def try_click_buy_button(page, plan: str) -> tuple[bool, str]:
    """
    找非售罄的购买按钮并点击。返回 (真成功?, 按钮文字)
    关键修复: 点击后必须验证跳到真支付页（路径变了或域名变了），否则是误报。
    """
    try:
        candidates = page.locator("button, a[role='button'], .ant-btn")
        n = await candidates.count()
        for i in range(n):
            btn = candidates.nth(i)
            try:
                text = (await btn.text_content() or "").strip()
            except Exception:
                continue
            if not text or len(text) < 2:
                continue
            # 售罄 → 跳过
            if any(k in text for k in SOLDOUT_KEYWORDS):
                continue
            # 必须是购买相关
            if not any(k in text for k in BUY_KEYWORDS):
                continue
            # 必须可见 + 可点
            try:
                if not await btn.is_visible():
                    continue
                if await btn.is_disabled():
                    continue
            except Exception:
                continue
            # 记录点击前的 URL（用于验证）
            url_before = page.url
            # 点！
            try:
                await btn.click(no_wait_after=True, force=True, timeout=2000)
            except Exception:
                continue
            # 验证是否跳到真支付页（最多等 2 秒）
            for _ in range(20):
                await asyncio.sleep(0.1)
                if await is_payment_url(page.url, url_before):
                    return True, text
            # 不是支付页 = 误报，继续找下一个
        return False, ""
    except Exception:
        return False, ""


async def grab_one_tab(page, tab_id: int, plan: str) -> int:
    """
    单个 tab 的抢循环。
    返回这个 tab 最终点击的轮次（0 表示没抢到）。
    """
    refresh_every = max(1, int(REFRESH_INTERVAL / SCAN_INTERVAL))
    rounds_done = 0
    for i in itertools.count(1):
        rounds_done = i
        ok, text = await try_click_buy_button(page, plan)
        if ok:
            print(f"\n[{ts()}] [Tab {tab_id}] ✓ 抢到！点击按钮: {text!r}")
            return i
        if i % refresh_every == 0:
            try:
                await page.reload(wait_until="domcontentloaded", timeout=3000)
                # 每次刷新后重新切月度（页面会回到默认季卡）
                await ensure_monthly_tab(page)
            except Exception:
                pass
        if i % 20 == 0:
            print(f"[{ts()}] [Tab {tab_id}] 第 {i} 轮扫描中...")
        await asyncio.sleep(SCAN_INTERVAL)
    return rounds_done


async def wait_for_start() -> str:
    """
    等待开始信号：
    1) 触发文件 GO.txt 存在
    2) 到了 RESTOCK_TIME - AUTO_START_MIN_BEFORE
    返回 'trigger' 或 'schedule'
    """
    h, m, s = map(int, RESTOCK_TIME.split(":"))
    target_sec = h * 3600 + m * 60 + s - AUTO_START_MIN_BEFORE * 60
    # 跨天处理：如果目标时间已经过了，明天再开始
    now = datetime.now()
    now_sec = now.hour * 3600 + now.minute * 60 + now.second
    if now_sec > target_sec:
        target_sec += 24 * 3600  # 推迟到明天

    target_dt = datetime.fromtimestamp(target_sec - now_sec + now.timestamp() if now_sec > h*3600+m*60+s else target_sec)
    th, tm, ts2 = (target_sec // 3600) % 24, (target_sec // 60) % 60, target_sec % 60

    print(f"\n[启动] 等到 {th:02d}:{tm:02d}:{ts2:02d}（{RESTOCK_TIME} 前 {AUTO_START_MIN_BEFORE} 分钟）开始抢")
    print(f"       或创建文件 {TRIGGER_FILE} 立刻开始\n")

    while True:
        if os.path.exists(TRIGGER_FILE):
            try:
                os.remove(TRIGGER_FILE)
            except OSError:
                pass
            return "trigger"
        now = datetime.now()
        now_sec = now.hour * 3600 + now.minute * 60 + now.second
        if now.hour == th and now.minute == tm and now.second >= ts2:
            return "schedule"
        # 显示倒计时
        remain = target_sec - now_sec
        if remain > 0:
            if remain > 60:
                print(f"\r[倒计时] 距离开始还有 {remain/60:5.1f} 分钟 ", end="", flush=True)
            else:
                print(f"\r[最后冲刺] 还有 {remain:5.1f} 秒 ", end="", flush=True)
        await asyncio.sleep(0.5)


async def main():
    print("=" * 60)
    print(f"  GLM Coding 抢购脚本 v2")
    print(f"  套餐: {PLAN} | 补货: {RESTOCK_TIME} | 提前 {AUTO_START_MIN_BEFORE}min")
    print(f"  并行 tab: {TAB_COUNT} | 刷新: {REFRESH_INTERVAL}s | 扫描: {SCAN_INTERVAL}s")
    print("=" * 60)

    GLM_URL = "https://bigmodel.cn/glm-coding?utm_source=bigModel&utm_medium=Special&utm_content=glm-code&utm_campaign=Platform_Ops&_channel_track_key=8BAeCdUS"

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./glm_profile",
            headless=False,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        # 1. 用第一个 tab 登录
        page = browser.pages[0] if browser.pages else await browser.new_page()
        print(f"\n[1/4] 打开 {GLM_URL[:60]}...")
        await page.goto(GLM_URL, wait_until="domcontentloaded")
        await asyncio.sleep(1)

        print("[2/4] 检查登录...")
        if not await is_logged_in(page):
            print("\n" + "!" * 50)
            print("  请在浏览器里登录（手机扫码 / 账号密码）")
            print("  登录态会自动保存")
            print("  5 分钟超时")
            print("!" * 50 + "\n")
            start = datetime.now()
            while (datetime.now() - start).total_seconds() < 300:
                if await is_logged_in(page):
                    break
                await asyncio.sleep(2)
            else:
                print("[X] 登录超时")
                return
            print("[OK] 登录成功\n")

        # 2. 开多个 tab
        tabs = [page]
        for i in range(1, TAB_COUNT):
            try:
                new_page = await browser.new_page()
                await new_page.goto(GLM_URL, wait_until="domcontentloaded")
                await ensure_monthly_tab(new_page)
                tabs.append(new_page)
                print(f"     [OK] Tab {i+1}/{TAB_COUNT} 已开")
            except Exception as e:
                print(f"     [!] Tab {i+1} 开失败: {e}")

        print(f"[3/4] {len(tabs)} 个 tab 就绪")

        # 3. 等触发
        start_mode = await wait_for_start()
        print(f"\n[4/4] [{ts()}] 开始抢！（{start_mode} 模式）")
        print(f"       4 个 tab 并行刷新 + 扫描，目标: {PLAN}\n")

        # 4. 并行抢
        tasks = [asyncio.create_task(grab_one_tab(tab, i+1, PLAN)) for i, tab in enumerate(tabs)]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        winner_idx = None
        for task in done:
            try:
                result = task.result()
                if result > 0:
                    winner_idx = tasks.index(task)
                    break
            except Exception:
                pass

        # 取消其他任务
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        # 关闭其他 tab
        for i, tab in enumerate(tabs):
            if i != winner_idx:
                try:
                    await tab.close()
                except Exception:
                    pass

        if winner_idx is None:
            print(f"\n[{ts()}] [X] 所有 tab 都没抢到，浏览器保持 5 分钟供手动操作")
            await asyncio.sleep(300)
            return

        # 5. 跳到支付页
        winner_page = tabs[winner_idx]
        try:
            await winner_page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        print(f"\n[{ts()}] [!!!] Tab {winner_idx + 1} 抢到！")
        print(f"[!] 当前页面: {winner_page.url}")
        print(f"[!] 请立即在浏览器里完成支付！")
        print(f"[!] 浏览器保持 10 分钟...")

        await asyncio.sleep(600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n[{ts()}] [!] 用户中断")
