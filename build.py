#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyInstaller 打包脚本：生成 dist\多平台下载器.exe（抖音/小红书/快手/B站/X/Instagram，单文件 GUI）。"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ---- 统一 Tcl/Tk 来源（Anaconda）----
# Python 3.13 的 _tkinter 需要 Tcl 8.6.14。本机 Graphviz / SPSS / 旧版 Python 自带
# 旧 Tcl（如 8.6.10），若它们在 PATH 里排在 Anaconda 之前，PyInstaller 收集 tkinter
# 依赖时会误抓它们的 tcl/tk，导致打包出的 exe 一运行就报「Tcl 版本冲突」。
# 因此打包前净化 PATH：Anaconda 的 bin 提到最前，剔除干扰来源。
base = Path(sys.base_prefix)
prefer = [str(p) for p in (
    base / "Library" / "bin",
    base / "Library" / "mingw-w64" / "bin",
    base / "Library" / "usr" / "bin",
    base, base / "Scripts",
) if p.is_dir()]


def _keep_path(p: str) -> bool:
    low = p.lower()
    if any(x in low for x in ("graphviz", "spss")):
        return False
    if "python" in low and "anaconda" not in low:
        return False
    return True


os.environ["PATH"] = os.pathsep.join(
    prefer + [p for p in os.environ.get("PATH", "").split(os.pathsep) if p and _keep_path(p)]
)

# 显式指定 tcl/tk 数据目录（Anaconda/conda 布局；标准 CPython 会自动定位，跳过即可）。
# 必须设：本机 Graphviz / SPSS / 旧版 Python 自带旧 Tcl（8.6.10），若它们在 PATH 里排在
# Anaconda 之前，PyInstaller 收集 tkinter 依赖时会误抓它们的 tcl/tk → 打出的 exe 一运行
# 就报 `Can't find a usable init.tcl`（2026-10-22 实测：删掉这段后 onedir/onefile 都起不来）。
tcl_dir = base / "Library" / "lib" / "tcl8.6"
if tcl_dir.is_dir():
    os.environ["TCL_LIBRARY"] = str(tcl_dir)
    os.environ["TK_LIBRARY"] = str(tcl_dir.with_name("tk8.6"))
    print(f"[*] TCL_LIBRARY = {tcl_dir}")
else:
    print("[*] 非 conda 布局，交给 PyInstaller 自动定位 tcl/tk")

# ---- exe 版本资源 ----
# Windows「属性 → 详细信息」里显示版本/产品名的来源；版本号以 gui.py 的 APP_VERSION 为
# 唯一真相，构建时生成 PyInstaller version file（不落仓库，避免与 APP_VERSION 分叉）。
_m = re.search(r'APP_VERSION\s*=\s*"([\d.]+)"', (BASE / "gui.py").read_text(encoding="utf-8"))
if not _m:
    sys.exit("[FAIL] gui.py 里找不到 APP_VERSION")
ver = _m.group(1)
ver_tuple = tuple(int(x) for x in (ver.split(".") + ["0", "0", "0"])[:4])
version_file = Path(tempfile.gettempdir()) / "mpl_version_info.txt"
version_file.write_text(
    f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={ver_tuple}, prodvers={ver_tuple}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Janusilver'),
      StringStruct('FileDescription', '多平台下载器 - 抖音/小红书/快手/B站/YouTube/X/Instagram'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'multiplatform-downloader'),
      StringStruct('OriginalFilename', '多平台下载器.exe'),
      StringStruct('ProductName', '多平台下载器'),
      StringStruct('ProductVersion', '{ver}'),
      StringStruct('LegalCopyright', 'Copyright (C) 2026 Janusilver'),
    ])]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
""",
    encoding="utf-8")
print(f"[*] 版本资源 = {ver}")

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "多平台下载器",
    "--version-file", str(version_file),
    "--collect-all", "yt_dlp",
    "--collect-all", "curl_cffi",
    "--add-data", f"ffmpeg{os.sep}ffmpeg.exe;ffmpeg",
    "gui.py",
]
print("[*] 打包中（需几分钟）...")
subprocess.check_call(cmd, cwd=BASE)

exe = BASE / "dist" / "多平台下载器.exe"
if exe.exists():
    size = exe.stat().st_size / 1024 / 1024
    release = BASE / "release" / exe.name
    release.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, release)
    print(f"[OK] {exe}（{size:.1f} MB）")
    print(f"[OK] 已复制到 {release}（clone 仓库后双击即用）")
else:
    print("[FAIL] exe 未生成")
