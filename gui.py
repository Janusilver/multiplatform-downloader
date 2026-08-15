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
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import douyin

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
OUT_DIR = BASE / "downloads"
HISTORY_PATH = BASE / "history.json"
HISTORY_MAX = 200


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
        root.title("抖音 / 小红书 / 快手 / B站 下载器")
        root.geometry("580x600")
        root.minsize(480, 440)

        tk.Label(root, text="粘贴抖音 / 小红书 / 快手 / B站分享链接（支持多行批量）：").pack(anchor="w", padx=10, pady=(10, 2))
        box = ttk.Frame(root)
        box.pack(fill="x", padx=10)
        self.input = tk.Text(box, height=5, font=("Consolas", 10))
        sb = ttk.Scrollbar(box, command=self.input.yview)
        self.input.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.input.pack(side="left", fill="both", expand=True)

        self.btn = ttk.Button(root, text="开始下载", command=self.start)
        self.btn.pack(pady=6)

        drow = ttk.Frame(root)
        drow.pack(fill="x", padx=10)
        self.dir_label = tk.Label(drow, text=f"文件保存到：{self.out_dir}",
                                  anchor="w", fg="#555")
        self.dir_label.pack(side="left")
        ttk.Button(drow, text="历史", width=6,
                   command=self.open_history).pack(side="right", padx=(0, 6))
        ttk.Button(drow, text="选择目录", width=10,
                   command=self.choose_dir).pack(side="right")
        ttk.Button(drow, text="打开目录", width=10,
                   command=self.open_dir).pack(side="right", padx=(0, 6))

        logbox = ttk.Frame(root)
        logbox.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.log = tk.Text(logbox, height=18, state="disabled", font=("Consolas", 9))
        lsb = ttk.Scrollbar(logbox, command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        root.after(100, self._drain)
        self._welcome()

    # ---------- 保存目录 ----------
    def choose_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=str(self.out_dir),
                                    title="选择保存目录")
        if d:
            self.out_dir = Path(d)
            self.dir_label.configure(text=f"文件保存到：{self.out_dir}")

    def open_dir(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(self.out_dir))          # Windows
        except AttributeError:
            self._post(f"[*] 保存目录：{self.out_dir}")

    # ---------- 日志 ----------
    def _welcome(self) -> None:
        self._post("=" * 44)
        self._post("  抖音 / 小红书 / 快手 / B站 下载器")
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
        self._post("")

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
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

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
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                self._post(f"\n[*] 处理：{line[:60]}")
                platform, url = classify(line)
                if not platform:
                    self._post("  [!] 无法识别链接")
                    continue
                ok = True
                try:
                    if platform == "douyin":
                        self._run_douyin(url)
                    elif platform == "xhs":
                        self._run_xhs(url)
                    elif platform == "kuaishou":
                        self._run_kuaishou(url)
                    else:
                        self._run_bili(url)
                except Exception as e:
                    self._post(f"  [!] 出错：{e}")
                    ok = False
                self._add_history(platform, url, ok)
            self._post("\n[✓] 全部完成")
        finally:
            sys.stdout = old
            self.q.put(("done", ""))

    def _run_douyin(self, url: str) -> None:
        cookie = douyin.load_cookie_str(str(COOKIE_PATH))
        if not cookie:
            self._post("  [!] Cookie 为空，跳过（先导出 douyin_cookies.txt）")
            return
        self.out_dir.mkdir(parents=True, exist_ok=True)
        douyin.process(url, self.out_dir, douyin.make_session(cookie))

    def _run_xhs(self, url: str) -> None:
        try:
            import xhs
        except ImportError as e:
            self._post(f"  [!] 小红书依赖缺失（curl_cffi）：{e}")
            return
        cookie = (douyin.load_cookie_str(str(XHS_COOKIE_PATH))
                  if XHS_COOKIE_PATH.exists() else "")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        xhs.process(url, self.out_dir, cookie)

    def _run_kuaishou(self, url: str) -> None:
        try:
            import kuaishou
        except ImportError as e:
            self._post(f"  [!] 快手依赖缺失（curl_cffi）：{e}")
            return
        cookie = (douyin.load_cookie_str(str(KS_COOKIE_PATH))
                  if KS_COOKIE_PATH.exists() else "")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        kuaishou.process(url, self.out_dir, cookie)

    def _run_bili(self, url: str) -> None:
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
