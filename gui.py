#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音 / 小红书 / B站 / YouTube / X / Instagram 下载器（tkinter GUI，PyInstaller 打包 exe 用）
抖音复用 douyin.py；小红书复用 xhs.py；B站 / YouTube 走 yt-dlp
（用便携 ffmpeg 合并音视频）；X / Instagram 走各自模块。
文件与 Cookie 均以 exe 所在目录为基准，双击即可用。
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import douyin

APP_VERSION = "1.6.6"
UPDATE_URL = "https://api.github.com/repos/Janusilver/multiplatform-downloader/releases/latest"
PROXY_FALLBACK = {"http": "http://127.0.0.1:7890",
                  "https": "http://127.0.0.1:7890"}

BILI_RE = re.compile(
    r"(?:https?://(?:www\.)?bilibili\.com/[^?\s]+"
    r"|b23\.tv/\S+"
    r"|BV[0-9A-Za-z]{10}"
    r"|av\d+)"
)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

if getattr(sys, "frozen", False):              # 打包后：exe 所在目录 + PyInstaller 解压目录
    BASE = Path(sys.executable).resolve().parent
    FFMPEG_DIR = Path(getattr(sys, "_MEIPASS", str(BASE))) / "ffmpeg"
else:                                          # 开发模式：脚本所在目录
    BASE = Path(__file__).resolve().parent
    FFMPEG_DIR = BASE / "ffmpeg"

def _ffmpeg_location() -> Path | None:
    """ffmpeg 解析实现统一放在 douyin.find_ffmpeg（各平台共用一份）。"""
    return douyin.find_ffmpeg(FFMPEG_DIR.parent)


def _find_cookie(name: str) -> Path:
    """Cookie 允许放两处：程序所在目录（exe 旁边）或它的上级目录（跑源码时的项目根）。

    用户常把 exe 放 release/、Cookie 放仓库根目录，只认一处就会「明明导出了却说没有」；
    再兜底当前工作目录。都找不到时返回主位置，方便提示里直接说该放哪。
    """
    primary = BASE / name
    for cand in (primary, BASE.parent / name, Path.cwd() / name):
        if cand.exists():
            return cand
    return primary


COOKIE_PATH = _find_cookie("douyin_cookies.txt")
XHS_COOKIE_PATH = _find_cookie("xhs_cookies.txt")
TW_COOKIE_PATH = _find_cookie("twitter_cookies.txt")
IG_COOKIE_PATH = _find_cookie("instagram_cookies.txt")
YT_COOKIE_PATH = _find_cookie("youtube_cookies.txt")
BILI_COOKIE_PATH = _find_cookie("bilibili_cookies.txt")

# ---- 用户向提示（只说「该做什么」，原理写在 README / AGENTS）----
PLATFORM_NAMES = {
    "douyin": "抖音", "xhs": "小红书", "bili": "B站",
    "youtube": "YouTube", "twitter": "X", "instagram": "Instagram",
}
PLATFORM_HINTS = {
    "douyin": "必须有登录 Cookie（douyin_cookies.txt 放程序旁边），缺失会解析失败",
    "xhs": "建议导出 Cookie（匿名易被风控），视频可能带小红书号水印",
    "bili": "不登录最高 1080P，4K / 1080P60 需大会员 Cookie",
    "youtube": "国内网络需要代理（海外可直连）；公开视频不需要 Cookie",
    "twitter": "仅支持单条推文（/status/…），主页批量不支持；国内网络需要代理",
    "instagram": "需要登录 Cookie；国内网络还需要代理；用户主页批量不支持",
}

# 日志里命中关键字时补一句人话处置（同一次下载每条只提示一次）
ADVICE = [
    ("HTTP Error 412", "B站 被代理拦了，程序已强制直连，直接重试即可"),
    ("Requested format is not available",
     "YouTube 登录态触发 SABR-only，已自动去 Cookie 重试；仍失败请稍后再试"),
    ("HTTP Error 403", "多半是风控/限流：停手静置 5–10 分钟再试，连续重试只会延长窗口"),
    ("Read timed out", "网络超时：检查代理或稍后重试"),
    ("浏览器启动后立即退出",
     "常见原因是安全软件误拦（卡巴斯基 / 360 / 火绒 / Defender 等）或系统策略："
     "把本程序加入信任/白名单，或改用源码方式运行"),
    ("Cookie 为空", "先装扩展导出对应平台 Cookie，放到程序旁边"),
    ("/login", "Cookie 可能已过期（小红书常见），重新导出一次"),
]

# 首次运行引导用：状态存用户目录，别写 exe 旁边（Program Files 里不可写）
STATE_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "multiplatform-downloader"
STATE_FILE = STATE_DIR / "state.json"
EXT_SUBDIR = "cookie-export"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}          # 首次运行 / 文件损坏都当默认值，不打扰用户


def save_state(state: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass               # 状态存不下不影响主流程


def extension_source() -> Path | None:
    """源码运行取项目里的 extensions/；exe 运行取 PyInstaller 解包目录里的副本。"""
    bases = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        bases.append(Path(meipass))
    bases.append(BASE)
    for base in bases:
        p = (base / "extensions" / EXT_SUBDIR).resolve()
        if (p / "manifest.json").exists():
            return p
    return None


def install_extension() -> Path | None:
    """把扩展复制到用户目录（便于「加载解压缩的扩展」直接选中），返回该目录。"""
    src = extension_source()
    if src is None:
        return None
    dst = STATE_DIR / EXT_SUBDIR
    try:
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
        return dst
    except Exception as e:
        print(f"[!] 复制扩展失败：{e}")     # 不静默：引导窗口里能直接看到原因
        return None


def open_path(path) -> None:
    """用系统文件管理器打开目录：Windows 用 startfile，macOS/Linux 用 open/xdg-open。

    gui.py 主要在 Windows 跑，但源码方式也会有人在 Linux/macOS 试，os.startfile 在那边不存在。
    """
    try:
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        print(f"[!] 打开目录失败：{e}")


NOTES = (
    "1) Cookie 一般几周就会过期：B站掉 4K、小红书跳登录、抖音解析失败时，重新导出一次即可。\n"
    "2) 失败先别连点：抖音 / YouTube 的风控按「停手静置」恢复，连续重试只会延长封禁窗口。\n"
    "3) 抖音解析需要本机装有 Chrome 或 Edge 之一。若报「浏览器启动后立即退出」，"
    "多为安全软件误拦（卡巴斯基 / 360 / 火绒 / Defender 等）或系统策略："
    "把本程序加入信任/白名单，或改用源码方式运行。\n"
    "4) B站：无 Cookie 最高 1080P；4K / 1080P60 需大会员 Cookie。\n"
    "5) YouTube：国内网络需要代理（海外可直连）；不要导 Cookie —— 登录态会触发 SABR-only，"
    "只下发图片流导致下载失败，公开视频本来就不需要 Cookie。\n"
    "6) X 仅支持单条推文；Instagram 需 Cookie，国内网络还需要代理；两者主页批量都不支持。\n"
    "7) 同名文件已存在会自动跳过；下载历史最多保留 200 条。"
)
OUT_DIR = BASE / "downloads"
HISTORY_PATH = BASE / "history.json"
HISTORY_MAX = 200


def abbrev_path(path: Path) -> str:
    """路径缩写：超过两级时只显示最后两级，前面用 … 省略。
    完整路径通过悬停 tooltip 查看，避免长路径把右侧按钮挤没。"""
    parts = list(path.parts)
    if len(parts) <= 2:
        return str(path)
    return "…" + "\\" + "\\".join(parts[-2:])


def load_history() -> list[dict]:
    """读取下载历史（JSON，只存链接和时间，不存 Cookie）。"""
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_history(history: list[dict]) -> None:
    try:
        HISTORY_PATH.write_text(
            json.dumps(history[-HISTORY_MAX:], ensure_ascii=False, indent=1),
            encoding="utf-8")
    except OSError:
        pass


def latest_release() -> tuple[str, str] | None:
    """查 GitHub 最新 Release，返回 (版本号, 下载页URL)；网络失败返回 None。"""
    try:
        from curl_cffi import requests as cr
    except ImportError:
        return None
    for proxies in (None, PROXY_FALLBACK):
        try:
            r = cr.get(UPDATE_URL, impersonate="chrome", timeout=8,
                       headers={"User-Agent": "Mozilla/5.0",
                                "Accept": "application/vnd.github+json"},
                       proxies=proxies)
            j = r.json()
            tag = str(j.get("tag_name") or "").lstrip("v")
            if tag and j.get("html_url"):
                return tag, j["html_url"]
        except Exception:
            continue
    return None


def version_gt(a: str, b: str) -> bool:
    """a > b（按数字段比较，如 1.10.0 > 1.9.2）。"""
    pa = [int(x) for x in re.split(r"[^\d]+", a) if x.isdigit()]
    pb = [int(x) for x in re.split(r"[^\d]+", b) if x.isdigit()]
    return pa > pb


def _normalize_bili(raw: str) -> str:
    """把 B站 链接补成完整 http URL（裸 BV/av 号、裸 b23.tv 短链）。"""
    if raw.startswith(("BV", "av")):
        return f"https://www.bilibili.com/video/{raw}"
    if not raw.startswith("http"):
        return f"https://{raw}"
    return raw


def classify(text: str) -> tuple[str | None, str | None]:
    """识别链接属于哪个平台，返回 (平台, 处理用URL)；无法识别返回 (None, None)。"""
    m = douyin.URL_RE.search(text)
    if m:
        return "douyin", m.group(0).rstrip("/")
    m = BILI_RE.search(text)
    if m:
        return "bili", _normalize_bili(m.group(0).rstrip("/"))
    try:
        import youtube
        u = youtube.extract_url(text)
        if u:
            return "youtube", u
    except ImportError:
        pass
    try:
        import xhs
        m = xhs.URL_RE.search(text)
        if m:
            return "xhs", m.group(0).rstrip("/")
    except ImportError:
        pass
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
    return None, None


def classify_all(text: str) -> list[tuple[str, str]]:
    """识别文本里所有分享链接（跨平台），按出现顺序返回 [(平台, URL), ...]，去重。
    classify 只取第一个匹配，剪贴板里常含多条链接，这里用 finditer 全量遍历。"""
    pats: list[tuple[str, object]] = [("douyin", douyin.URL_RE), ("bili", BILI_RE)]
    for mod_name in ("xhs", "twitter", "instagram", "youtube"):
        try:
            pats.append((mod_name, __import__(mod_name).URL_RE))
        except ImportError:
            continue
    found: list[tuple[int, str, str]] = []
    for platform, pat in pats:
        for m in pat.finditer(text):
            url = m.group(0).rstrip("/")
            if platform == "bili":
                url = _normalize_bili(url)
            elif platform == "youtube":
                url = __import__("youtube").extract_url(url) or url
            found.append((m.start(), platform, url))
    found.sort(key=lambda t: t[0])                       # 按在文本里的位置排序，保持原顺序
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for _, platform, url in found:
        if (platform, url) not in seen:
            seen.add((platform, url))
            out.append((platform, url))
    return out


class _QueueWriter:
    """把 print 输出重定向进 GUI 日志队列（douyin.py 内部大量 print 用）。"""

    def __init__(self, q: queue.Queue):
        self.q = q
        self.advised: set[str] = set()      # 同一次下载内每条建议只提示一次

    def write(self, s: str) -> None:
        if not s.strip():
            return
        line = s.rstrip("\n")
        self.q.put(("log", line))
        for needle, tip in ADVICE:
            if needle in line and needle not in self.advised:
                self.advised.add(needle)
                self.q.put(("log", f"  💡 {tip}"))
                break

    def flush(self) -> None:
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: queue.Queue = queue.Queue()
        self._last_pct = ""
        self.out_dir = OUT_DIR
        self.history = load_history()
        root.title(f"抖音 / 小红书 / B站 / YouTube / X / Instagram 下载器 v{APP_VERSION}")
        root.geometry("580x600")
        root.minsize(480, 440)

        tk.Label(root, text="粘贴抖音 / 小红书 / B站 / YouTube / X / Instagram 分享链接（支持多行批量）：").pack(anchor="w", padx=10, pady=(10, 2))
        self.clip_bar = tk.Frame(root, bg="#fff3cd", cursor="hand2")   # 剪贴板识别提示条（初始隐藏）
        self.clip_label = tk.Label(self.clip_bar, text="", bg="#fff3cd", anchor="w",
                                   padx=4, pady=2, cursor="hand2")
        self.clip_label.pack(fill="x")
        self.clip_label.bind("<Button-1>", lambda e: self._use_clip())
        self.box = ttk.Frame(root)
        self.box.pack(fill="x", padx=10)
        self.input = tk.Text(self.box, height=5, font=("Consolas", 10))
        sb = ttk.Scrollbar(self.box, command=self.input.yview)
        self.input.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.input.pack(side="left", fill="both", expand=True)

        # 平台提示：随输入内容实时更新（识别到平台时给该平台的一句话注意事项）
        self.hint_var = tk.StringVar(value="")
        self.hint_label = tk.Label(root, textvariable=self.hint_var, anchor="w",
                                   justify="left", fg="#555", wraplength=545)
        self.hint_label.pack(fill="x", padx=10, pady=(4, 0))
        self.input.bind("<<Modified>>", self._on_input_modified)
        self._refresh_hint()

        self.btn = ttk.Button(root, text="开始下载", command=self.start)
        self.btn.pack(pady=6)

        prow = ttk.Frame(root)
        prow.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(prow, text="代理（YouTube / X / IG 国内网络需要，留空直连）：").pack(side="left")
        self.proxy_var = tk.StringVar()
        # 自动读 Windows 系统代理（Clash 等已开启「系统代理」时），填进代理框，可手动改/清空
        system_proxy = douyin.detect_system_proxy()
        if system_proxy:
            self.proxy_var.set(system_proxy)
        self.proxy_entry = ttk.Entry(prow, textvariable=self.proxy_var, width=30)
        self.proxy_entry.pack(side="left", fill="x", expand=True)

        yrow = ttk.Frame(root)
        yrow.pack(fill="x", padx=10)
        self.yt_playlist_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            yrow, text="YouTube：下载整个播放列表（默认单条）",
            variable=self.yt_playlist_var).pack(side="left")

        drow = ttk.Frame(root)
        drow.pack(fill="x", padx=10)
        ttk.Button(drow, text="历史", width=6,
                   command=self.open_history).pack(side="right", padx=(0, 6))
        ttk.Button(drow, text="说明", width=6,
                   command=self.show_notes).pack(side="right", padx=(0, 6))
        ttk.Button(drow, text="引导", width=6,
                   command=self.show_guide).pack(side="right", padx=(0, 6))
        ttk.Button(drow, text="选择目录", width=10,
                   command=self.choose_dir).pack(side="right")
        ttk.Button(drow, text="打开目录", width=10,
                   command=self.open_dir).pack(side="right", padx=(0, 6))
        self.dir_label = tk.Label(drow, text=f"文件保存到：{abbrev_path(self.out_dir)}",
                                  anchor="w", fg="#555")
        # 按钮先 pack（右侧优先占位），Label 再占剩余空间；路径用 abbrev_path 缩写，
        # 悬停 tooltip 显示完整路径，按钮和路径都始终完整可见。
        self.dir_label.pack(side="left", fill="x", expand=True)
        self._tooltip(self.dir_label, f"文件保存到：{self.out_dir}")

        logbox = ttk.Frame(root)
        logbox.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.log = tk.Text(logbox, height=18, state="disabled", font=("Consolas", 9))
        lsb = ttk.Scrollbar(logbox, command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        root.after(100, self._drain)
        self._welcome()
        threading.Thread(target=self._check_update, daemon=True).start()
        self._last_clip = ""                     # 剪贴板监听基线（空：首次轮询把当前剪贴板当新内容）
        self._pending_clip = None                # 待填入的链接
        root.after(500, self._poll_clipboard)

    # ---------- 保存目录 ----------
    def _tooltip(self, widget: tk.Widget, text: str) -> None:
        """悬停提示：无边框置顶小窗，用于显示缩写路径的完整值。"""
        tip = None
        def on_enter(e):
            nonlocal tip
            tip = tk.Toplevel(self.root)
            tip.wm_overrideredirect(True)
            tip.attributes("-topmost", True)
            tk.Label(tip, text=text, bg="#ffffe0", relief="solid", borderwidth=1,
                     font=("Consolas", 9)).pack()
            tip.wm_geometry(f"+{e.x_root + 12}+{e.y_root + 12}")
        def on_leave(e):
            nonlocal tip
            if tip is not None:
                tip.destroy()
                tip = None
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def choose_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=str(self.out_dir),
                                    title="选择保存目录")
        if d:
            self.out_dir = Path(d)
            self.dir_label.configure(text=f"文件保存到：{abbrev_path(self.out_dir)}")
            self._tooltip(self.dir_label, f"文件保存到：{self.out_dir}")

    def open_dir(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                open_path(self.out_dir)
            else:
                subprocess.Popen(["xdg-open", str(self.out_dir)])   # Linux
        except (AttributeError, OSError):
            # 没有图形环境或缺少 xdg-open 时退化为打印路径，不影响下载
            self._post(f"[*] 保存目录：{self.out_dir}")

    # ---------- 日志 ----------
    def _env_status(self) -> list[tuple[str, bool, str]]:
        """返回 [(项, 是否就绪, 处理建议)]，用于引导窗口；只检测、不猜。"""
        rows: list[tuple[str, bool, str]] = []
        rows.append(("抖音 Cookie（必需）", COOKIE_PATH.exists(),
                     f"已就绪：{COOKIE_PATH}" if COOKIE_PATH.exists()
                     else f"导出后放到：{BASE}\\douyin_cookies.txt"))
        rows.append(("B站 Cookie（可选）", BILI_COOKIE_PATH.exists(),
                     "已就绪，可选 4K / 1080P60" if BILI_COOKIE_PATH.exists()
                     else f"不装也能下 1080P；要 4K 就放到：{BASE}\\bilibili_cookies.txt"))
        try:
            import douyin_browser
            has_browser = douyin_browser.find_browser() is not None
        except Exception:
            has_browser = True
        rows.append(("Chrome / Edge（抖音解析用）", has_browser,
                     "已检测到浏览器" if has_browser
                     else "装 Chrome 或 Edge 任一个即可，不需要本程序自带的"))
        ff = _ffmpeg_location()
        rows.append(("ffmpeg（B站/YouTube 合并用）", ff is not None,
                     f"已找到：{ff}" if ff else "exe 版已内置；源码运行需自备 ffmpeg 放 ffmpeg 目录"))
        proxy = douyin.detect_system_proxy()
        rows.append(("系统代理（YouTube/X/IG 用）", bool(proxy),
                     f"已检测到：{proxy}" if proxy
                     else "国内网络下 YouTube / X / Instagram 需要代理；海外可直连"))
        return rows

    def _open_extensions_page(self) -> None:
        """打开浏览器的扩展管理页（顺带把 Edge/Chrome 都试一遍）。"""
        import subprocess
        targets = [
            (["msedge.exe", "edge://extensions"], "Edge"),
            (["chrome.exe", "chrome://extensions"], "Chrome"),
        ]
        for args, _name in targets:
            try:
                subprocess.Popen(args, shell=False)
                return
            except Exception:
                continue
        webbrowser.open("https://support.microsoft.com/microsoft-edge/add-or-remove-extensions")

    def show_guide(self, first_run: bool = False) -> None:
        """首次运行引导：一句话说清缺什么、点哪个按钮补上。"""
        win = tk.Toplevel(self.root)
        win.title("首次使用引导")
        win.geometry("620x480")
        win.transient(self.root)
        tk.Label(win, text=("先补两样东西：① 导出 Cookie 的扩展  ② 各平台 Cookie；"
                            "其余（浏览器 / ffmpeg / 代理）程序会自动检测。"),
                 wraplength=490, justify="left", anchor="w").pack(fill="x", padx=12, pady=(12, 6))

        box = tk.Frame(win)
        box.pack(fill="both", expand=True, padx=12)

        def render() -> None:
            for w in box.winfo_children():
                w.destroy()
            for name, ok, detail in self._env_status():
                row = tk.Frame(box)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=("✅" if ok else "❌"), width=2).pack(side="left", anchor="n")
                tk.Label(row, text=name, anchor="w", width=22,
                         fg="#1a7f37" if ok else "#b42318").pack(side="left", anchor="n")
                tk.Label(row, text=detail, anchor="w", justify="left",
                         wraplength=310, fg="#666").pack(side="left", fill="x", expand=True)

        def do_install() -> None:
            dst = install_extension()
            if dst is None:
                messagebox.showwarning(
                    "没找到扩展文件",
                    "本程序里没有内置 extensions/cookie-export。\n"
                    "请从仓库下载该项目目录后重试，或手动加载仓库里的扩展文件夹。", parent=win)
                return
            self._open_extensions_page()
            open_path(dst)
            messagebox.showinfo(
                "接下来两步",
                "1) 浏览器地址栏进 edge://extensions（Chrome 是 chrome://extensions）\n"
                "2) 打开右上角「开发者模式」→「加载解压缩的扩展」→ 选刚弹出的文件夹：\n"
                f"{dst}\n\n"
                "加载后到对应网站点扩展图标导出 Cookie，把 txt 放到本程序旁边，再点「重新检测」。",
                parent=win)
            render()

        btns = tk.Frame(win)
        btns.pack(fill="x", padx=12, pady=10)
        ttk.Button(btns, text="安装扩展（复制并打开目录）", command=do_install).pack(side="left")
        ttk.Button(btns, text="重新检测", command=render).pack(side="left", padx=6)
        ttk.Button(btns, text="说明", command=self.show_notes).pack(side="left")
        ttk.Button(btns, text="打开程序目录", command=lambda: open_path(BASE)).pack(side="left", padx=6)

        def close() -> None:
            st = load_state()
            st["onboarded"] = True
            save_state(st)
            win.destroy()

        ttk.Button(btns, text="关闭", command=close).pack(side="right")
        render()

    def _maybe_onboard(self) -> None:
        """首次运行且关键项缺失时才自动弹，别每次启动都烦人。"""
        st = load_state()
        if st.get("onboarded"):
            return
        missing = [name for name, ok, _ in self._env_status() if not ok]
        if missing:
            self._post(f"[*] 首次使用：还有 {len(missing)} 项没就绪，已打开引导窗口。")
            self.show_guide(first_run=True)

    def _on_input_modified(self, _event=None) -> None:
        if not self.input.edit_modified():
            return
        self.input.edit_modified(False)     # 复位，否则 <<Modified>> 只触发一次
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        """按输入内容 + Cookie 现况给一句提示：说清楚「现在缺什么、会有什么后果」。"""
        text = self.input.get("1.0", "end").strip()
        found = classify_all(text) if text else []
        if not found:
            self.hint_var.set("支持：抖音 / 小红书 / B站 / YouTube / X / Instagram。"
                              "粘贴分享链接后，这里会显示该平台的注意事项。")
            return
        platforms = []
        for platform, _ in found:
            if platform not in platforms:
                platforms.append(platform)
        if len(platforms) > 1:
            names = " / ".join(PLATFORM_NAMES.get(p, p) for p in platforms)
            self.hint_var.set(f"已识别 {len(found)} 条链接（{names}），将按顺序下载，每条间隔 2 秒防风控。")
            return

        p = platforms[0]
        name = PLATFORM_NAMES.get(p, p)
        status = ""
        if p == "douyin":
            status = ("（Cookie 已就绪）" if COOKIE_PATH.exists()
                      else f"（Cookie 缺失：把 douyin_cookies.txt 放到 {BASE}）")
        elif p == "bili":
            status = ("（大会员 Cookie 已就绪，可选 4K）" if BILI_COOKIE_PATH.exists()
                      else f"（无 Cookie，最高 1080P；把 bilibili_cookies.txt 放到 {BASE}）")
        elif p == "xhs":
            status = "（Cookie 已就绪）" if XHS_COOKIE_PATH.exists() else "（Cookie 缺失）"
        elif p == "twitter":
            status = "（Cookie 已就绪）" if TW_COOKIE_PATH.exists() else "（Cookie 缺失，匿名可能被登录墙挡）"
        elif p == "instagram":
            status = "（Cookie 已就绪）" if IG_COOKIE_PATH.exists() else "（Cookie 缺失）"
        elif p == "youtube" and YT_COOKIE_PATH.exists():
            status = "  ⚠️ 检测到 youtube_cookies.txt：登录态只下发图片流，建议移走"
        self.hint_var.set(f"{name}：{PLATFORM_HINTS.get(p, '')}{status}")

    def show_notes(self) -> None:
        messagebox.showinfo("注意事项（都是踩过的坑）", NOTES)

    def _welcome(self) -> None:
        self._post("=" * 44)
        self._post("  抖音 / 小红书 / B站 / YouTube / X / Instagram 下载器")
        self._post("=" * 44)
        if COOKIE_PATH.exists():
            cookie = douyin.load_cookie_str(str(COOKIE_PATH))
            self._post(f"[OK] 已找到抖音 Cookie（{len(cookie)} 字符）")
        else:
            self._post("[!] 未找到 douyin_cookies.txt —— 抖音下载不可用")
        # 可选 Cookie 合并成一行报告：缺哪个不影响启动，只影响那个平台的成功率
        optional = [
            (XHS_COOKIE_PATH, "xhs_cookies.txt"),
            (TW_COOKIE_PATH, "twitter_cookies.txt"),
            (IG_COOKIE_PATH, "instagram_cookies.txt"),
            (YT_COOKIE_PATH, "youtube_cookies.txt"),
        ]
        have = [name for path, name in optional if path.exists()]
        miss = [name for path, name in optional if not path.exists()]
        if have:
            self._post(f"[OK] 已找到可选 Cookie：{', '.join(have)}")
        if miss:
            self._post(f"[*] 未找到可选 Cookie（不影响启动，对应平台匿名跑）：{', '.join(miss)}")
        if YT_COOKIE_PATH.exists():
            self._post("[!] 检测到 youtube_cookies.txt：YouTube 登录态会只下发图片流（SABR-only），"
                       "下载会报「Requested format is not available」。公开视频请把它移走。")
        try:
            import douyin_browser
            has_browser = douyin_browser.find_browser() is not None
        except Exception:
            has_browser = True      # 检测失败时保持沉默，别误导用户
        if not has_browser:
            self._post("[!] 未检测到 Chrome / Edge：抖音解析需要其中之一（装好任一个即可）。")
        if _ffmpeg_location() is None:      # 与下载路径用同一个解析函数，exe 里指向 _MEIPASS/ffmpeg
            self._post("[!] 未找到 ffmpeg：B站 / YouTube 无法合并音视频（源码运行需自备；exe 版已内置）。")
        if not (COOKIE_PATH.exists() and XHS_COOKIE_PATH.exists()):
            self._post("    缺 Cookie 时先装浏览器扩展导出（支持三平台）：")
            self._post("    1. 压缩包内含 extensions\\cookie-export 文件夹")
            self._post("    2. Edge 打开 edge://extensions/ → 左下角「开发人员模式」")
            self._post("       （Chrome 用 chrome://extensions/）")
            self._post("    3. 「加载解压缩的扩展」→ 选 cookie-export 文件夹")
            self._post("    4. 打开对应网站并保持登录，点扩展图标导出")
            self._post("    5. 把下载的 cookies.txt 放到 exe 旁边，重启本程序")
        self._post(f"[*] 文件将保存到：{self.out_dir}")
        self._post(f"[*] 历史记录：{len(self.history)} 条（点「历史」查看）")
        self._post(f"[*] 当前版本 v{APP_VERSION}，启动时自动检查更新")
        self.root.after(600, self._maybe_onboard)
        self._post("")

    # ---------- 更新检查 ----------
    def _check_update(self) -> None:
        """后台查最新 Release；有新版本时把提示放进队列，由主线程弹窗。"""
        try:
            found = latest_release()
            if found and version_gt(found[0], APP_VERSION):
                self.q.put(("update", (found[0], found[1])))
        except Exception:
            pass

    # ---------- 下载历史 ----------
    def _add_history(self, platform: str, url: str, ok: bool) -> None:
        self.history.append({
            "time": datetime.now().strftime("%m-%d %H:%M:%S"),
            "platform": platform,
            "url": url[:100],
            "ok": ok,
        })
        if len(self.history) > HISTORY_MAX:
            self.history = self.history[-HISTORY_MAX:]
        save_history(self.history)

    def open_history(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("下载历史")
        win.geometry("580x380")
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        cols = ("time", "platform", "url", "ok")
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        tree.heading("time", text="时间")
        tree.heading("platform", text="平台")
        tree.heading("url", text="链接")
        tree.heading("ok", text="结果")
        tree.column("time", width=110, anchor="w")
        tree.column("platform", width=64, anchor="center")
        tree.column("url", width=330, anchor="w")
        tree.column("ok", width=44, anchor="center")
        sb = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        for item in reversed(self.history):
            tree.insert("", "end", values=(
                item.get("time", ""), item.get("platform", ""),
                item.get("url", ""), "✓" if item.get("ok") else "✗"))

        def clear() -> None:
            self.history = []
            save_history(self.history)
            for i in tree.get_children():
                tree.delete(i)

        ttk.Button(win, text="清空历史", command=clear).pack(pady=(0, 8))

    def _post(self, msg: str = "") -> None:
        self.q.put(("log", msg))

    def _drain(self) -> None:
        try:
            while True:
                kind, msg = self.q.get_nowait()
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", msg + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "done":
                    self.btn.configure(state="normal")
                elif kind == "update":
                    tag, url = msg
                    if messagebox.askyesno(
                            "发现新版本",
                            f"本地版本 v{APP_VERSION}，GitHub 最新 v{tag}\n\n"
                            "本地 exe 版本落后才会提示更新。\n"
                            "若你刚改了代码，请先升版本号并重新打包，否则会重复提示。\n\n"
                            "是否前往 GitHub 下载最新版？"):
                        webbrowser.open(url)
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    # ---------- 剪贴板监听 ----------
    def _poll_clipboard(self) -> None:
        """主线程轮询剪贴板，检测到新链接时显示提示条（tkinter 剪贴板只能在主线程访问）。"""
        try:
            clip = (self.root.clipboard_get() or "").strip()
        except tk.TclError:
            clip = ""
        if clip and clip != self._last_clip:
            self._last_clip = clip
            urls = classify_all(clip)                    # 遍历全部链接，不只取第一个
            if urls:
                self._pending_clip = urls
                self.clip_label.configure(text=f"📋 检测到 {len(urls)} 条分享链接，点击填入")
                self.clip_bar.pack(fill="x", padx=10, before=self.box)
            else:
                self._pending_clip = None
                self.clip_bar.pack_forget()
        self.root.after(500, self._poll_clipboard)

    def _use_clip(self) -> None:
        """点击提示条：把识别到的所有链接追加进输入框。"""
        urls = self._pending_clip
        if not urls:
            self.clip_bar.pack_forget()
            return
        cur = self.input.get("1.0", "end").strip()
        joined = "\n".join(u for _, u in urls)
        self.input.delete("1.0", "end")
        self.input.insert("1.0", (cur + "\n" + joined).strip())
        self._pending_clip = None
        self.clip_bar.pack_forget()
        self._post(f"[+] 已加入 {len(urls)} 条链接")

    # ---------- 下载 ----------
    def start(self) -> None:
        text = self.input.get("1.0", "end").strip()
        if not text:
            self._post("[!] 请先粘贴链接。")
            return
        self.btn.configure(state="disabled")
        threading.Thread(target=self._run, args=(text,), daemon=True).start()

    def _run(self, text: str) -> None:
        old = sys.stdout
        sys.stdout = _QueueWriter(self.q)
        sys.stdout.advised.clear()          # 新一轮下载，建议重新提示
        try:
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            fail = 0
            for i, line in enumerate(lines):
                self._post(f"\n[*] 处理：{line[:60]}")
                platform, url = classify(line)
                if not platform:
                    self._post("  [!] 无法识别链接")
                    fail += 1
                    continue
                try:
                    if platform == "douyin":
                        ok = self._run_douyin(url)
                    elif platform == "xhs":
                        ok = self._run_xhs(url)
                    elif platform == "twitter":
                        ok = self._run_twitter(url)
                    elif platform == "instagram":
                        ok = self._run_instagram(url)
                    elif platform == "youtube":
                        ok = self._run_youtube(url)
                    else:
                        ok = self._run_bili(url)
                except Exception as e:
                    self._post(f"  [!] 出错：{e}")
                    ok = False
                self._add_history(platform, url, ok)
                if not ok:
                    fail += 1
                if i < len(lines) - 1:
                    time.sleep(2)    # 多条链接间限速，避免背靠背打抖音 detail 触发风控(CLI main 同理)
            if fail:
                self._post(f"\n[!] {fail}/{len(lines)} 条失败，见上方出错信息")
            else:
                self._post("\n[✓] 全部完成")
        finally:
            sys.stdout = old
            self.q.put(("done", ""))

    def _run_douyin(self, url: str) -> bool:
        cookie = (douyin.load_cookie_str(str(COOKIE_PATH), host="www.douyin.com")
                  if COOKIE_PATH.exists() else "")
        if not cookie:
            self._post("  [!] Cookie 为空，跳过（先导出 douyin_cookies.txt）")
            return False
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return douyin.process(url, self.out_dir, douyin.make_session(cookie))

    def _run_xhs(self, url: str) -> bool:
        try:
            import xhs
        except ImportError as e:
            self._post(f"  [!] 小红书依赖缺失（curl_cffi）：{e}")
            return False
        cookie = (douyin.load_cookie_str(str(XHS_COOKIE_PATH))
                  if XHS_COOKIE_PATH.exists() else "")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return xhs.process(url, self.out_dir, cookie)

    def _run_bili(self, url: str) -> bool:
        import yt_dlp
        self.out_dir.mkdir(parents=True, exist_ok=True)
        opts = {
            "no_playlist": True,
            "format": "bv*[vcodec^=avc1]+ba[ext=m4a]/bv*+ba/b",
            "outtmpl": str(self.out_dir / "%(title)s [%(id)s].%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._bili_hook],
            # B站是国内站，走系统代理（海外节点）会被 412 拦；强制直连
            "proxy": "",
        }
        tmp_dir = None
        if BILI_COOKIE_PATH.exists():
            # yt-dlp 退出会把 cookiejar 写回 cookiefile，直接传导出文件会被改写，必须传临时副本
            tmp_dir, tmp_ck = douyin.temp_cookie_copy(str(BILI_COOKIE_PATH))
            if tmp_ck is not None:
                opts["cookiefile"] = str(tmp_ck)
        ffmpeg = _ffmpeg_location()
        if ffmpeg is not None:
            opts["ffmpeg_location"] = str(ffmpeg)
        else:
            self._post("  [!] 未找到 ffmpeg，B站将无法合并音视频")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
        self._post("  [✓] B站下载完成")
        return True

    def _run_twitter(self, url: str) -> bool:
        try:
            import twitter
        except ImportError as e:
            self._post(f"  [!] X 依赖缺失（yt-dlp）：{e}")
            return False
        cookie = str(TW_COOKIE_PATH) if TW_COOKIE_PATH.exists() else ""
        proxy = self.proxy_var.get().strip()
        return twitter.process(url, self.out_dir, cookie_path=cookie, proxy=proxy)

    def _run_youtube(self, url: str) -> bool:
        try:
            import youtube
        except ImportError as e:
            self._post(f"  [!] YouTube 依赖缺失（yt-dlp）：{e}")
            return False
        cookie = str(YT_COOKIE_PATH) if YT_COOKIE_PATH.exists() else ""
        return youtube.process(url, self.out_dir, cookie_path=cookie,
                               proxy=self.proxy_var.get().strip(),
                               playlist=self.yt_playlist_var.get())

    def _run_instagram(self, url: str) -> bool:
        try:
            import instagram
        except ImportError as e:
            self._post(f"  [!] Instagram 依赖缺失（yt-dlp）：{e}")
            return False
        cookie = str(IG_COOKIE_PATH) if IG_COOKIE_PATH.exists() else ""
        proxy = self.proxy_var.get().strip()
        return instagram.process(url, self.out_dir, cookie_path=cookie, proxy=proxy)

    def _bili_hook(self, d: dict) -> None:
        if d.get("status") == "downloading":
            pct = ANSI_RE.sub("", d.get("_percent_str", "")).strip()
            if pct != self._last_pct:            # 只显示百分比变化，避免刷屏
                self._last_pct = pct
                spd = ANSI_RE.sub("", d.get("_speed_str", "")).strip()
                eta = ANSI_RE.sub("", d.get("_eta_str", "")).strip()
                self._post(f"  {pct} {spd} {eta}".rstrip())
        elif d.get("status") == "finished":
            self._post(f"  已下载：{Path(d.get('filename', '')).name}")


def main() -> None:
    try:
        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception:
        import traceback
        with open(BASE / "error.log", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        try:
            messagebox.showerror("出错", f"程序运行出错，详情见 error.log：\n{BASE / 'error.log'}")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
