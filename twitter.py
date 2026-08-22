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
