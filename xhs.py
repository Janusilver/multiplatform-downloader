#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书图文 / 视频下载器（建议带 xhs_cookies.txt，登录 Cookie 更稳）
=================================================================
流程：链接（xhslink 短链 / explore / discovery/item / user/profile）
→ 笔记 ID → 笔记页 HTML（curl_cffi 伪装 Chrome，带 Cookie）
→ 解析 __INITIAL_STATE__ → 提取无水印原图 / 原始视频 → 下载。

依赖：requests、curl_cffi（.venv 已装）
用法：
  python xhs.py "https://xhslink.com/xxxx/"           # 单条
  python xhs.py links.txt                             # 批量（每行一条）
  python xhs.py "链接" -o 保存目录                    # 指定目录
Cookie：浏览器扩展导出 xhs_cookies.txt 放项目根目录（可选，但强烈建议）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from curl_cffi import requests as cr

import douyin  # 复用 UA / host_allowed / load_cookie_str / sanitize / download

UA = douyin.UA
URL_RE = re.compile(
    r"https?://(?:xhslink\.com/\S+"
    r"|(?:www\.)?xiaohongshu\.com/(?:explore|discovery/item)/[0-9a-f]{20,}\S*"
    r"|(?:www\.)?xiaohongshu\.com/user/profile/[0-9a-z]+/[0-9a-f]{20,}\S*)"
)
ID_RE = re.compile(r"/(?:explore|item|profile/[0-9a-z]+)/([0-9a-f]{20,})")
HOSTS = ("xhslink.com", "xiaohongshu.com")


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
    """curl_cffi 伪装 Chrome（小红书对 TLS 指纹有风控）。"""
    h = {"User-Agent": UA, "Referer": "https://www.xiaohongshu.com/",
         "Accept-Language": "zh-CN,zh;q=0.9"}
    if cookie:
        h["Cookie"] = cookie
    return cr.get(url, headers=h, impersonate="chrome", timeout=timeout)


def clean_js(raw: str) -> str:
    """__INITIAL_STATE__ 是 JS 赋值，混有 undefined / new Map([]) 等字面量，json.loads 前先清洗。"""
    raw = re.sub(r"\bundefined\b", "null", raw)
    raw = re.sub(r"\bNaN\b", "null", raw)
    raw = re.sub(r"-?Infinity", "null", raw)
    raw = re.sub(r"new (Map|Set)\(\[[^\]]*\]\)", "{}", raw)
    return raw


def parse_state(text: str) -> dict:
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*", text)
    if not m:
        return {}
    raw = text[m.end():]
    raw = raw[:raw.find("</script>")]
    raw = raw.rstrip().rstrip(";")
    try:
        return json.loads(clean_js(raw))
    except json.JSONDecodeError as e:
        print(f"  [!] __INITIAL_STATE__ JSON 解析失败: {e}")
        return {}


def is_blocked(r: cr.Response) -> bool:
    """被风控时跳转到 /404?source=/404/sec_xxx 或标题是「页面不见了」。"""
    return ("/404" in str(r.url)) or ("页面不见了" in r.text[:2000])


def fetch_homepage_xsec(note_id: str, cookie: str) -> tuple[str | None, str | None]:
    """详情页缺 xsec_token 时，从首页 feed 里借该笔记的 xsecToken（只对在推荐流里的笔记有效）。"""
    try:
        r = get("https://www.xiaohongshu.com/explore", cookie)
        st = parse_state(r.text)
        for item in (st.get("feed") or {}).get("feeds") or []:
            if not isinstance(item, dict) or item.get("id") != note_id:
                continue
            return item.get("xsecToken"), item.get("xsecSource") or "pc_feed"
    except Exception:
        pass
    return None, None


def fetch_note(note_id: str, cookie: str, xsec_token: str = "",
               xsec_source: str = "") -> dict:
    """笔记页 HTML → __INITIAL_STATE__ → noteDetailMap[noteId].note"""
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    if xsec_token:
        url += f"?xsec_token={xsec_token}&xsec_source={xsec_source or 'pc_feed'}"
    r = get(url, cookie)
    if r.status_code != 200:
        return {}
    if is_blocked(r) and not xsec_token:
        # 裸 explore 链接没有 xsec 会被风控：尝试从首页 feed 借 token 重试
        tok, src = fetch_homepage_xsec(note_id, cookie)
        if tok:
            print(f"  [*] 从首页 feed 借到 xsec_token，重试")
            return fetch_note(note_id, cookie, tok, src)
    st = parse_state(r.text)
    nmap = (st.get("note") or {}).get("noteDetailMap") or {}
    first = None
    for k, v in nmap.items():
        note = v.get("note") or {}
        if first is None:
            first = note
        if note.get("noteId") == note_id:
            return note
    return first or {}


def image_token(url: str) -> str:
    """去掉 CDN 域名、参数和变换后缀，得到原图 token（无水印原图）。
    兼容三种形态：https://host/path、//host/path、host/path。"""
    u = url.split("?")[0].split("!")[0]
    u = re.sub(r"^https?://", "", u).lstrip("/")
    parts = u.split("/")
    if len(parts) > 1 and "." in parts[0]:   # 首段是域名
        u = "/".join(parts[1:])
    return u


def image_urls(note: dict) -> list[tuple[str, str | None]]:
    """返回 [(图片URL, 动图URL或None)]，图片为无水印原图。
    原图 key 是 imageList[].fileId；动图（实况图）是 imageList[].stream 里
    第一个非空流（EF4/h264）的 masterUrl。"""
    out = []
    for im in note.get("imageList") or []:
        live = None
        streams = im.get("stream") or {}
        for codec in ("EF4", "h264", "EF6", "EF7", "h265"):
            lst = streams.get(codec) or []
            if lst and lst[0].get("masterUrl"):
                live = lst[0]["masterUrl"]
                break
        fid = im.get("fileId") or ""
        url = f"https://sns-img-bd.xhscdn.com/{fid}" if fid else ""
        if not url:
            src = im.get("urlDefault") or im.get("url") or ""
            url = (f"https://sns-img-bd.xhscdn.com/{image_token(src)}"
                   if src else "")
        out.append((url, live))
    return out


def video_urls(note: dict) -> list[str]:
    """优先原始文件（无水印），失败再退回各编码流最高清（列表通常升序，取最后）。"""
    vid = note.get("video") or {}
    key = (vid.get("consumer") or {}).get("originVideoKey")
    if key:
        return [f"https://sns-video-bd.xhscdn.com/{key}"]
    urls = []
    streams = (vid.get("media") or {}).get("stream") or {}
    for codec in ("EF4", "EF5", "EF7", "EF6", "h264", "h265"):
        for it in streams.get(codec) or []:
            if it.get("masterUrl"):
                urls.append(it["masterUrl"])
    return urls


def process(link: str, out_dir: Path, cookie: str) -> bool:
    url = extract_url(link)
    if not url:
        print(f"  [!] 未找到小红书链接: {link[:50]}")
        return False
    print(f"  [*] 解析: {url}")

    # 短链先跳转拿最终 URL（含 xsec_token）
    if douyin.host_allowed(url, ("xhslink.com",)):
        try:
            # 短链跳转不传 Cookie：xsec_token 是短链自带的时效凭证，不依赖登录态
            # （实测带/不带 Cookie 拿到的 noteID 与 token 一致）；且跳转会跨 host，
            # Cookie 头不按域隔离，跟着跳到哪发到哪。
            r = get(url, "")
            url = str(r.url)
            print(f"  [*] 跳转: {url[:80]}")
        except Exception as e:
            print(f"  [!] 短链跳转失败: {e}")
            return False

    m = ID_RE.search(url)
    if not m:
        print("  [!] 无法识别笔记 ID")
        return False
    note_id = m.group(1)
    params = dict(re.findall(r"[?&](xsec_token|xsec_source)=([^&\s\"'<>]+)", url))
    note = fetch_note(note_id, cookie, params.get("xsec_token", ""),
                      params.get("xsec_source", ""))
    if not note:
        print("  [!] 笔记数据获取失败（可能被风控/需登录 Cookie/笔记已删除）")
        return False

    title = note.get("title") or note.get("desc") or ""
    author = (note.get("user") or {}).get("nickname") or "未知"
    base = douyin.sanitize(f"{author}_{title}")

    imgs = image_urls(note)
    ntype = note.get("type") or "normal"
    if ntype == "video":
        # 视频笔记（imageList 里的 1 张是封面，不下载）
        vids = video_urls(note)
        if not vids:
            print("  [!] 未找到视频地址")
            return False
        if not (note.get("video") or {}).get("consumer", {}).get("originVideoKey"):
            print("  [!] 该视频无原始文件源，网页流可能带小红书号水印")
        dest = out_dir / f"{base}.mp4"
        print(f"  [*] 视频: {title[:40] or '(无标题)'} by {author}")
        done, _ = douyin.download(vids[0], dest, label="视频", timeout=(10, 600))
        if done:
            print(f"  [✓] 已保存 → {dest}")
            return True
        print("  [!] 视频下载失败")
        return False
    elif imgs:
        sub = out_dir / base
        sub.mkdir(parents=True, exist_ok=True)
        ok = 0
        for i, (u, live) in enumerate(imgs, 1):
            if u:
                ext = ".jpg"
                done, _ = douyin.download(u, sub / f"{i:02d}.tmp", label=f"图片{i}",
                                          timeout=(10, 300))
                if done:
                    (sub / f"{i:02d}.tmp").replace(sub / f"{i:02d}{ext}")
                    ok += 1
            if live:  # 动图（Live Photo）附带的短视频
                done, _ = douyin.download(live, sub / f"{i:02d}.mp4", label=f"动图{i}",
                                          timeout=(10, 300))
                if done:
                    ok += 1
            time.sleep(0.5)
        if ok:
            print(f"  [✓] 已保存 {ok}/{len(imgs)} 项（动图含 mp4） → {sub}")
            return True
        print(f"  [!] 图集 {len(imgs)} 项全部下载失败")
        return False
    else:
        print("  [!] 既无图集也无视频地址")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="小红书无水印下载器（建议带 xhs_cookies.txt）")
    ap.add_argument("input", help="分享链接 / 含链接的文本 / txt 文件（每行一条）")
    ap.add_argument("-o", "--output", default=None,
                    help="保存目录（默认：脚本所在目录/downloads）")
    ap.add_argument("-c", "--cookie", default="xhs_cookies.txt", help="Cookie 文件路径")
    args = ap.parse_args()

    # 默认固定到脚本目录，避免从别处运行把下载散落到当前目录
    out_dir = Path(args.output) if args.output else Path(__file__).resolve().parent / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = Path(args.cookie)
    cookie = douyin.load_cookie_str(str(cookie_path)) if cookie_path.exists() else ""
    if not cookie:
        print("[!] 未找到 xhs_cookies.txt —— 匿名可用，但可能被风控；建议登录后导出 Cookie")

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
