#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instagram 单条帖子/Reels / 用户主页 下载器（IG 私有 API 自研）
=============================================================
流程：shortcode → pk → i.instagram.com/api/v1/media/{pk}/info/ 拿完整媒体数据，
      carousel 图集里**图片(image_versions2.candidates 原图)+视频(video_versions)** 全部提取；
      用户主页走 feed/user/{uid} 分页拉取所有帖子，同样全媒体提取。
依赖：requests + douyin（复用 UA / load_cookie_str / sanitize / MIME_EXT）
Cookie（必需）：浏览器扩展导出 instagram_cookies.txt 放脚本目录（IG 匿名拿不到数据）。
用法：
  python instagram.py "https://www.instagram.com/p/CxAb12345/"    # 单条帖子（图集全提取）
  python instagram.py "https://www.instagram.com/reel/CxAb12345/" # Reels
  python instagram.py "https://www.instagram.com/user/"           # 主页批量（默认最近 50 条）
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import requests
from curl_cffi import requests as cr   # IG API 对 requests TLS 指纹风控（429），需伪装 Chrome

import douyin

# Windows 默认 GBK 控制台打不出 ✓ 等字符会 UnicodeEncodeError，强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

_API = "https://i.instagram.com/api/v1"
_APP_ID = "936619743392459"          # web app id，IG 私有 API 必需
_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'

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


def _shortcode_to_pk(shortcode: str) -> int:
    """IG shortcode（短码）是 base64（_CHARS 表）编码的数字媒体 id。"""
    n = 0
    for ch in shortcode:
        n = n * 64 + _CHARS.index(ch)
    return n


def _get_json(url: str, cookie: str, proxy: str = "", params: dict | None = None,
              extra: dict | None = None) -> dict:
    headers = {
        "X-IG-App-ID": _APP_ID,
        "User-Agent": douyin.UA,
        "Accept": "*/*",
        "Origin": "https://www.instagram.com",
        "Cookie": cookie,
    }
    if extra:
        headers.update(extra)
    # IG API 对 requests TLS 指纹风控（429），必须 curl_cffi 伪装 Chrome。
    # proxy 通过 curl_cffi 的 proxy 参数传（不带协议前缀 scheme 会报错，需补 http://）
    proxy_arg = None
    if proxy:
        proxy_arg = proxy if "://" in proxy else "http://" + proxy
    r = cr.get(url, headers=headers, params=params, proxy=proxy_arg,
               impersonate="chrome", timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_media_info(shortcode: str, cookie: str, proxy: str = "") -> dict:
    """单条帖子完整数据（items[0]）。"""
    pk = _shortcode_to_pk(shortcode)
    info = _get_json(f"{_API}/media/{pk}/info/", cookie, proxy)
    items = info.get("items") or []
    if not items:
        raise ValueError("帖子数据为空（可能已删除或私密）")
    return items[0]


def fetch_user_items(username: str, cookie: str, proxy: str = "", max_items: int = 50) -> list:
    """用户主页分页拉取帖子。先 web_profile_info 拿 uid，再 feed/user 翻页。"""
    # web_profile_info 需要完整浏览器头（X-Requested-With + Referer），朴素头会被 429 风控
    info = _get_json(f"{_API}/users/web_profile_info/?username={username}", cookie, proxy,
                     extra={"X-Requested-With": "XMLHttpRequest",
                            "Referer": f"https://www.instagram.com/{username}/"})
    uid = (info.get("data") or {}).get("user", {}).get("id")
    if not uid:
        raise ValueError(f"拿不到用户 @{username} 的信息（确认用户名正确、Cookie 有效）")
    items: list = []
    max_id = None
    while len(items) < max_items:
        params = {"count": 12}
        if max_id:
            params["max_id"] = max_id
        feed = _get_json(f"{_API}/feed/user/{uid}/", cookie, proxy, params=params)
        page = feed.get("items") or []
        if not page:
            break
        items.extend(page)
        max_id = feed.get("next_max_id")
        if not max_id:
            break
    return items[:max_items]


def extract_media(item: dict) -> list[tuple[str, str]]:
    """从单条帖子 item 提取全部媒体，递归处理图集。返回 [(kind, url)]，kind: 'image'/'video'。"""
    out: list = []
    media_type = item.get("media_type")        # 1=图 2=视频 8=图集
    if media_type == 8:
        for cm in item.get("carousel_media") or []:
            out.extend(extract_media(cm))
    elif media_type == 2:
        versions = item.get("video_versions") or []
        if versions:
            best = max(versions, key=lambda v: (v.get("width") or 0) * (v.get("height") or 0))
            out.append(("video", best["url"]))
    else:
        candidates = (item.get("image_versions2") or {}).get("candidates") or []
        if candidates:
            best = max(candidates, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0))
            out.append(("image", best["url"]))
    return out


def _download(url: str, dest: Path, kind: str, proxy: str = "") -> tuple[bool, str]:
    """图片只带 UA；视频带 Referer（IG CDN 在海外，必须走代理）。"""
    headers = {"User-Agent": douyin.UA}
    if kind == "video":
        headers["Referer"] = "https://www.instagram.com/"
    proxies = {"http": proxy, "https": proxy} if proxy else None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, proxies=proxies, stream=True, timeout=(10, 120))
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "").split(";")[0].lower()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    if chunk:
                        f.write(chunk)
            if os.path.getsize(dest) == 0:
                raise ValueError("空文件（可能被限流）")
            return True, ctype
        except Exception as e:
            print(f"  [!] {dest.name} 第{attempt + 1}次下载失败: {e}")
            time.sleep(2 * (attempt + 1))
    return False, ""


def _download_one(item: dict, out_dir: Path, prefix: str = "", proxy: str = "") -> bool:
    """下载一个帖子的全部媒体（图片+视频）。prefix 用于单条命名（作者），主页批量子目录内为空。
    至少下到 1 个文件返回 True，无媒体或全部失败返回 False。"""
    media = extract_media(item)
    shortcode = item.get("code") or item.get("pk") or "post"
    if not media:
        print(f"  [!] 帖子 {shortcode} 没有可提取的媒体")
        return False
    n_img = sum(1 for k, _ in media if k == "image")
    n_vid = sum(1 for k, _ in media if k == "video")
    print(f"  [*] {shortcode}: {len(media)} 个媒体（{n_img} 图 + {n_vid} 视频）")
    got = 0
    for idx, (kind, url) in enumerate(media, 1):
        # 不用 Path.with_suffix：作者名含点（如 xx.uyvn）时它会把点后全当扩展名替换，
        # 导致多项目互相覆盖。用字符串拼接，文件名任何位置都能含点。
        base = out_dir / f"{prefix}{shortcode}_{idx:02d}"
        part = Path(f"{base}.part")
        ok, ctype = _download(url, part, kind, proxy)
        if not ok:
            continue
        ext = ".mp4" if kind == "video" else douyin.MIME_EXT.get(ctype, ".jpg")
        os.replace(part, Path(f"{base}{ext}"))
        print(f"      ✓ {idx:02d}{ext}")
        got += 1
    return got > 0


def process(url: str, out_dir: Path, cookie_path: str | None = None,
            proxy: str = "", max_items: int = 50) -> bool:
    """下载单条帖子/Reels 或用户主页。out_dir 需已存在。至少 1 个文件落盘返回 True。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not proxy:
        proxy = douyin.detect_system_proxy()
        if proxy:
            print(f"  [*] 检测到系统代理：{proxy}")
    if proxy and "://" not in proxy:                     # 无 scheme 的代理（requests/curl 都要求）
        proxy = "http://" + proxy
    if not (cookie_path and Path(cookie_path).exists()):
        print("  [!] IG 需要登录 Cookie：请用浏览器扩展导出 instagram_cookies.txt 放到脚本目录")
        return False
    cookie = douyin.load_cookie_str(cookie_path)
    profile = is_profile(url)
    try:
        if profile:
            username = url.rstrip("/").rsplit("/", 1)[-1]
            print(f"  [*] 拉取用户主页 @{username}（上限 {max_items} 条）...")
            try:
                items = fetch_user_items(username, cookie, proxy, max_items)
            except Exception as e:
                # 2026-10-17 实测：IG 把 users/web_profile_info 限流成 429，
                # 而 feed/user、users/{id}/info、topsearch 分别 403/403/404，主页批量暂无可用替代
                print(f"  [!] 拉取主页失败（{e}）：IG 目前对 web_profile_info 返回 429 限流；"
                      "单条帖子（/p/、/reel/）下载仍正常")
                return False
            print(f"  [*] 共 {len(items)} 条帖子")
            user_dir = out_dir / douyin.sanitize(username)
            user_dir.mkdir(exist_ok=True)
            ok_all = 0
            for item in items:
                if _download_one(item, user_dir, proxy=proxy):
                    ok_all += 1
            if ok_all:
                print(f"  [✓] 已保存 {ok_all}/{len(items)} 条 → {user_dir}")
                return True
            print("  [!] 主页帖子全部下载失败")
            return False
        else:
            shortcode = url.rstrip("/").rsplit("/", 1)[-1]
            print(f"  [*] 获取帖子数据: {shortcode}")
            item = fetch_media_info(shortcode, cookie, proxy)
            uploader = (item.get("user") or {}).get("username") or ""
            if _download_one(item, out_dir, prefix=douyin.sanitize(uploader) + "_", proxy=proxy):
                print(f"  [✓] 已保存 → {out_dir}")
                return True
            print(f"  [!] 帖子 {shortcode} 无文件落盘")
            return False
    except Exception as e:
        print(f"  [!] 下载失败: {e}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Instagram 单条帖子/Reels/主页批量下载器（IG API 自研）")
    ap.add_argument("input", help="帖子/Reels/主页链接，或含链接的文本")
    ap.add_argument("-o", "--output", default=None, help="保存目录（默认：脚本目录/downloads）")
    ap.add_argument("-c", "--cookie", default="instagram_cookies.txt", help="Cookie 文件路径")
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
