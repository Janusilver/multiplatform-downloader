#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音图文 / 视频 无水印下载器（需要浏览器扩展导出的 douyin_cookies.txt）
=================================================================
流程：短链 → aweme_id → aweme/detail（带 Cookie）→ 提取图集原图或无水印视频 → 下载。
2026-10 起 detail 接口要求 secsdk 现场签名，纯 requests 必被 Argus 拦；此时自动退回
douyin_browser.py（无头 Chrome/Edge + CDP 截响应）拿同一份 detail 数据。

依赖：requests + 本机 Chrome 或 Edge（兜底抓详情用；douyin_browser.py 本身纯标准库）
用法：
  python douyin.py "https://v.douyin.com/xxxx/"        # 单条
  python douyin.py links.txt                           # 批量（每行一条）
  python douyin.py "链接" -o 保存目录                   # 指定目录
Cookie 失效时重新用浏览器扩展导出 douyin_cookies.txt 即可。

本模块同时是共享工具库：xhs / kuaishou / instagram 复用
UA / host_allowed / load_cookie_str / sanitize / MIME_EXT / download。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

# Windows 默认 GBK 控制台打不出 ✓ 等字符会 UnicodeEncodeError，强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0")
URL_RE = re.compile(
    r"https?://(?:v\.douyin\.com/\S+|(?:www\.)?iesdouyin\.com/share/\S+/\d+"
    r"|(?:www\.|m\.)?douyin\.com/(?:video|note|slides)/\d+|www\.douyin\.com/\d+)"
)
ID_RE = re.compile(r"/(?:video|note|slides)/(\d+)")
HOSTS = ("douyin.com", "iesdouyin.com")
MIME_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
            "image/avif": ".avif", "image/gif": ".gif", "image/heic": ".heic"}


def host_allowed(url: str, domains: tuple[str, ...]) -> bool:
    """URL 的 host 是否落在白名单内（含子域）。

    不能用子串判断：`"xhslink.com" in url` 会被 https://evil.com/?x=xhslink.com 骗过，
    而下游会把登录 Cookie 当 Header 发给该 host。
    """
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def detect_system_proxy() -> str:
    """读 Windows 系统代理（注册表 Internet Settings），返回代理地址（如 http://127.0.0.1:7890）。
    未启用 / 读取失败返回 ""。IG、X 等国外站可直接复用本机任意代理工具（Clash / V2rayN /
    Shadowsocks / Netch 等）开启的「系统代理」，免去手动填端口。返回带 scheme，可直接传给
    requests / yt-dlp / curl_cffi。"""
    try:
        import winreg
    except ImportError:
        return ""                                        # 非 Windows 平台
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if not enabled:
            return ""
        server, _ = winreg.QueryValueEx(key, "ProxyServer")
    except OSError:
        return ""
    for part in (server or "").split(";"):               # 多协议格式 http=..;https=..;socks=..
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            scheme, _, val = part.partition("=")
            val = val.strip()
            if scheme.lower() in ("http", "https"):
                return "http://" + val
            if scheme.lower() in ("socks", "socks5"):
                return "socks5://" + val                # SOCKS 代理必须带 socks5:// 前缀
        else:                                            # 纯 "host:port"（WinINET 固定是 http 代理）
            return "http://" + part
    return ""


def load_cookie_str(path: str = "douyin_cookies.txt", host: str | None = None) -> str:
    """读扩展导出的 cookies.txt，转成 Cookie 请求头字符串。

    host 给定时只保留对该 host 生效的 cookie。同一个 cookie 名可能同时存在于多个子域
    （实测导出文件里 www.douyin.com 与 live.douyin.com 的 s_v_web_id 值不同），
    不按域名过滤就按行拼，后出现的值会覆盖真正该发的那一个。
    """
    pairs = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#HttpOnly_"):       # HttpOnly 前缀去掉，按正常行处理
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        if host:
            domain = parts[0].lstrip(".").lower()
            if not (host == domain or host.endswith("." + domain)):
                continue
        pairs.append(f"{parts[-2]}={parts[-1]}")
    return "; ".join(pairs)


def make_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Cookie": cookie, "User-Agent": UA,
                      "Referer": "https://www.douyin.com/",
                      "Accept-Language": "zh-CN,zh;q=0.9"})
    return s


def extract_url(text: str) -> str | None:
    m = URL_RE.search(text)
    if m:
        return m.group(0).rstrip("/")
    m = re.search(r"https?://[^\s<>\"']+", text)   # 兜底：取第一个链接
    if not m:
        return None
    u = m.group(0).rstrip("),。；）")
    return u if host_allowed(u, HOSTS) else None   # 站外域名不放行，避免 Cookie 外发


def resolve_aweme_id(url: str, s: requests.Session) -> str | None:
    url = url.rstrip("/")
    m = ID_RE.search(url)
    if m:
        return m.group(1)
    try:
        # 短链跳转不需要登录态，且会跨 host（v.douyin.com → iesdouyin.com → douyin.com）；
        # session 的 Cookie 头不按域隔离，跟着跳到哪发到哪，故显式设 None 摘掉（cookie jar 按域隔离，无需处理）
        r = s.get(url, headers={"User-Agent": UA, "Cookie": None},
                  allow_redirects=True, timeout=20)
        m = ID_RE.search(r.url)
        return m.group(1) if m else None
    except requests.RequestException as e:
        print(f"  [!] 短链解析失败: {e}")
        return None


def fetch_detail(aweme_id: str, s: requests.Session) -> dict:
    """取作品详情。先直连接口，被签名校验拦下时退回真浏览器抓响应。"""
    url = (f"https://www.douyin.com/aweme/v1/web/aweme/detail/"
           f"?aweme_id={aweme_id}&device_platform=webapp&aid=6383&channel=channel_pc_web")
    r = s.get(url, timeout=20)
    if r.status_code == 200 and r.content:
        detail = r.json().get("aweme_detail") or {}
        if detail:
            return detail
    # 2026-10 起 detail 要 secsdk 现场签名（a_bogus + timestamp + x-secsdk-web-signature），
    # 纯 requests 一律 403 `Blocked by ArgusSecurityPlugin ...`。签名依赖浏览器 JS 运行时与
    # 本地会话密钥，复现代价远大于收益，改让真浏览器自己请求、经 CDP 截响应。
    print("  [*] 接口被签名校验拦截，改用浏览器抓取（约 5~10s）")
    import douyin_browser
    return douyin_browser.fetch_detail(aweme_id)


def best_video_url(video: dict) -> tuple[str, str]:
    """挑最高画质，返回 (url, 档位名)。

    不能直接用 play_addr.url_list[0]：它只是默认档，实测同一条作品 play_addr 是 540p，
    而 bit_rate 里有 normal_1080_0（1080x1920）。按 (height, 平均码率) 降序取第一个。
    """
    cands = []
    for b in video.get("bit_rate") or []:
        addr = b.get("play_addr") or {}
        urls = addr.get("url_list") or []
        if urls:
            label = b.get("gear_name") or f"{addr.get('height') or '?'}p"
            cands.append(((addr.get("height") or 0, b.get("bit_rate") or 0), urls[0], label))
    if cands:
        cands.sort(key=lambda c: c[0], reverse=True)
        return cands[0][1], cands[0][2]
    urls = (video.get("play_addr") or {}).get("url_list") or []
    return (urls[0], "default") if urls else ("", "")


def sanitize(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    return (name or "douyin")[:max_len]


def best_image_url(im: dict) -> str | None:
    """图集图片用 url_list（无水印，分辨率不变）。download_url_list 带「抖音号」水印，弃用。"""
    ul = im.get("url_list") or []
    for u in ul:
        if ".jpeg" in u.split("?")[0].lower():
            return u
    return ul[0] if ul else None


def download(url: str, dest: Path, label: str = "",
             timeout: tuple = (10, 120), headers: dict | None = None,
             session: requests.Session | None = None) -> tuple[bool, str]:
    """通用直链下载（douyin / xhs / kuaishou 共用）。
    headers 不传默认只带 UA——多数图片 CDN 防盗链要求：不能带 Cookie/Referer，否则 403；
    传 session 时走 session.get（带 Cookie/Referer，视频下载用）。
    写临时文件 `.part` 再 `os.replace` 原子改名，中断不留半截成品；目标已存在非空则跳过
    （重复链接不重下）；失败重试 3 次。返回 (是否成功, Content-Type)。"""
    part = Path(str(dest) + ".part")
    for attempt in range(3):
        try:
            if dest.exists() and os.path.getsize(dest) > 0:
                return True, ""                 # 已存在完整文件，跳过
            if session is not None:
                cm = session.get(url, headers=headers, stream=True, timeout=timeout)
            else:
                cm = requests.get(url, headers=headers or {"User-Agent": UA},
                                  stream=True, timeout=timeout)
            with cm as r:
                r.raise_for_status()
                ctype = r.headers.get("Content-Type", "").split(";")[0].lower()
                with open(part, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if chunk:
                            f.write(chunk)
            if os.path.getsize(part) == 0:
                raise ValueError("空文件（可能被限流）")
            os.replace(part, dest)
            return True, ctype
        except Exception as e:
            try:
                os.unlink(part)                 # 清掉半截临时文件
            except OSError:
                pass
            print(f"  [!] {label} 第{attempt + 1}次下载失败: {e}")
            time.sleep(2 * (attempt + 1))
    return False, ""


def process(link: str, out_dir: Path, s: requests.Session) -> bool:
    url = extract_url(link)
    if not url:
        print(f"  [!] 未找到抖音链接: {link[:50]}")
        return False
    print(f"  [*] 解析: {url}")
    aid = resolve_aweme_id(url, s)
    if not aid:
        print("  [!] 无法解析 aweme_id，链接可能失效或 Cookie 过期")
        return False
    try:
        detail = fetch_detail(aid, s)
    except RuntimeError as e:            # 浏览器兜底失败：给一行可读原因，不抛栈
        print(f"  [!] {e}")
        return False
    desc = detail.get("desc", "") or ""
    author = (detail.get("author") or {}).get("nickname", "") or "未知"
    base = sanitize(f"{author}_{desc}")

    images = detail.get("images") or []
    if images:
        print(f"  [*] 图文作品: {len(images)} 张 by {author}")
        sub = out_dir / base
        sub.mkdir(parents=True, exist_ok=True)
        ok = 0
        for i, im in enumerate(images, 1):
            done = False
            # 实况图/动图（Live Photo）：每张图内嵌一个短视频，静态封面 + 动图 mp4 都下。
            # 用权威字段判断（live_photo_type==1 / clip_type==5），不能只看 video.url_list 非空
            # ——普通图集作品的 video.play_addr 是背景音乐 mp3（非视频），否则会误下 BGM。
            v = im.get("video") or {}
            v_url = ((v.get("download_addr") or {}).get("url_list") or
                     (v.get("play_addr") or {}).get("url_list") or [])
            is_live = (im.get("live_photo_type") == 1) or (im.get("clip_type") == 5)
            if is_live and v_url:
                u = best_image_url(im)                      # 静态封面
                if u:
                    ok_f, ctype = download(u, sub / f"{i:02d}.tmp", label=f"封面{i}")
                    if ok_f:
                        ext = MIME_EXT.get(ctype, ".jpg")
                        (sub / f"{i:02d}.tmp").replace(sub / f"{i:02d}{ext}")
                        done = True
                u = v_url[0].replace("watermark=1", "watermark=0")  # url_list[0] 可能排到带水印档，强制归一
                ok_f, _ = download(u, sub / f"{i:02d}.mp4", label=f"动图{i}", session=s,
                                   timeout=(30, 120),   # 元组里较小值才是实际 socket 超时（见 CLAUDE.md「坑」）
                                   headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"})
                if ok_f:
                    done = True
            else:
                u = best_image_url(im)
                if u:
                    ok_f, ctype = download(u, sub / f"{i:02d}.tmp", label=f"图片{i}")
                    if ok_f:
                        ext = MIME_EXT.get(ctype, ".jpg")
                        (sub / f"{i:02d}.tmp").replace(sub / f"{i:02d}{ext}")
                        done = True
            if done:
                ok += 1
            time.sleep(0.5)
        if ok:
            print(f"  [✓] 已保存 {ok}/{len(images)} 张（动图含 mp4） → {sub}")
            return True
        print(f"  [!] {len(images)} 张图全部下载失败")
        return False
    else:
        video = detail.get("video") or {}
        play = video.get("play_addr") or {}
        u, gear = best_video_url(video)
        if not u:
            print("  [!] 既无图集也无视频地址")
            return False
        u = u.replace("/playwm/", "/play/")   # 去水印
        dest = out_dir / f"{base}.mp4"
        print(f"  [*] 视频({gear}): {desc[:40] or '(无标题)'} by {author}")
        # 主路径（playwm→play）；失败时用 snssdk 直链兜底（play_addr.uri 即 video_id）
        candidates = [u]
        vid = play.get("uri")
        if vid:
            candidates.append(
                f"https://aweme.snssdk.com/aweme/v1/play/"
                f"?video_id={vid}&ratio=1080p&line=0")
        ok_f = False
        for cand in candidates:
            ok_f, _ = download(cand, dest, label="视频", timeout=(30, 600), session=s,
                               headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"})
            if ok_f:
                break
        if ok_f:
            print(f"  [✓] 已保存 → {dest}")
            return True
        print("  [!] 视频下载失败（主路径与 snssdk 兜底均失败）")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="抖音图文/视频无水印下载器（需 douyin_cookies.txt）")
    ap.add_argument("input", help="分享链接 / 含链接的文本 / txt 文件（每行一条）")
    ap.add_argument("-o", "--output", default=None,
                    help="保存目录（默认：脚本所在目录/downloads）")
    ap.add_argument("-c", "--cookie", default="douyin_cookies.txt", help="Cookie 文件路径")
    args = ap.parse_args()

    # 默认固定到脚本目录，避免从别处运行把下载散落到当前目录
    out_dir = Path(args.output) if args.output else Path(__file__).resolve().parent / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    cookie = load_cookie_str(args.cookie, host="www.douyin.com")
    if not cookie:
        sys.exit("[!] Cookie 为空。请先在浏览器扩展里导出 douyin_cookies.txt（见 CLAUDE.md）")
    s = make_session(cookie)

    if Path(args.input).exists():
        links = [l.strip() for l in Path(args.input).read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        links = [args.input]
    print(f"[*] 共 {len(links)} 条链接")
    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}]")
        process(link, out_dir, s)
        if i < len(links):
            time.sleep(2)   # 限速避免触发风控


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
