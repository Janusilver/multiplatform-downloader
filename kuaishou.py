#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快手视频 / 图集下载器（Cookie 可选；建议带 kuaishou_cookies.txt 更稳）
=================================================================
流程：链接（v.kuaishou.com 短链 / short-video / f/ 短链）
→ photoId → PC 作品页（curl_cffi 伪装 Chrome）
→ 解析 window.__APOLLO_STATE__ → 提取无水印视频（manifest）/ 图集 → 下载。

依赖：requests、curl_cffi（.venv 已装）
用法：
  python kuaishou.py "https://v.kuaishou.com/xxxx/"     # 单条
  python kuaishou.py links.txt                          # 批量（每行一条）
  python kuaishou.py "链接" -o 保存目录                 # 指定目录
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from curl_cffi import requests as cr

import douyin  # 复用 UA / load_cookie_str / sanitize

UA = douyin.UA
URL_RE = re.compile(
    r"https?://(?:v\.kuaishou\.com/\S+"
    r"|(?:www\.)?kuaishou\.com/(?:short-video/[0-9A-Za-z]+|f/\S+)"
    r"|v\.m\.chenzhongtech\.com/fw/photo/[0-9A-Za-z]+\S*)"
)
ID_RE = re.compile(r"(?:short-video|fw/photo)/([0-9A-Za-z]+)")
PHOTO_ID_QRY = re.compile(r"[?&]photoId=([0-9A-Za-z]+)")
HOSTS = ("kuaishou.com", "chenzhongtech.com")
IIFE_TAIL = (";(function(){var s;(s=document.currentScript||document.scripts["
             "document.scripts.length-1]).parentNode.removeChild(s);}());")


def extract_url(text: str) -> str | None:
    m = URL_RE.search(text)
    if m:
        return m.group(0).rstrip("/")
    m = re.search(r"https?://[^\s<>\"']+", text)   # 兜底：取第一个链接
    if not m:
        return None
    u = m.group(0).rstrip("),。；）")
    return u if douyin.host_allowed(u, HOSTS) else None   # 站外域名不放行，避免 Cookie 外发


def get(url: str, cookie: str, timeout: int = 25) -> cr.Response:
    h = {"User-Agent": UA, "Referer": "https://www.kuaishou.com/",
         "Accept-Language": "zh-CN,zh;q=0.9"}
    if cookie:
        h["Cookie"] = cookie
    return cr.get(url, headers=h, impersonate="chrome", timeout=timeout)


def resolve_photo_id(url: str, cookie: str) -> str | None:
    m = ID_RE.search(url)
    if m:
        return m.group(1)
    m = PHOTO_ID_QRY.search(url)
    if m:
        return m.group(1)
    try:
        # 短链跳转不需要登录态（实测带/不带 Cookie 拿到的 photoId 一致），且跳转会跨 host；
        # Cookie 头不按域隔离，跟着跳到哪发到哪，故这一步不传 Cookie
        r = get(url, "")
        final = str(r.url)
        m = ID_RE.search(final) or PHOTO_ID_QRY.search(final)
        if m:
            return m.group(1)
        print(f"  [!] 跳转结果无法识别: {final[:100]}")
    except Exception as e:
        print(f"  [!] 短链跳转失败: {e}")
    return None


def fetch_photo(photo_id: str, cookie: str) -> tuple[dict, dict]:
    """返回 (photo, defaultClient)。defaultClient 用于解析 manifest 的 Apollo 引用。"""
    url = f"https://www.kuaishou.com/short-video/{photo_id}"
    r = get(url, cookie)
    text = r.text
    m = re.search(r"window\.__APOLLO_STATE__\s*=\s*", text)
    if not m:
        print("  [!] 页面无 __APOLLO_STATE__（可能被风控，试试带 Cookie）")
        return {}, {}
    raw = text[m.end():]
    raw = raw[:raw.find("</script>")]
    raw = raw.replace(IIFE_TAIL, "").rstrip().rstrip(";")
    try:
        st = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [!] __APOLLO_STATE__ 解析失败: {e}")
        return {}, {}
    dc = st.get("defaultClient") or {}
    photo = dc.get(f"VisionVideoDetailPhoto:{photo_id}") or {}
    if photo:
        # 作者昵称：优先取状态里的 Author 对象
        for k, v in dc.items():
            if k.startswith("VisionVideoDetailAuthor:"):
                photo.setdefault("_authorName", (v or {}).get("name"))
                break
    return photo, dc


def resolve_ref(v, dc: dict):
    """Apollo 引用（{"type":"id","id":"..."}）→ defaultClient 里的真实对象。"""
    hops = 0
    while isinstance(v, dict) and v.get("type") == "id" \
            and isinstance(v.get("id"), str):
        nxt = dc.get(v["id"])
        if not isinstance(nxt, dict):
            return nxt or v
        v = nxt
        hops += 1
        if hops > 10:
            break
    return v


def video_urls(photo: dict, dc: dict) -> list[str]:
    """收集 H264 + H265 全部候选档，按（分辨率, 码率）降序返回，取第一个即最佳画质。
    实测（2026-08）：快手网页两种编码的文件都不带平台水印（H264 upic 4.89MB vs
    H265 bs2 2.93MB，同为 720p 时 H264 码率更高画质更好）。"""
    cands = []

    def add(man, suffix):
        man = resolve_ref(man, dc) if isinstance(man, dict) else man
        for aset in (man or {}).get("adaptationSet") or []:
            aset = resolve_ref(aset, dc)
            for rep in (aset or {}).get("representation") or []:
                rep = resolve_ref(rep, dc)
                if not isinstance(rep, dict):
                    continue
                urls = []
                for k in ("url", "backupUrl"):
                    val = rep.get(k)
                    if isinstance(val, dict) and val.get("json"):
                        urls.extend(v for v in val["json"] if isinstance(v, str))
                    elif isinstance(val, str):
                        urls.append(val)
                    if urls and k == "url":
                        break
                for u in urls:
                    cands.append((u, rep.get("height") or 0,
                                  rep.get("avgBitrate") or 0))

    add(photo.get("manifest"), "h264")
    mh = photo.get("manifestH265")
    if isinstance(mh, dict):
        mh = mh.get("json") or mh
    add(mh, "h265")
    for key in ("photoUrl", "photoH265Url"):
        if photo.get(key):
            cands.append((photo[key], 0, 0))

    seen, out = set(), []
    for u, h, br in sorted(cands, key=lambda x: (x[1], x[2]), reverse=True):
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def atlas_urls(photo: dict) -> list[str]:
    """图集：ext_params.atlas（JSON 字符串或列表）里的图片直链。"""
    ext = photo.get("ext_params") or {}
    atlas = ext.get("atlas") or []
    if isinstance(atlas, str):
        try:
            atlas = json.loads(atlas)
        except json.JSONDecodeError:
            return []
    out = []
    for it in atlas:
        if not isinstance(it, dict):
            continue
        for cdn in it.get("cdnUrls") or [it]:
            if isinstance(cdn, dict) and cdn.get("url"):
                out.append(cdn["url"])
    return out


def download(url: str, dest: Path, label: str = "",
             timeout: tuple = (10, 600)) -> bool:
    """直链下载：UA + Referer（快手 CDN 校验），失败重试 3 次。
    写临时文件 `.part` 再 `os.replace` 原子改名，中断不留半截成品；目标已存在非空则跳过。"""
    part = Path(str(dest) + ".part")
    for attempt in range(3):
        try:
            if dest.exists() and os.path.getsize(dest) > 0:
                return True                     # 已存在完整文件，跳过（重复链接不重下）
            r = requests.get(url, headers={"User-Agent": UA,
                                           "Referer": "https://www.kuaishou.com/"},
                             stream=True, timeout=timeout)
            r.raise_for_status()
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    if chunk:
                        f.write(chunk)
            if os.path.getsize(part) == 0:
                raise ValueError("空文件（可能被限流）")
            os.replace(part, dest)
            return True
        except Exception as e:
            try:
                os.unlink(part)                 # 清掉半截临时文件
            except OSError:
                pass
            print(f"  [!] {label} 第{attempt + 1}次下载失败: {e}")
            time.sleep(2 * (attempt + 1))
    return False


def process(link: str, out_dir: Path, cookie: str) -> bool:
    url = extract_url(link)
    if not url:
        print(f"  [!] 未找到快手链接: {link[:50]}")
        return False
    print(f"  [*] 解析: {url}")
    pid = resolve_photo_id(url, cookie)
    if not pid:
        print("  [!] 无法解析 photoId")
        return False
    photo, dc = fetch_photo(pid, cookie)
    if not photo:
        print("  [!] 作品数据获取失败（可能被风控/作品已删除）")
        return False

    caption = photo.get("caption") or ""
    author = photo.get("_authorName") or photo.get("userName") or "未知"
    base = douyin.sanitize(f"{author}_{caption}")
    ptype = photo.get("photoType") or "VIDEO"

    atlas = atlas_urls(photo)
    if atlas and "ATLAS" in str(ptype).upper():
        sub = out_dir / base
        sub.mkdir(parents=True, exist_ok=True)
        ok = 0
        for i, u in enumerate(atlas, 1):
            if download(u, sub / f"{i:02d}.tmp", label=f"图片{i}"):
                (sub / f"{i:02d}.tmp").replace(sub / f"{i:02d}.jpg")
                ok += 1
            time.sleep(0.5)
        if ok:
            print(f"  [✓] 已保存 {ok}/{len(atlas)} 张 → {sub}")
            return True
        print(f"  [!] 图集 {len(atlas)} 张全部下载失败")
        return False

    vids = video_urls(photo, dc)
    if not vids:
        print("  [!] 既无图集也无视频地址")
        return False
    dest = out_dir / f"{base}.mp4"
    print(f"  [*] 视频: {caption[:40] or '(无标题)'} by {author}")
    if download(vids[0], dest, label="视频"):
        print(f"  [✓] 已保存 → {dest}")
        return True
    print("  [!] 视频下载失败")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="快手无水印下载器（Cookie 可选）")
    ap.add_argument("input", help="分享链接 / 含链接的文本 / txt 文件（每行一条）")
    ap.add_argument("-o", "--output", default=None,
                    help="保存目录（默认：脚本所在目录/downloads）")
    ap.add_argument("-c", "--cookie", default="kuaishou_cookies.txt", help="Cookie 文件路径")
    args = ap.parse_args()

    # 默认固定到脚本目录，避免从别处运行把下载散落到当前目录
    out_dir = Path(args.output) if args.output else Path(__file__).resolve().parent / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = Path(args.cookie)
    cookie = douyin.load_cookie_str(str(cookie_path)) if cookie_path.exists() else ""
    if not cookie:
        print("[!] 未找到 kuaishou_cookies.txt —— 匿名可用，登录后更稳")

    if Path(args.input).exists():
        links = [l.strip() for l in Path(args.input).read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        links = [args.input]
    print(f"[*] 共 {len(links)} 条链接")
    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}]")
        process(link, out_dir, cookie)
        if i < len(links):
            time.sleep(2)   # 限速避免触发风控


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
