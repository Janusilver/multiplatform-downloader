#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X (Twitter) 单条推文 下载器（yt-dlp 封装）
==========================================
流程：识别链接 → 交给 yt-dlp（cookies + 可选代理）→ 下载到输出目录。
X 媒体为平台原始 CDN 直链，天然无水印。
依赖：yt-dlp（已装 .venv）
用法：
  python twitter.py "https://x.com/user/status/123"          # 单条推文
  python twitter.py "链接" -o 目录 --proxy http://127.0.0.1:7890
注意：X **用户主页批量暂不支持**（yt-dlp 无主页提取器，只能下 /status/ID 单条）。
Cookie（可选，无则匿名试一次）：浏览器扩展导出 twitter_cookies.txt 放脚本目录。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yt_dlp

import douyin

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
    r"|(?!" + _SYSTEM_PATH + r")[A-Za-z0-9_][A-Za-z0-9_]{0,14})"  # 用户主页
)
SINGLE_RE = re.compile(r"https?://(?:x\.com|twitter\.com)/[A-Za-z0-9_]{1,15}/status/\d+")


def extract_url(text: str) -> str | None:
    m = URL_RE.search(text)
    return m.group(0).rstrip("/") if m else None


def is_profile(url: str) -> bool:
    """True=用户主页（批量），False=单条推文。URL 已 rstrip('/')。"""
    return bool(URL_RE.fullmatch(url)) and not SINGLE_RE.search(url)


def process(url: str, out_dir: Path, cookie_path: str | None = None,
            proxy: str = "", max_items: int = 50) -> bool:
    """下载单条推文。X 用户主页批量 yt-dlp 不支持，明确提示局限。out_dir 需已存在。
    成功（有文件落地）返回 True，失败/不支持返回 False。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    if is_profile(url):
        print("  [!] X 主页批量暂不支持：yt-dlp 只能下载单条推文（/status/ID）。")
        print("      请粘贴具体推文链接，例如 https://x.com/用户名/status/12345")
        return False
    # 单条推文：作者名_推文ID.ext。不带 playlist_index（单条时它变 NA，污染文件名）
    tmpl = "%(uploader)s_%(id)s.%(ext)s"
    opts: dict = {
        "outtmpl": str(out_dir / tmpl),
        "quiet": True,
        "no_warnings": True,
        "nooverwrites": True,          # 已存在的文件跳过，不重复下
    }
    cookie_tmp_dir: str | None = None
    if cookie_path and Path(cookie_path).exists():
        # yt-dlp 退出时会把更新后的 cookiejar 写回 cookiefile：直接用用户的导出文件会被改动，
        # 文件被占用/只读时还会抛 PermissionError（实测 Downloads 里的导出文件就踩过）。
        # 拷一份到临时目录交给它写，退出时删掉。
        cookie_tmp_dir = tempfile.mkdtemp(prefix="dydl-x-cookie-")
        cookie_tmp = Path(cookie_tmp_dir) / "cookies.txt"
        shutil.copyfile(cookie_path, cookie_tmp)
        opts["cookiefile"] = str(cookie_tmp)   # Netscape 格式，扩展导出即用
    if not proxy:
        proxy = douyin.detect_system_proxy()
        if proxy:
            print(f"  [*] 检测到系统代理：{proxy}")
    if proxy:
        if "://" not in proxy:                   # yt-dlp 要求带 scheme
            proxy = "http://" + proxy
        opts["proxy"] = proxy
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        print(f"  [✓] 已保存 → {out_dir}")
        return True
    except yt_dlp.utils.DownloadError as e:
        hint = "" if cookie_path else "（无 Cookie，若失败请导 twitter_cookies.txt 后重试）"
        print(f"  [!] 下载失败{hint}: {str(e).splitlines()[0]}")
        return False
    finally:
        if cookie_tmp_dir:
            shutil.rmtree(cookie_tmp_dir, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="X (Twitter) 单条推文下载器（yt-dlp；主页批量暂不支持）")
    ap.add_argument("input", help="推文链接，或含链接的文本")
    ap.add_argument("-o", "--output", default=None, help="保存目录（默认：脚本目录/downloads）")
    ap.add_argument("-c", "--cookie", default="twitter_cookies.txt", help="Cookie 文件路径（可缺省，匿名试一次）")
    ap.add_argument("--proxy", default="", help="代理地址，如 http://127.0.0.1:7890（默认直连）")
    ap.add_argument("--max", type=int, default=50, help="保留参数（主页批量暂不支持，忽略）")
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
