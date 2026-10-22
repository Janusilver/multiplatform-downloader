#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube 下载器（yt-dlp 封装：单条视频 / 播放列表）
=====================================================
流程：识别链接 → 判断单条还是整个播放列表 → 交 yt-dlp（可选 Cookie + 代理）→ 下载并合并音视频。
YouTube 视频天然无水印，交 yt-dlp 即可，无需自己解析。

链接形态与处理方式：
  单条：`watch?v=ID` / `youtu.be/ID` / `/shorts/ID` / `/live/ID`
  列表：`playlist?list=PL…` → 默认下整列表（受 `--max` 限制）
        `watch?v=ID&list=PL…` → **默认只下当前视频**，加 `--playlist` 才下整个列表
        `list=RD…`（自动生成的 Mix / 电台，无限流）→ 永远按单条处理
  频道（`@name` / `/channel/` / `/c/`）→ 不支持，直接提示

依赖：yt-dlp + 便携 ffmpeg（`ffmpeg/ffmpeg.exe`）
用法：
  python youtube.py "https://youtu.be/xxxx"
  python youtube.py "https://www.youtube.com/watch?v=xxxx"
  python youtube.py "https://www.youtube.com/playlist?list=PLxxxx"                 # 整列表
  python youtube.py "https://www.youtube.com/watch?v=xxxx&list=PLxxxx" --playlist  # 该列表全下
  python youtube.py "链接" --proxy http://127.0.0.1:7890 --max 10
Cookie（可选，会员/年龄限制/私密视频需要）：浏览器扩展导出 youtube_cookies.txt 放脚本目录。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import douyin

# Windows 默认 GBK 控制台打不出 ✓ 等字符会 UnicodeEncodeError，强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

HOSTS = ("youtube.com", "youtu.be")
# URL 只吃 ASCII 字符集，避免把分享文案里的中文/标点一起吞进来
_REST = r"[A-Za-z0-9\-_./?=&%:#+~]*"
URL_RE = re.compile(
    r"https?://(?:[A-Za-z0-9-]+\.)?"
    r"(?:youtube\.com/(?:watch\?|playlist\?|shorts/|live/|embed/|v/)" + _REST +
    r"|youtu\.be/" + _REST + r")"
)
_VIDEO_PREFIXES = ("/shorts/", "/live/", "/embed/", "/v/")


def host_ok(url: str) -> bool:
    return douyin.host_allowed(url, HOSTS)


def extract_url(text: str) -> str | None:
    """从文本里取出第一条 YouTube 链接；站外域名一律返回 None（防把 Cookie 发错 host）。"""
    for m in URL_RE.finditer(text):
        u = m.group(0).rstrip(".,;:!?)]}'\"")
        if host_ok(u):
            return u
    return None


def _parts(url: str) -> tuple[str, str, dict]:
    u = urlsplit(url)
    return (u.hostname or "").lower(), u.path, parse_qs(u.query)


def video_id(url: str) -> str | None:
    """取单条视频 ID；不是单视频链接返回 None。"""
    host, path, q = _parts(url)
    if host.endswith("youtu.be"):
        seg = path.strip("/").split("/")[0]
        return seg or None
    if path == "/watch":
        return (q.get("v") or [""])[0] or None
    for prefix in _VIDEO_PREFIXES:
        if path.startswith(prefix):
            return path[len(prefix):].strip("/").split("/")[0] or None
    return None


def playlist_id(url: str) -> str | None:
    """取播放列表 ID；`list=RD…` 是自动生成的 Mix/电台（无限流），返回 None。"""
    host, path, q = _parts(url)
    if not (host == "youtube.com" or host.endswith(".youtube.com")):
        return None
    lst = (q.get("list") or [""])[0]
    if not lst or lst.startswith("RD"):
        return None
    if path == "/playlist" or path == "/watch":
        return lst
    return None


def kind(url: str) -> str | None:
    """'video' | 'playlist' | 'video+playlist' | None"""
    if not host_ok(url):
        return None
    _, path, _ = _parts(url)
    vid, pid = video_id(url), playlist_id(url)
    if path == "/playlist" and pid:
        return "playlist"
    if vid and pid:
        return "video+playlist"
    if vid:
        return "video"
    if pid:
        return "playlist"
    return None


def should_download_playlist(url: str, want_playlist: bool) -> bool:
    """决定这次是否下整个列表。

    纯 `playlist?list=` 链接没有单条视频可选 → 总是下列表；
    `watch?v=…&list=…` 由调用方（CLI --playlist / GUI 复选框）决定，默认只下当前视频。
    """
    k = kind(url)
    if k == "playlist":
        return True
    if k == "video+playlist":
        return bool(want_playlist)
    return False


def _fmt_opts(ffmpeg_dir: Path) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "nooverwrites": True,               # 已存在的文件跳过
        "format": "bv*[vcodec^=avc1]+ba[ext=m4a]/bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b",
        # 优先 H.264 + m4a：兼容性最好，且避开 4K AV1 流在部分网络下下到一半 403 的问题；
        # 没有 avc1 档（如纯 4K 视频）时退回最佳画质
        "retries": 3,
        "fragment_retries": 3,
        "ignoreerrors": True,               # 列表里个别视频失败不中断整体
    }
    if ffmpeg_dir.is_dir():
        opts["ffmpeg_location"] = str(ffmpeg_dir)
    return opts


def process(url: str, out_dir: Path, cookie_path: str | None = None,
            proxy: str = "", playlist: bool = False, max_items: int = 20) -> bool:
    """下载单条视频或播放列表。成功返回 True。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    k = kind(url)
    if k is None:
        print("  [!] 不是可识别的 YouTube 链接（支持 watch / youtu.be / shorts / live / playlist；"
              "频道主页不支持）")
        return False
    try:
        import yt_dlp
    except ImportError as e:
        print(f"  [!] 缺少 yt-dlp：{e}")
        return False

    want_list = should_download_playlist(url, playlist)
    ffmpeg_dir = Path(__file__).resolve().parent / "ffmpeg"
    opts = _fmt_opts(ffmpeg_dir)
    if want_list:
        max_items = max(1, max_items)       # yt-dlp 的 playlist_items 不接受 1-0 / 1--5
        print(f"  [*] 下载播放列表（最多 {max_items} 条）...")
        opts["playlist_items"] = f"1-{max_items}"
        # 列表存到 downloads/列表名/ 子目录，避免和单条视频混在一起
        opts["outtmpl"] = str(out_dir / "%(playlist_title).80s" /
                             "%(uploader)s_%(title).60s_%(id)s.%(ext)s")
    else:
        print("  [*] 下载单条视频" + ("（链接里的 list 已忽略，要整列表请加 --playlist）"
                                      if k == "video+playlist" else "") + "...")
        opts["noplaylist"] = True
        # 单条要如实报错：ignoreerrors 会把 403 之类的失败吞掉，变成"假成功"
        opts["ignoreerrors"] = False
        opts["outtmpl"] = str(out_dir / "%(uploader)s_%(title).60s_%(id)s.%(ext)s")

    cookie_tmp_dir: str | None = None
    if cookie_path and Path(cookie_path).exists():
        # yt-dlp 退出会把 cookiejar 写回 cookiefile，不能直接传用户的导出文件
        cookie_tmp_dir, cookie_tmp = douyin.temp_cookie_copy(cookie_path)
        if cookie_tmp is not None:          # 契约允许 (None, None)，别把 "None" 交给 yt-dlp
            opts["cookiefile"] = str(cookie_tmp)
    if not proxy:
        proxy = douyin.detect_system_proxy()
        if proxy:
            print(f"  [*] 检测到系统代理：{proxy}")
    if proxy:
        if "://" not in proxy:              # yt-dlp 要求带 scheme
            proxy = "http://" + proxy
        opts["proxy"] = proxy
    else:
        print("  [*] 未设置代理：YouTube 在境外，直连大概率超时（可加 --proxy http://127.0.0.1:7890）")

    before = _snapshot(out_dir)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        print(f"  [!] 下载失败: {str(e).splitlines()[0]}")
        _cleanup_partial(out_dir, before)
        return False
    finally:
        if cookie_tmp_dir:
            shutil.rmtree(cookie_tmp_dir, ignore_errors=True)

    new = _snapshot(out_dir) - before
    done = [p for p in new if not p.name.endswith((".part", ".ytdl"))]
    _cleanup_partial(out_dir, before)
    if done:
        print(f"  [✓] 下载完成（{len(done)} 个文件） → {out_dir}")
        return True
    # ignoreerrors=True 的播放列表会静默跳过失败项，所以按"有没有文件落盘"判定成败
    print("  [!] 没有文件落盘：YouTube 可能限流/403（换代理节点或稍后重试）、"
          "或该视频需要登录（可导出 youtube_cookies.txt 后重试）")
    return False


def _snapshot(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


def _cleanup_partial(root: Path, before: set[Path]) -> None:
    """删除本次新产生的 .part/.ytdl 残留（yt-dlp 失败会留下半截文件）。"""
    for p in _snapshot(root) - before:
        if p.name.endswith((".part", ".ytdl")):
            try:
                p.unlink()
            except OSError:
                pass


def main() -> None:
    ap = argparse.ArgumentParser(description="YouTube 下载器（单条视频 / 播放列表）")
    ap.add_argument("input", help="YouTube 链接（watch / youtu.be / shorts / live / playlist）")
    ap.add_argument("-o", "--output", default=None, help="保存目录（默认：脚本目录/downloads）")
    ap.add_argument("-c", "--cookie", default="youtube_cookies.txt",
                    help="Cookie 文件路径（可选，会员/年龄限制视频需要）")
    ap.add_argument("--proxy", default="",
                    help="代理地址，如 http://127.0.0.1:7890（默认自动读系统代理）")
    ap.add_argument("--playlist", action="store_true",
                    help="链接是 watch?v=…&list=… 时下载整个列表（默认只下当前视频）")
    ap.add_argument("--max", type=int, default=20, help="播放列表最多下载条数（默认 20）")
    args = ap.parse_args()

    out_dir = Path(args.output) if args.output else Path(__file__).resolve().parent / "downloads"
    url = extract_url(args.input)
    if not url:
        sys.exit("[!] 未找到 YouTube 链接")
    print(f"  [*] 解析: {url}")
    ok = process(url, out_dir, cookie_path=args.cookie, proxy=args.proxy,
                 playlist=args.playlist, max_items=args.max)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
