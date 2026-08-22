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
