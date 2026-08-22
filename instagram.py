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

# Windows 默认 GBK 控制台打不出 ✓ 等字符会 UnicodeEncodeError，强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

_SYSTEM_PATH = r"(?:p/|reel/|tv/|stories/|accounts/|direct/|explore/|about/|help/|web/|static/)"
URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:p/[A-Za-z0-9_-]+"                                        # 帖子
    r"|reel/[A-Za-z0-9_-]+"                                       # Reels
    r"|tv/[A-Za-z0-9_-]+"                                         # IGTV
    r"|(?!" + _SYSTEM_PATH + r")[A-Za-z0-9_][A-Za-z0-9_.]{0,29})"  # 用户主页
)
SINGLE_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[A-Za-z0-9_-]+")


def extract_url(text: str) -> str | None:
    m = URL_RE.search(text)
    return m.group(0).rstrip("/") if m else None


def is_profile(url: str) -> bool:
    """True=用户主页（批量），False=单条帖子/Reels。URL 已 rstrip('/')。"""
    return bool(URL_RE.fullmatch(url)) and not SINGLE_RE.search(url)
