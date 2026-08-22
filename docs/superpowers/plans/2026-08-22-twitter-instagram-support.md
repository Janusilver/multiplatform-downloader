# Twitter/X + Instagram 支持 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给多平台下载器加入 X(Twitter) 和 Instagram 的单条 + 用户主页批量下载，完整集成 CLI、GUI、Cookie 扩展、README 与发布流程。

**Architecture:** 复用已装的 yt-dlp（B站同一条路）。新建 `twitter.py` / `instagram.py` 薄封装脚本（URL 识别 + yt-dlp opts 构造 + process()），GUI 的 `classify()` 加两个分支后调各自 `process()`；浏览器扩展加两个站点导出 Cookie；代理走 GUI 输入框 / CLI `--proxy`，不硬编码。

**Tech Stack:** Python 3.13、yt-dlp、requests（现有）、tkinter（现有）、MV3 浏览器扩展（现有）。

**对 spec 的一处实现微调（已确认合理性）：** spec 原写「抽共用 `_run_ytdlp()` 三平台共用」。计划改为**不抽共用函数**——X/IG 各自 `process()` 自包含 yt-dlp 调用（与 douyin/xhs/kuaishou 的 process 模式完全一致），GUI 调 `process()`；**B站 `_run_bili()` 保持不动**。理由：`_run_bili()` 工作正常，抽出重构有回归风险（CLAUDE.md「不重构没坏的东西」）；各平台 opts 差异大（B站 ffmpeg/progress，X/IG cookies/proxy/playlist），共用收益小。

---

### Task 1: twitter.py URL 识别（TDD 先行）

**Files:**
- Test: `tests/test_urls.py`
- Create: `twitter.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_urls.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""URL 识别轻量测试：纯 assert，无 pytest 依赖。跑：.venv/Scripts/python.exe tests/test_urls.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import instagram
import twitter


def check(name: str, fn, cases) -> int:
    failed = 0
    for text, expected in cases:
        got = fn(text)
        ok = got == expected
        failed += 0 if ok else 1
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: {text!r} -> {got!r}"
              + ("" if ok else f"  (期望 {expected!r})"))
    print(f"{name}: {len(cases) - failed}/{len(cases)} 通过\n")
    return failed


def main() -> int:
    f = 0
    f += check("twitter.extract_url", twitter.extract_url, [
        # 单条推文：x.com 与 twitter.com 域名都认
        ("https://x.com/<user>/status/<id 隐去>",
         "https://x.com/<user>/status/<id 隐去>"),
        ("https://twitter.com/jack/status/123",
         "https://twitter.com/jack/status/123"),
        # 从分享文本里取出链接
        ("看看这个 https://x.com/<user>/status/<id 隐去> 有意思",
         "https://x.com/<user>/status/<id 隐去>"),
        # 用户主页批量
        ("https://x.com/jack", "https://x.com/jack"),
        # 系统路径不匹配
        ("https://x.com/search?q=test", None),
        ("https://x.com/home", None),
        # 其他平台链接不匹配
        ("https://www.douyin.com/video/123", None),
    ])
    f += check("twitter.is_profile", twitter.is_profile, [
        ("https://x.com/jack", True),
        ("https://x.com/<user>/status/<id 隐去>", False),
    ])
    f += check("instagram.extract_url", instagram.extract_url, [
        ("https://www.instagram.com/<id 隐去>/", "https://www.instagram.com/<id 隐去>"),
        ("https://instagram.com/<id 隐去>/", "https://instagram.com/<id 隐去>"),
        ("https://www.instagram.com/jack/", "https://www.instagram.com/jack"),
        # 系统路径不匹配
        ("https://www.instagram.com/accounts/login/", None),
        ("https://www.instagram.com/explore/", None),
    ])
    f += check("instagram.is_profile", instagram.is_profile, [
        ("https://www.instagram.com/jack", True),
        ("https://www.instagram.com/<id 隐去>", False),
    ])
    sys.exit(1 if f else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe tests/test_urls.py`
Expected: FAIL —— `ModuleNotFoundError: No module named 'twitter'`（twitter.py / instagram.py 还不存在）

- [ ] **Step 3: 创建 twitter.py 骨架（URL 识别部分）**

创建 `twitter.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X (Twitter) 单条推文 / 用户主页 下载器（yt-dlp 封装）
====================================================
流程：识别链接 → 交给 yt-dlp（cookies + 可选代理）→ 下载到输出目录。
X 媒体为平台原始 CDN 直链，天然无水印。
依赖：yt-dlp（已装 .venv）
用法：
  python twitter.py "https://x.com/<user>/status/<id 隐去>"          # 单条
  python twitter.py "https://x.com/user"                     # 主页批量（默认最近 50 条）
  python twitter.py "链接" -o 目录 --proxy http://127.0.0.1:7890
Cookie（可选，无则匿名试一次）：浏览器扩展导出 twitter_cookies.txt 放脚本目录。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yt_dlp

# Windows 默认 GBK 控制台打不出 ✓ 等字符会 UnicodeEncodeError，强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

_SYSTEM_PATH = r"(?:search\?|i/|explore|home|settings|notifications|messages|compose)"
URL_RE = re.compile(
    r"https?://(?:x\.com|twitter\.com)/"
    r"(?:[A-Za-z0-9_]{1,15}/status/\d+"                       # 单条推文
    r"|(?!{0})[A-Za-z0-9_][A-Za-z0-9_]{0,14})".format(_SYSTEM_PATH))  # 用户主页
SINGLE_RE = re.compile(r"https?://(?:x\.com|twitter\.com)/[A-Za-z0-9_]{1,15}/status/\d+")


def extract_url(text: str) -> str | None:
    m = URL_RE.search(text)
    return m.group(0).rstrip("/") if m else None


def is_profile(url: str) -> bool:
    """True=用户主页（批量），False=单条推文。URL 已 rstrip('/')。"""
    return bool(URL_RE.fullmatch(url)) and not SINGLE_RE.search(url)
```

注意：`is_profile` 的入参是 `extract_url` 的输出（已 rstrip `/`）。URL_RE 用 `search`（从文本里取），is_profile 用 `fullmatch`（判断整串 URL 类型）。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe tests/test_urls.py`
Expected: `twitter.extract_url: 7/7 通过`、`twitter.is_profile: 2/2 通过`、`instagram.*: 0/0`（Step 5 前 instagram 测试仍失败）——本任务末尾 instagram 失败属预期，Task 3 修复。

- [ ] **Step 5: Commit**

```bash
git add twitter.py tests/test_urls.py
git commit -m "feat: add twitter url recognition (yt-dlp wrapper skeleton)"
```

---

### Task 2: twitter.py 完整下载逻辑

**Files:**
- Modify: `twitter.py`（在 Task 1 骨架后追加）

- [ ] **Step 1: 在 twitter.py 末尾追加 process() 与 main()**

```python
def process(url: str, out_dir: Path, cookie_path: str | None = None,
            proxy: str = "", max_items: int = 50) -> None:
    """下载单条推文或用户主页。out_dir 需已存在。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = is_profile(url)
    # 主页批量按作者建子目录；单条平铺在 out_dir
    tmpl = ("%(uploader)s/%(id)s_%(playlist_index)02d.%(ext)s" if profile
            else "%(uploader)s_%(id)s_%(playlist_index)02d.%(ext)s")
    opts: dict = {
        "outtmpl": str(out_dir / tmpl),
        "quiet": True,
        "no_warnings": True,
        "nooverwrites": True,          # 已存在的文件跳过，不重复下
    }
    if cookie_path and Path(cookie_path).exists():
        opts["cookiefile"] = str(cookie_path)   # Netscape 格式，扩展导出即用
    if proxy:
        opts["proxy"] = proxy
    if profile and max_items:
        opts["playlist_items"] = f"1:{max_items}"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        print(f"  [✓] 已保存 → {out_dir}")
    except yt_dlp.utils.DownloadError as e:
        hint = "" if cookie_path else "（无 Cookie，若失败请导 twitter_cookies.txt 后重试）"
        print(f"  [!] 下载失败{hint}: {str(e).splitlines()[0]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="X (Twitter) 单条推文/主页批量下载器（yt-dlp）")
    ap.add_argument("input", help="推文/主页链接，或含链接的文本")
    ap.add_argument("-o", "--output", default=None, help="保存目录（默认：脚本目录/downloads）")
    ap.add_argument("-c", "--cookie", default="twitter_cookies.txt", help="Cookie 文件路径（可缺省，匿名试一次）")
    ap.add_argument("--proxy", default="", help="代理地址，如 http://127.0.0.1:7890（默认直连）")
    ap.add_argument("--max", type=int, default=50, help="主页批量上限（默认 50）")
    args = ap.parse_args()

    out_dir = Path(args.output) if args.output else Path(__file__).resolve().parent / "downloads"
    url = extract_url(args.input)
    if not url:
        sys.exit("[!] 未找到 X 链接")
    print(f"  [*] 解析: {url}")
    process(url, out_dir, cookie_path=args.cookie, proxy=args.proxy, max_items=args.max)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
```

- [ ] **Step 2: 验证脚本可解析、可启动**

Run: `.venv/Scripts/python.exe twitter.py --help`
Expected: 打印 argparse 帮助，无 ImportError（yt-dlp 已装）。真实下载在 Task 8 实测。

- [ ] **Step 3: Commit**

```bash
git add twitter.py
git commit -m "feat: add twitter download logic (yt-dlp wrapper)"
```

---

### Task 3: instagram.py URL 识别（TDD 先行）

**Files:**
- Create: `instagram.py`
- Test: `tests/test_urls.py`（已有 instagram 测试用例）

- [ ] **Step 1: 创建 instagram.py（URL 识别部分）**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instagram 单条帖子/Reels / 用户主页 下载器（yt-dlp 封装）
=========================================================
流程：识别链接 → 交给 yt-dlp（cookies + 可选代理）→ 下载到输出目录。
IG 媒体为平台原始 CDN 直链，天然无水印。
依赖：yt-dlp（已装 .venv）
用法：
  python instagram.py "https://www.instagram.com/<id 隐去>/"    # 单条帖子
  python instagram.py "https://www.instagram.com/<id 隐去>/" # Reels
  python instagram.py "https://www.instagram.com/user/"           # 主页批量（默认最近 50 条）
Cookie（强烈建议）：浏览器扩展导出 instagram_cookies.txt 放脚本目录（IG 匿名大概率拿不到数据）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yt_dlp

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

_SYSTEM_PATH = r"(?:p/|reel/|tv/|stories/|accounts/|direct/|explore/|about/|help/|web/|static/)"
URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:p/[A-Za-z0-9_-]+"                                       # 帖子
    r"|reel/[A-Za-z0-9_-]+"                                      # Reels
    r"|tv/[A-Za-z0-9_-]+"                                        # IGTV
    r"|(?!{0})[A-Za-z0-9_][A-Za-z0-9_.]{0,29})".format(_SYSTEM_PATH))  # 用户主页
SINGLE_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[A-Za-z0-9_-]+")


def extract_url(text: str) -> str | None:
    m = URL_RE.search(text)
    return m.group(0).rstrip("/") if m else None


def is_profile(url: str) -> bool:
    """True=用户主页（批量），False=单条帖子/Reels。URL 已 rstrip('/')。"""
    return bool(URL_RE.fullmatch(url)) and not SINGLE_RE.search(url)
```

- [ ] **Step 2: 跑测试确认通过**

Run: `.venv/Scripts/python.exe tests/test_urls.py`
Expected: `instagram.extract_url: 4/4 通过`、`instagram.is_profile: 2/2 通过`，全部分组 `x/x 通过`，exit 0。

- [ ] **Step 3: Commit**

```bash
git add instagram.py
git commit -m "feat: add instagram url recognition (yt-dlp wrapper skeleton)"
```

---

### Task 4: instagram.py 完整下载逻辑

**Files:**
- Modify: `instagram.py`（在 Task 3 骨架后追加）

- [ ] **Step 1: 追加 process() 与 main()**

与 twitter.py 完全同构，三处差异：cookie 默认文件名、提示语、单条 outtmpl 不变。

```python
def process(url: str, out_dir: Path, cookie_path: str | None = None,
            proxy: str = "", max_items: int = 50) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = is_profile(url)
    tmpl = ("%(uploader)s/%(id)s_%(playlist_index)02d.%(ext)s" if profile
            else "%(uploader)s_%(id)s_%(playlist_index)02d.%(ext)s")
    opts: dict = {
        "outtmpl": str(out_dir / tmpl),
        "quiet": True,
        "no_warnings": True,
        "nooverwrites": True,
    }
    if cookie_path and Path(cookie_path).exists():
        opts["cookiefile"] = str(cookie_path)
    if proxy:
        opts["proxy"] = proxy
    if profile and max_items:
        opts["playlist_items"] = f"1:{max_items}"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        print(f"  [✓] 已保存 → {out_dir}")
    except yt_dlp.utils.DownloadError as e:
        hint = "" if cookie_path else "（无 Cookie，IG 大概率失败，请导 instagram_cookies.txt）"
        print(f"  [!] 下载失败{hint}: {str(e).splitlines()[0]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Instagram 单条帖子/Reels/主页批量下载器（yt-dlp）")
    ap.add_argument("input", help="帖子/Reels/主页链接，或含链接的文本")
    ap.add_argument("-o", "--output", default=None, help="保存目录（默认：脚本目录/downloads）")
    ap.add_argument("-c", "--cookie", default="instagram_cookies.txt", help="Cookie 文件路径（可缺省，匿名试一次）")
    ap.add_argument("--proxy", default="", help="代理地址，如 http://127.0.0.1:7890（默认直连）")
    ap.add_argument("--max", type=int, default=50, help="主页批量上限（默认 50）")
    args = ap.parse_args()

    out_dir = Path(args.output) if args.output else Path(__file__).resolve().parent / "downloads"
    url = extract_url(args.input)
    if not url:
        sys.exit("[!] 未找到 Instagram 链接")
    print(f"  [*] 解析: {url}")
    process(url, out_dir, cookie_path=args.cookie, proxy=args.proxy, max_items=args.max)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
```

- [ ] **Step 2: 验证脚本可解析**

Run: `.venv/Scripts/python.exe instagram.py --help`
Expected: 打印 argparse 帮助，无 ImportError。

- [ ] **Step 3: Commit**

```bash
git add instagram.py
git commit -m "feat: add instagram download logic (yt-dlp wrapper)"
```

---

### Task 5: 浏览器扩展加 X / Instagram 站点

**Files:**
- Modify: `extensions/cookie-export/popup.js`
- Modify: `extensions/cookie-export/popup.html`
- Modify: `extensions/cookie-export/manifest.json`

- [ ] **Step 1: popup.js 的 SITES 加两站**

在 `popup.js` 的 `SITES` 字典内追加两行（原三行保留）：

```js
const SITES = {
  'btn-dy':  { domain: '.douyin.com',       file: 'douyin_cookies.txt',   name: '抖音' },
  'btn-xhs': { domain: '.xiaohongshu.com',  file: 'xhs_cookies.txt',      name: '小红书' },
  'btn-ks':  { domain: '.kuaishou.com',     file: 'kuaishou_cookies.txt', name: '快手' },
  'btn-tw':  { domain: '.x.com',            file: 'twitter_cookies.txt',  name: 'X' },
  'btn-ig':  { domain: '.instagram.com',    file: 'instagram_cookies.txt', name: 'Instagram' },
};
```

- [ ] **Step 2: popup.html 加两个按钮与配色**

在 `popup.html` 的 `#btn-ks` 按钮后追加两个按钮：

```html
  <button id="btn-tw">导出 X Cookie</button>
  <button id="btn-ig">导出 Instagram Cookie</button>
```

在 `<style>` 里追加两行配色：

```css
  #btn-tw  { background: #1d9bf0; }
  #btn-ig  { background: #e1306c; }
```

- [ ] **Step 3: manifest.json 的 host_permissions 加域名**

```json
  "host_permissions": [
    "*://*.douyin.com/*",
    "*://*.xiaohongshu.com/*",
    "*://*.kuaishou.com/*",
    "*://*.x.com/*",
    "*://*.instagram.com/*"
  ],
```

- [ ] **Step 4: 验证**

Run: `.venv/Scripts/python.exe -c "import json; json.load(open('extensions/cookie-export/manifest.json')); print('manifest OK')"`
Expected: `manifest OK`。popup.js 语法：`node --check extensions/cookie-export/popup.js`（node 已装），Expected: 无输出（通过）。

- [ ] **Step 5: Commit**

```bash
git add extensions/cookie-export
git commit -m "feat: cookie export extension supports X and Instagram"
```

---

### Task 6: gui.py 集成

**Files:**
- Modify: `gui.py`

- [ ] **Step 1: 顶部常量区加 Cookie 路径**

在 `KS_COOKIE_PATH` 行后追加：

```python
TW_COOKIE_PATH = BASE / "twitter_cookies.txt"
IG_COOKIE_PATH = BASE / "instagram_cookies.txt"
```

- [ ] **Step 2: classify() 加两个平台分支**

在 `classify()` 的 kuaishou try/except 块之后（`return None, None` 之前）追加：

```python
    try:
        import twitter
        m = twitter.URL_RE.search(text)
        if m:
            return "twitter", m.group(0).rstrip("/")
    except ImportError:
        pass
    try:
        import instagram
        m = instagram.URL_RE.search(text)
        if m:
            return "instagram", m.group(0).rstrip("/")
    except ImportError:
        pass
```

- [ ] **Step 3: 平台名映射加两项**

`_poll_clipboard()` 里的 `name = {...}` 字典加两键：

```python
                name = {"douyin": "抖音", "xhs": "小红书", "kuaishou": "快手", "bili": "B站",
                        "twitter": "X", "instagram": "Instagram"}.get(platform, "分享")
```

- [ ] **Step 4: 添加代理输入框**

在 `self.btn = ttk.Button(root, text="开始下载", command=self.start)` 之后插入代理行：

```python
        prow = ttk.Frame(root)
        prow.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(prow, text="代理（X/IG 建议填写，留空直连）：").pack(side="left")
        self.proxy_var = tk.StringVar()
        self.proxy_entry = ttk.Entry(prow, textvariable=self.proxy_var, width=30)
        self.proxy_entry.pack(side="left", fill="x", expand=True)
```

- [ ] **Step 5: 添加 _run_twitter / _run_instagram 方法**

在 `_run_bili()` 方法之后追加：

```python
    def _run_twitter(self, url: str) -> None:
        try:
            import twitter
        except ImportError as e:
            self._post(f"  [!] X 依赖缺失（yt-dlp）：{e}")
            return
        cookie = str(TW_COOKIE_PATH) if TW_COOKIE_PATH.exists() else ""
        proxy = self.proxy_var.get().strip()
        twitter.process(url, self.out_dir, cookie_path=cookie, proxy=proxy)

    def _run_instagram(self, url: str) -> None:
        try:
            import instagram
        except ImportError as e:
            self._post(f"  [!] Instagram 依赖缺失（yt-dlp）：{e}")
            return
        cookie = str(IG_COOKIE_PATH) if IG_COOKIE_PATH.exists() else ""
        proxy = self.proxy_var.get().strip()
        instagram.process(url, self.out_dir, cookie_path=cookie, proxy=proxy)
```

- [ ] **Step 6: _run() 分流加两个 elif**

在 `_run()` 的 `elif platform == "kuaishou":` 分支后、`else:` 之前插入：

```python
                    elif platform == "twitter":
                        self._run_twitter(url)
                    elif platform == "instagram":
                        self._run_instagram(url)
```

- [ ] **Step 7: 标题、欢迎语加两平台**

- `__init__` 的 `root.title(...)` 改为：
  `root.title(f"抖音 / 小红书 / 快手 / B站 / X / Instagram 下载器 v{APP_VERSION}")`
- `_welcome()` 的窗口标题文案 `"  抖音 / 小红书 / 快手 / B站 下载器"` 同步改为
  `"  抖音 / 小红书 / 快手 / B站 / X / Instagram 下载器"`
- `_welcome()` 在 KS Cookie 检查后追加 X/IG 检查：

```python
        if TW_COOKIE_PATH.exists():
            self._post(f"[OK] 已找到 X Cookie（可选，匿名可能失败）")
        else:
            self._post("[!] 未找到 twitter_cookies.txt —— X 匿名可用，可能被登录墙挡住")
        if IG_COOKIE_PATH.exists():
            self._post(f"[OK] 已找到 Instagram Cookie（可选，匿名大概率失败）")
        else:
            self._post("[!] 未找到 instagram_cookies.txt —— IG 匿名大概率失败")
```

- [ ] **Step 8: 验证 classify 与 GUI 启动**

Run:
```bash
.venv/Scripts/python.exe -c "import gui; print(gui.classify('https://x.com/<user>/status/<id 隐去>'))"
.venv/Scripts/python.exe -c "import gui; print(gui.classify('https://www.instagram.com/<id 隐去>/'))"
```
Expected: 输出 `('twitter', 'https://x.com/<user>/status/<id 隐去>')` 和 `('instagram', 'https://www.instagram.com/<id 隐去>')`。
再 Run: `.venv/Scripts/python.exe -c "import gui"` —— 无报错（不启动窗口，仅验证可导入）。

- [ ] **Step 9: Commit**

```bash
git add gui.py
git commit -m "feat: GUI integrates X/Instagram with proxy input"
```

---

### Task 7: .gitignore 与 README

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `README.en.md`

- [ ] **Step 1: .gitignore 加两个新 Cookie 文件**

在隐私节（第 3-7 行）追加：

```
twitter_cookies.txt
twitter_cookies_*.txt
instagram_cookies.txt
instagram_cookies_*.txt
```

- [ ] **Step 2: README.md 加平台与用法**

在「工作流」的 CLI 命令行块追加两行：

```bash
.venv/Scripts/python.exe twitter.py "链接" [-o 目录] [--proxy http://127.0.0.1:7890]  # X 单条/主页
.venv/Scripts/python.exe instagram.py "链接" [-o 目录] [--proxy http://127.0.0.1:7890] # Instagram
```

在「为什么这样设计」或新增段落说明：

```
**X / Instagram**：复用 yt-dlp（与 B站 同路）。两平台媒体为原始 CDN 直链，天然无水印。
X 现需登录态（匿名可能被登录墙挡住）；IG 需登录 session（匿名大概率失败）——用浏览器扩展
导 twitter_cookies.txt / instagram_cookies.txt 放脚本/exe 旁。国外 CDN 直连不稳，GUI「代理」
输入框或 CLI --proxy 填代理地址（如 http://127.0.0.1:7890）；国内平台不受影响。支持单条
（推文/帖子/Reels）与用户主页批量（默认最近 50 条，CLI --max N 调整）。
```

同步更新 README 开头功能列表与 README.en.md 对应英文（同结构、英文措辞）。

- [ ] **Step 3: 验证**

Run: `git check-ignore twitter_cookies.txt instagram_cookies.txt`
Expected: 两个路径都被打印（确认 .gitignore 生效）。

- [ ] **Step 4: Commit**

```bash
git add .gitignore README.md README.en.md
git commit -m "docs: X/Instagram support in README; ignore new cookie files"
```

---

### Task 8: 本机真实实测（手动，需网络环境）

前置：Chrome `chrome://extensions/` 加载解压扩展（更新后版本）→ 登录 x.com / instagram.com → 点扩展分别导出 `twitter_cookies.txt` / `instagram_cookies.txt` 到项目根目录。7890 代理在线。

**Files:**
- 无代码改动；验证 Task 1-7 产物

- [ ] **Step 1: X 单条推文（视频）**

Run: `.venv/Scripts/python.exe twitter.py "某条带视频的推文链接" --proxy http://127.0.0.1:7890`
Expected: `[✓] 已保存`，downloads 下出现 `作者_推文ID_01.mp4`，播放无水印。

- [ ] **Step 2: X 用户主页批量**

Run: `.venv/Scripts/python.exe twitter.py "某用户主页链接" --proxy http://127.0.0.1:7890 --max 5`
Expected: 作者子目录出现 ≤5 个文件（视频/图片混排）。

- [ ] **Step 3: IG 单条图集**

Run: `.venv/Scripts/python.exe instagram.py "某图集帖子链接" --proxy http://127.0.0.1:7890`
Expected: 帖子下多张图 `作者_帖子ID_01.jpg...`。

- [ ] **Step 4: IG Reels + 主页批量**

Run: `.venv/Scripts/python.exe instagram.py "某 Reels 链接" --proxy http://127.0.0.1:7890`，再 `.venv/Scripts/python.exe instagram.py "某主页" --proxy http://127.0.0.1:7890 --max 3`
Expected: Reels 视频 + 主页子目录批量，均无水印。

- [ ] **Step 5: GUI 手动验证**

启动 `.venv/Scripts/python.exe gui.py`：代理框填 `http://127.0.0.1:7890`，粘贴 X/IG 链接，确认分流、下载、历史记录、剪贴板识别（复制 X/IG 链接时提示条出现）。

- [ ] **Step 6: 匿名兜底验证**

Run: `.venv/Scripts/python.exe twitter.py "推文链接" --proxy http://127.0.0.1:7890 -c 不存在.txt`
Expected: 匿名尝试，若被登录墙挡则打印失败提示（含「请导 twitter_cookies.txt」），不崩溃。

- [ ] **Step 7: 清理下载产物**

`downloads/` 已被 .gitignore 排除，实测产物留在本地即可，不提交。

---

### Task 9: 打包与发布（需用户确认后执行）

**Files:**
- Modify: `gui.py`（APP_VERSION）
- 打包产物：本地 PyInstaller + GitHub Actions

- [ ] **Step 1: 升版本号**

`gui.py` 顶部 `APP_VERSION = "1.2.1"` 改为 `"1.3.0"`。

- [ ] **Step 2: 本地 PyInstaller 打包验证**

Run: `.venv/Scripts/python.exe build.py`（现有打包脚本）
Expected: `dist/多平台下载器.exe` 生成；启动 exe 冒烟测试：X/IG 链接可识别、代理框可填。

- [ ] **Step 3: Commit 代码**

```bash
git add gui.py
git commit -m "v1.3.0: X/Instagram support (yt-dlp wrapper, proxy config)"
```

- [ ] **Step 4: 打 tag 发 Release（先问用户，push 是红线）**

确认 `.gitignore` 不含 `twitter_cookies.txt`/`instagram_cookies.txt` 之外的新隐私文件后：
```bash
git tag v1.3.0 && git push origin main --tags
```
（push 前停下问用户；CI 自动出包 + Release 正文。）

---

## 自检记录（写作完成时已过）

- **Spec 覆盖**：spec 的架构表 6 项 → Task 1-7 逐项对应；关键决策 6 项 → 决策 1(cookie) Task 5/6/7、决策 2(代理) Task 2/4/6、决策 3(匿名兜底) Task 2/4/6、决策 4/5/6(命名/上限/形态) Task 2/4；测试计划 4 场景 → Task 8；发布注意 → Task 7(.gitignore)/Task 9。
- **占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码。
- **类型一致**：`extract_url`/`is_profile`/`process(url, out_dir, cookie_path, proxy, max_items)` 在 Task 1-6 全部同签名；GUI 调 `twitter.process(url, self.out_dir, cookie_path=..., proxy=...)` 与定义一致；`_SYSTEM_PATH`/`SINGLE_RE` 命名在 twitter/instagram 两脚本一致。
- **已知待实测项**：X 主页批量是否带 `playlist_index`（yt-dlp 行为差异）、IG 匿名是否完全失败——Task 8 实测后若与计划假设不符，就地微调 outtmpl/提示文案。
