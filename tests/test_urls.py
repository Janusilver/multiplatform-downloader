#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""URL 识别轻量测试：纯 assert，无 pytest 依赖。跑：.venv/Scripts/python.exe tests/test_urls.py"""
import sys
from pathlib import Path

# Windows 默认 GBK 控制台打不出中文/✓ 会乱码或 UnicodeEncodeError，强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 平台脚本逐个创建（TDD：先建 twitter.py，后建 instagram.py），缺失的模块不影响另一个的测试
try:
    import instagram
except ModuleNotFoundError:
    instagram = None
try:
    import twitter
except ModuleNotFoundError:
    twitter = None

import douyin
import kuaishou
import xhs


def check(name: str, fn, cases) -> int:
    failed = 0
    for text, expected in cases:
        got = fn(text)
        ok = got == expected
        failed += 0 if ok else 1
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: {text!r} -> {got!r}"
              + ("" if ok else f"  (期望 {expected!r})"))
    print(f"{name}: {len(cases) - failed}/{len(cases)} 通过\n")
    return failed


def main() -> int:
    f = 0
    if twitter is None:
        print("[FAIL] twitter 模块缺失\n")
        f += 1
    else:
        f += check("twitter.extract_url", twitter.extract_url, [
            # 单条推文：x.com 与 twitter.com 域名都认
            ("https://x.com/jack/status/1234567890123456789",
             "https://x.com/jack/status/1234567890123456789"),
            ("https://twitter.com/jack/status/123",
             "https://twitter.com/jack/status/123"),
            # 从分享文本里取出链接
            ("看看这个 https://x.com/jack/status/123 有意思",
             "https://x.com/jack/status/123"),
            # 用户主页批量
            ("https://x.com/jack", "https://x.com/jack"),
            # 系统路径不匹配
            ("https://x.com/search?q=test", None),
            ("https://x.com/home", None),
            # 其他平台链接不匹配
            ("https://www.douyin.com/video/123", None),
        ])
        f += check("twitter.is_profile", twitter.is_profile, [
            ("https://x.com/jack", True),
            ("https://x.com/jack/status/123", False),
        ])
    if instagram is None:
        print("[FAIL] instagram 模块缺失\n")
        f += 1
    else:
        f += check("instagram.extract_url", instagram.extract_url, [
            ("https://www.instagram.com/p/CxAb12345/", "https://www.instagram.com/p/CxAb12345"),
            ("https://instagram.com/reel/CxAb12345/", "https://instagram.com/reel/CxAb12345"),
            ("https://www.instagram.com/jack/", "https://www.instagram.com/jack"),
            # 系统路径不匹配
            ("https://www.instagram.com/accounts/login/", None),
            ("https://www.instagram.com/explore/", None),
        ])
        f += check("instagram.is_profile", instagram.is_profile, [
            ("https://www.instagram.com/jack", True),
            ("https://www.instagram.com/p/CxAb12345", False),
        ])
    # 兜底分支的域名白名单：站外域名必须返回 None，否则下游会把登录 Cookie 发给该 host
    note = "a" * 24                                    # 笔记 ID 形如 24 位十六进制
    f += check("douyin.extract_url", douyin.extract_url, [
        ("https://v.douyin.com/abc123/", "https://v.douyin.com/abc123"),
        ("https://www.douyin.com/video/7123456789012345678",
         "https://www.douyin.com/video/7123456789012345678"),
        # 兜底仍放行同域的未覆盖路径
        ("https://www.douyin.com/user/MS4wLjABAAAA", "https://www.douyin.com/user/MS4wLjABAAAA"),
        # 站外域名冒充
        ("https://evil.com/v.douyin.com/xxx", None),
        ("https://douyin.com.evil.com/video/123", None),
    ])
    f += check("xhs.extract_url", xhs.extract_url, [
        ("https://xhslink.com/a/abc123", "https://xhslink.com/a/abc123"),
        (f"https://www.xiaohongshu.com/explore/{note}",
         f"https://www.xiaohongshu.com/explore/{note}"),
        # 站外域名冒充：CodeQL 告警对应的场景
        ("https://evil.com/?x=xhslink.com", None),
        ("https://xhslink.com.evil.com/a", None),
    ])
    f += check("kuaishou.extract_url", kuaishou.extract_url, [
        ("https://v.kuaishou.com/abcdef", "https://v.kuaishou.com/abcdef"),
        ("https://www.kuaishou.com/short-video/3x7edaa985qmhqy",
         "https://www.kuaishou.com/short-video/3x7edaa985qmhqy"),
        # 站外域名冒充
        ("https://evil.com/#kuaishou.com", None),
        ("https://kuaishou.com.evil.com/short-video/3x7", None),
    ])
    f += check("douyin.host_allowed", lambda u: douyin.host_allowed(u, ("xhslink.com",)), [
        ("https://xhslink.com/a/1", True),
        ("https://sub.xhslink.com/a/1", True),
        ("https://evil.com/?x=xhslink.com", False),
        ("https://xhslink.com.evil.com/a", False),
        ("https://evilxhslink.com/a", False),
        ("not a url", False),
    ])
    sys.exit(1 if f else 0)


if __name__ == "__main__":
    main()
