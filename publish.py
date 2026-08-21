"""一键发布：升版本号 + commit + 打 tag + push，触发 GitHub Actions 自动出 Release。

用法（Windows 双击 publish.bat，或命令行）:
    python publish.py            # patch: 1.2.0 -> 1.2.1
    python publish.py minor      # 1.2.0 -> 1.3.0
    python publish.py major      # 1.2.0 -> 2.0.0
    python publish.py --dry-run  # 只打印将要执行的操作，不写文件、不 push
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GUI = ROOT / "gui.py"
GITHUB_REPO = "Janusilver/douyin-dl"


def git(*args):
    return subprocess.run(["git", *args], capture_output=True,
                          text=True, encoding="utf-8")


def latest_tag():
    r = git("describe", "--tags", "--abbrev=0")
    return r.stdout.strip() if r.returncode == 0 else None


def bump(ver: str, level: str) -> str:
    major, minor, patch = (int(x) for x in ver.split("."))
    if level == "major":
        major, minor, patch = major + 1, 0, 0
    elif level == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def is_sensitive(path: str) -> bool:
    """发布前拒绝带上仓库的路径：Cookie、下载内容、构建产物。"""
    parts = path.replace("\\", "/").split("/")
    name = parts[-1].lower()
    if any(seg in ("downloads", "build", "dist", ".venv") for seg in parts):
        return True
    return "cookies" in name or name in ("history.json",) or name.endswith(".pyc")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    level = args[0] if args else "patch"
    if level not in ("patch", "minor", "major"):
        sys.exit(f"用法: publish.bat [patch|minor|major]  或  --dry-run")

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        sys.exit(f"[!] 当前分支是 {branch}，请在 main 分支运行 publish")

    dirty = [l for l in git("status", "--porcelain").stdout.splitlines()
             if is_sensitive(l[3:])]
    if dirty:
        sys.exit("[!] 发现敏感/构建产物未提交，拒绝发布：\n    "
                 + "\n    ".join(dirty))

    base = (latest_tag() or "v1.0.0").lstrip("v")
    new_ver = bump(base, level)
    print(f"[*] 最新 tag v{base} -> 新版本 v{new_ver}")

    src = GUI.read_text(encoding="utf-8")
    if f'APP_VERSION = "{new_ver}"' in src:
        sys.exit(f"[!] gui.py 已是 v{new_ver}，无需发布")
    new_src = re.sub(r'APP_VERSION = "[^"]+"',
                     f'APP_VERSION = "{new_ver}"', src, count=1)
    if new_src == src:
        sys.exit("[!] gui.py 找不到 APP_VERSION，中止")
    if not dry:
        GUI.write_text(new_src, encoding="utf-8")
    print(f'[*] 更新 gui.py: APP_VERSION = "{new_ver}"')

    if dry:
        print("[dry-run] 将执行：git add -A && commit && tag v"
              f"{new_ver} && push origin main + tag。未写入任何文件。")
        return

    git("add", "-A")
    cm = git("commit", "-m", f"v{new_ver}: release（publish.bat 自动）")
    if cm.returncode != 0:
        sys.exit(f"[!] commit 失败: {cm.stderr.strip() or cm.stdout.strip()}")
    print("[OK] commit:", (cm.stdout.strip().splitlines()[-1] or ""))
    git("tag", f"v{new_ver}")
    for ref in ("main", f"v{new_ver}"):
        p = git("push", "origin", ref)
        if p.returncode != 0:
            sys.exit(f"[!] push {ref} 失败: {p.stderr.strip()}")
    print(f"[OK] 已推送 main + tag v{new_ver}")
    print("[*] GitHub Actions 正在构建，稍后自动出 Release：")
    print(f"    https://github.com/{GITHUB_REPO}/releases/tag/v{new_ver}")


if __name__ == "__main__":
    main()
