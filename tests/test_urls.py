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
            ("https://x.com/<user>/status/<id 隐去>",
             "https://x.com/<user>/status/<id 隐去>"),
            ("https://twitter.com/jack/status/123",
             "https://twitter.com/jack/status/123"),
            # 从分享文本里取出链接
            ("看看这个 https://x.com/<user>/status/<id 隐去> 有意思",
             "https://x.com/<user>/status/<id 隐去>"),
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
            ("https://x.com/<user>/status/<id 隐去>", False),
        ])
    if instagram is None:
        print("[FAIL] instagram 模块缺失\n")
        f += 1
    else:
        f += check("instagram.extract_url", instagram.extract_url, [
            ("https://www.instagram.com/<id 隐去>/", "https://www.instagram.com/<id 隐去>"),
            ("https://instagram.com/<id 隐去>/", "https://instagram.com/<id 隐去>"),
            ("https://www.instagram.com/jack/", "https://www.instagram.com/jack"),
            # 系统路径不匹配
            ("https://www.instagram.com/accounts/login/", None),
            ("https://www.instagram.com/explore/", None),
        ])
        f += check("instagram.is_profile", instagram.is_profile, [
            ("https://www.instagram.com/jack", True),
            ("https://www.instagram.com/<id 隐去>", False),
        ])
    sys.exit(1 if f else 0)


if __name__ == "__main__":
    main()
