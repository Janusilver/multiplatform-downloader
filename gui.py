#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音 / 小红书 / 快手 / B站 下载器（tkinter GUI，PyInstaller 打包 exe 用）
抖音复用 douyin.py；小红书/快手分别复用 xhs.py / kuaishou.py；
B站走 yt-dlp（用便携 ffmpeg 合并音视频）。
文件与 Cookie 均以 exe 所在目录为基准，双击即可用。
"""
from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import douyin

APP_VERSION = "1.3.4"
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

COOKIE_PATH = BASE / "douyin_cookies.txt"
XHS_COOKIE_PATH = BASE / "xhs_cookies.txt"
KS_COOKIE_PATH = BASE / "kuaishou_cookies.txt"
TW_COOKIE_PATH = BASE / "twitter_cookies.txt"
IG_COOKIE_PATH = BASE / "instagram_cookies.txt"
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


def classify(text: str) -> tuple[str | None, str | None]:
    """识别链接属于哪个平台，返回 (平台, 处理用URL)；无法识别返回 (None, None)。"""
    m = douyin.URL_RE.search(text)
    if m:
        return "douyin", m.group(0).rstrip("/")
    m = BILI_RE.search(text)
    if m:
        raw = m.group(0).rstrip("/")
        if raw.startswith(("BV", "av")):               # 裸 BV/av 号补全
            raw = f"https://www.bilibili.com/video/{raw}"
        elif not raw.startswith("http"):               # 裸 b23.tv 短链补全
            raw = f"https://{raw}"
        return "bili", raw
    try:
        import xhs
        m = xhs.URL_RE.search(text)
        if m:
            return "xhs", m.group(0).rstrip("/")
    except ImportError:
        pass
    try:
        import kuaishou
        m = kuaishou.URL_RE.search(text)
        if m:
            return "kuaishou", m.group(0).rstrip("/")
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


class _QueueWriter:
    """把 print 输出重定向进 GUI 日志队列（douyin.py 内部大量 print 用）。"""

    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s: str) -> None:
        if s.strip():
            self.q.put(("log", s.rstrip("\n")))

    def flush(self) -> None:
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: queue.Queue = queue.Queue()
        self._last_pct = ""
        self.out_dir = OUT_DIR
        self.history = load_history()
        root.title(f"抖音 / 小红书 / 快手 / B站 / X / Instagram 下载器 v{APP_VERSION}")
        root.geometry("580x600")
        root.minsize(480, 440)

        tk.Label(root, text="粘贴抖音 / 小红书 / 快手 / B站分享链接（支持多行批量）：").pack(anchor="w", padx=10, pady=(10, 2))
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

        self.btn = ttk.Button(root, text="开始下载", command=self.start)
        self.btn.pack(pady=6)

        prow = ttk.Frame(root)
        prow.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(prow, text="代理（X/IG 建议填写，留空直连）：").pack(side="left")
        self.proxy_var = tk.StringVar()
        # 自动读 Windows 系统代理（Clash 等已开启「系统代理」时），填进代理框，可手动改/清空
        system_proxy = douyin.detect_system_proxy()
        if system_proxy:
            self.proxy_var.set(system_proxy)
        self.proxy_entry = ttk.Entry(prow, textvariable=self.proxy_var, width=30)
        self.proxy_entry.pack(side="left", fill="x", expand=True)

        drow = ttk.Frame(root)
        drow.pack(fill="x", padx=10)
        ttk.Button(drow, text="历史", width=6,
                   command=self.open_history).pack(side="right", padx=(0, 6))
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
            os.startfile(str(self.out_dir))          # Windows
        except AttributeError:
            self._post(f"[*] 保存目录：{self.out_dir}")

    # ---------- 日志 ----------
    def _welcome(self) -> None:
        self._post("=" * 44)
        self._post("  抖音 / 小红书 / 快手 / B站 / X / Instagram 下载器")
        self._post("=" * 44)
        if COOKIE_PATH.exists():
            cookie = douyin.load_cookie_str(str(COOKIE_PATH))
            self._post(f"[OK] 已找到抖音 Cookie（{len(cookie)} 字符）")
        else:
            self._post("[!] 未找到 douyin_cookies.txt —— 抖音下载不可用")
        if XHS_COOKIE_PATH.exists():
            self._post(f"[OK] 已找到小红书 Cookie（可选，登录后更稳）")
        else:
            self._post("[!] 未找到 xhs_cookies.txt —— 小红书匿名可用，可能被风控")
        if KS_COOKIE_PATH.exists():
            self._post(f"[OK] 已找到快手 Cookie（可选，登录后更稳）")
        else:
            self._post("[!] 未找到 kuaishou_cookies.txt —— 快手匿名可用")
        if TW_COOKIE_PATH.exists():
            self._post(f"[OK] 已找到 X Cookie（可选，匿名可能失败）")
        else:
            self._post("[!] 未找到 twitter_cookies.txt —— X 匿名可用，可能被登录墙挡住")
        if IG_COOKIE_PATH.exists():
            self._post(f"[OK] 已找到 Instagram Cookie（可选，匿名大概率失败）")
        else:
            self._post("[!] 未找到 instagram_cookies.txt —— IG 匿名大概率失败")
        if not (COOKIE_PATH.exists() and XHS_COOKIE_PATH.exists() and KS_COOKIE_PATH.exists()):
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
            platform, url = classify(clip)
            if url:
                self._pending_clip = url
                name = {"douyin": "抖音", "xhs": "小红书", "kuaishou": "快手", "bili": "B站",
                        "twitter": "X", "instagram": "Instagram"}.get(platform, "分享")
                self.clip_label.configure(text=f"📋 检测到{name}分享链接，点击填入")
                self.clip_bar.pack(fill="x", padx=10, before=self.box)
            else:
                self._pending_clip = None
                self.clip_bar.pack_forget()
        self.root.after(500, self._poll_clipboard)

    def _use_clip(self) -> None:
        """点击提示条：把识别到的链接追加进输入框。"""
        url = self._pending_clip
        if not url:
            self.clip_bar.pack_forget()
            return
        cur = self.input.get("1.0", "end").strip()
        self.input.delete("1.0", "end")
        self.input.insert("1.0", (cur + "\n" + url).strip())
        self._pending_clip = None
        self.clip_bar.pack_forget()
        self._post(f"[+] 已加入链接：{url[:60]}")

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
        try:
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            fail = 0
            for line in lines:
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
                    elif platform == "kuaishou":
                        ok = self._run_kuaishou(url)
                    elif platform == "twitter":
                        ok = self._run_twitter(url)
                    elif platform == "instagram":
                        ok = self._run_instagram(url)
                    else:
                        ok = self._run_bili(url)
                except Exception as e:
                    self._post(f"  [!] 出错：{e}")
                    ok = False
                self._add_history(platform, url, ok)
                if not ok:
                    fail += 1
            if fail:
                self._post(f"\n[!] {fail}/{len(lines)} 条失败，见上方出错信息")
            else:
                self._post("\n[✓] 全部完成")
        finally:
            sys.stdout = old
            self.q.put(("done", ""))

    def _run_douyin(self, url: str) -> bool:
        cookie = (douyin.load_cookie_str(str(COOKIE_PATH))
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

    def _run_kuaishou(self, url: str) -> bool:
        try:
            import kuaishou
        except ImportError as e:
            self._post(f"  [!] 快手依赖缺失（curl_cffi）：{e}")
            return False
        cookie = (douyin.load_cookie_str(str(KS_COOKIE_PATH))
                  if KS_COOKIE_PATH.exists() else "")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return kuaishou.process(url, self.out_dir, cookie)

    def _run_bili(self, url: str) -> bool:
        import yt_dlp
        self.out_dir.mkdir(parents=True, exist_ok=True)
        opts = {
            "no_playlist": True,
            "format": "bv*+ba/b",
            "outtmpl": str(self.out_dir / "%(title)s [%(id)s].%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._bili_hook],
        }
        if FFMPEG_DIR.joinpath("ffmpeg.exe").exists():
            opts["ffmpeg_location"] = str(FFMPEG_DIR)
        else:
            self._post("  [!] 未找到便携 ffmpeg，B站将无法合并音视频")
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
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
