#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用本机真实浏览器抓 `aweme/v1/web/aweme/detail` 的响应（纯标准库，无第三方依赖）。

为什么需要它（2026-10 实测）：抖音 detail 接口现在要安全 SDK 现场签名——
`a_bogus` + `timestamp` + `x-secsdk-web-signature` + `uifid`，其中后三者由浏览器里的
secsdk 用本地会话密钥算出。纯 requests 一律被拦：
  带 uifid/timestamp 无签名 → 403 `Blocked by ArgusSecurityPlugin Signature Not Found`
  什么都不带                → 403 `Blocked by ArgusSecurityPlugin Uifid Not Found`
（对照：同一份 Cookie 打 `aweme/v1/web/hot/search/list/` 是 200，说明 Cookie 与网络没问题。）

复现签名要跑 secsdk 的 JS 运行时 + 浏览器会话密钥，代价远大于收益。所以反过来：
起一个**干净临时 profile** 的浏览器（不碰用户登录态，公开作品本来就不需要登录），
让浏览器自己请求并签名，我们通过 Chrome DevTools Protocol 截它的响应体。

CDP 走 WebSocket，标准库没有 WS 客户端，这里手写最小实现（只需文本帧 + ping/pong）。
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
)

DETAIL_PATH = "/aweme/v1/web/aweme/detail/"
_OP_TEXT, _OP_CLOSE, _OP_PING, _OP_PONG, _OP_CONT = 0x1, 0x8, 0x9, 0xA, 0x0


def find_browser() -> str | None:
    """返回第一个存在的 Chrome / Edge 可执行文件。"""
    for path in BROWSERS:
        if os.path.exists(path):
            return path
    return None


class _WS:
    """最小 WebSocket 客户端：只做客户端帧（必须掩码）+ 文本帧 + ping/pong。"""

    def __init__(self, url: str, timeout: float = 20):
        parts = urlsplit(url)
        self.sock = socket.create_connection((parts.hostname, parts.port or 80), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        req = (f"GET {parts.path or '/'} HTTP/1.1\r\nHost: {parts.netloc}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("CDP WebSocket 握手失败：连接被对端关闭")
            buf += chunk
        head, _, self._buf = buf.partition(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise RuntimeError(f"CDP WebSocket 握手失败：{status.decode(errors='replace')}")

    def _recv_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise RuntimeError("CDP 连接断开")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _recv_frame(self) -> tuple[int, bytes, bool]:
        b1, b2 = self._recv_exact(2)
        fin, op, masked, length = bool(b1 & 0x80), b1 & 0x0F, b2 & 0x80, b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length)
        if mask:
            payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        return op, payload, fin

    def send_text(self, text: str) -> None:
        data = text.encode("utf-8")
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack("!H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", n)
        mask = secrets.token_bytes(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))

    def recv_text(self) -> str:
        buf = b""
        while True:
            op, payload, fin = self._recv_frame()
            if op == _OP_PING:
                self._send_control(_OP_PONG, payload)
                continue
            if op == _OP_CLOSE:
                raise RuntimeError("浏览器关闭了 CDP 连接")
            if op in (_OP_TEXT, _OP_CONT):
                buf += payload
                if fin:
                    return buf.decode("utf-8")

    def _send_control(self, op: int, payload: bytes) -> None:
        mask = secrets.token_bytes(4)
        header = bytes([0x80 | op, 0x80 | len(payload)]) + mask
        self.sock.sendall(header + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class _CDP:
    def __init__(self, ws: _WS):
        self.ws = ws
        self._next_id = 0
        self.events: list[dict] = []

    def send(self, method: str, params: dict | None = None) -> int:
        self._next_id += 1
        self.ws.send_text(json.dumps({"id": self._next_id, "method": method, "params": params or {}}))
        return self._next_id

    def wait_result(self, msg_id: int, timeout: float) -> dict:
        """等某个命令的返回，期间收到的事件先存起来（避免丢 detail 的网络事件）。"""
        deadline = time.time() + timeout
        while True:
            msg = self._recv(deadline)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP 命令失败：{msg['error']}")
                return msg.get("result") or {}
            if "method" in msg:
                self.events.append(msg)

    def next_event(self, timeout: float) -> dict:
        if self.events:
            return self.events.pop(0)
        return self._recv(time.time() + timeout)

    def _recv(self, deadline: float) -> dict:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("CDP 等待超时")
        self.ws.sock.settimeout(remaining)
        return json.loads(self.ws.recv_text())


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _page_ws_url(port: int, timeout: float, proc: subprocess.Popen) -> str:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 本机回环别走代理
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:          # 浏览器自己退了：不用等满超时
            raise RuntimeError(
                f"浏览器启动后立即退出（exit code {proc.returncode}）。"
                "多半被安全软件拦截——实测卡巴斯基会把「项目目录下的 python 启动浏览器」"
                "判为不可信进程直接杀掉，把项目目录加入信任/排除即可")
        try:
            with opener.open(f"http://127.0.0.1:{port}/json/list", timeout=2) as resp:
                for target in json.load(resp):
                    if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                        return target["webSocketDebuggerUrl"]
        except (OSError, ValueError):
            pass                      # 浏览器还没起来 / 端口未监听
        time.sleep(0.3)
    raise RuntimeError(f"浏览器 CDP 端口 {port} 在 {timeout:.0f}s 内未就绪")


def _cleanup(proc: subprocess.Popen | None, profile: str) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    for _ in range(3):                # Windows 上浏览器退出后句柄释放有延迟
        shutil.rmtree(profile, ignore_errors=True)
        if not os.path.exists(profile):
            return
        time.sleep(0.5)


def fetch_detail(aweme_id: str, timeout: float = 60) -> dict:
    """起干净浏览器打开作品页，截 detail 响应并返回 aweme_detail。

    失败抛 RuntimeError（未装浏览器 / 超时 / 页面要求登录 / 作品已删）。
    """
    exe = find_browser()
    if not exe:
        raise RuntimeError("未找到 Chrome / Edge，无法用浏览器抓 detail")
    port = _free_port()
    profile = tempfile.mkdtemp(prefix="dydl-cdp-")
    proc = subprocess.Popen(
        [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--headless=new", "--no-first-run", "--no-default-browser-check",
         "--disable-gpu", "--disable-extensions", "--mute-audio", "--no-proxy-server",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    try:
        ws = _WS(_page_ws_url(port, timeout=20, proc=proc), timeout=timeout)
        cdp = _CDP(ws)
        cdp.send("Network.enable")
        cdp.send("Page.enable")
        cdp.send("Page.navigate", {"url": f"https://www.douyin.com/video/{aweme_id}"})

        deadline = time.time() + timeout
        pending: dict[str, int] = {}          # requestId -> HTTP 状态码
        while time.time() < deadline:
            event = cdp.next_event(timeout=max(1.0, deadline - time.time()))
            method = event.get("method")
            params = event.get("params") or {}
            if method == "Network.responseReceived":
                response = params.get("response") or {}
                if DETAIL_PATH in response.get("url", ""):
                    pending[params["requestId"]] = response.get("status", 0)
            elif method == "Network.loadingFinished" and params.get("requestId") in pending:
                request_id = params["requestId"]
                status = pending.pop(request_id)
                body = cdp.wait_result(
                    cdp.send("Network.getResponseBody", {"requestId": request_id}), 15)
                raw = body.get("body", "")
                text = base64.b64decode(raw).decode("utf-8") if body.get("base64Encoded") else raw
                if status != 200:
                    raise RuntimeError(f"浏览器请求 detail 返回 {status}：{text[:120]}")
                detail = (json.loads(text).get("aweme_detail") or {})
                if not detail:
                    raise RuntimeError("detail 响应无 aweme_detail（作品已删 / 需登录 / 为「动态」内容）")
                return detail
        raise RuntimeError(f"等待 detail 响应超时（{timeout:.0f}s）")
    finally:
        if ws:
            ws.close()
        _cleanup(proc, profile)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法: python douyin_browser.py <aweme_id>")
    sys.stdout.reconfigure(encoding="utf-8")
    d = fetch_detail(sys.argv[1])
    print("desc:", d.get("desc", "")[:60])
    print("author:", (d.get("author") or {}).get("nickname"))
    print("video urls:", len(((d.get("video") or {}).get("play_addr") or {}).get("url_list") or []))
