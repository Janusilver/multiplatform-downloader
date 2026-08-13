# douyin-dl · 抖音无水印图文 / 视频下载器

粘贴抖音分享链接，一键下载**图集无水印原图**、**实况图动图（静态封面 + mp4）**或**无水印视频**；附带 **B站视频下载**（BV 号 / av 号 / b23.tv 都支持，自动合并画质 + 音轨）。

> 纯个人工具，仅供**个人归档学习**，尊重创作者版权，请勿二次传播无水印内容。

## ✨ 功能特性

- ✅ **图集无水印**：全部图片走无水印源（`url_list`），作者「抖音号」水印版本自动跳过
- ✅ **实况图 / 动图（Live Photo）**：每张图自动下**静态封面 jpg + 动图 mp4** 两份（同编号 `01.jpg` / `01.mp4`）
- ✅ **视频去水印**：`playwm → play` 直达无水印视频
- ✅ **智能识别链接**：粘贴整段分享文案也能自动提取短链；支持 `v.douyin.com` / `douyin.com` / `iesdouyin.com`
- ✅ **批量下载**：txt 每行一个链接，内置限速避免触发风控
- ✅ **B站下载**：粘贴**裸 BV 号**（如 `BV<id 隐去>`）也能识别，自动补全链接；画质+音轨自动合并成一个 mp4
- ✅ 失败自动重试、Windows 编码自动处理

## 🚀 免环境版（Windows exe，无需装 Python）

给「不想装 Python」的人：**clone 或下载本仓库后，直接双击 `release\抖音下载器.exe`**，弹个小窗口粘贴分享链接即可下载抖音和 B站视频。exe 已内置 Python 运行时、yt-dlp、ffmpeg，无需任何安装。

**三个东西都要拿到**（一个都不能少）：

| 文件 | 作用 |
|---|---|
| `release\抖音下载器.exe` | 主程序，双击即用 |
| `extensions\cookie-export\` | 浏览器扩展，**抖音必需**：导出你的登录 Cookie |
| `douyin_cookies.txt` | 你导出的 Cookie，放到 exe **旁边** |

**首次使用（3 步）**：

1. **装扩展**：Edge 打开 `edge://extensions/`（Chrome 用 `chrome://extensions/`）→ 开启左下角「开发人员模式」→「加载解压缩的扩展」→ 选 `cookie-export` 文件夹
2. **导出 Cookie**：打开 [douyin.com](https://www.douyin.com) 并保持登录 → 点扩展图标 → 导出 `douyin_cookies.txt`
3. **双击 exe**：把 Cookie 文件放到 exe 同目录，双击 exe，粘贴链接点「开始下载」

> 💡 B站**不需要** Cookie，只有抖音需要。不导出 Cookie 也能用 B站功能。

**⚠️ Windows 提示「已保护你的电脑」**：因为没做代码签名，属正常现象，点「更多信息」→「仍要运行」。

> 想自己打包？先装好 venv 并准备好 `ffmpeg\ffmpeg.exe`（见下「安装」），双击 `build.bat`，输出到 `dist\抖音下载器.exe`（约 54MB，启动解压需等 3–15 秒属正常），并自动复制一份到 `release\`。

## 📦 目录结构

```
douyin-dl/
├── douyin.py            # 抖音核心下载器（Python）
├── douyin.bat           # 抖音下载入口（双击运行）
├── bilibili.bat         # B站下载入口（双击运行）
├── gui.py               # 免环境版 GUI 入口（PyInstaller 打包用）
├── build.bat            # 打包入口：装依赖 + 调 build.py
├── build.py             # PyInstaller 打包脚本（自动排除 tcl 干扰源）
├── release/
│   └── 抖音下载器.exe   # 免环境版成品（clone 后双击即用）
├── extensions/
│   └── cookie-export/   # 浏览器扩展：一键导出抖音 Cookie（跨域必需）
├── douyin_cookies.txt   # 【隐私】你的登录 Cookie，由扩展导出后放这里，已被 .gitignore 排除
├── downloads/           # 下载文件默认保存目录
└── ffmpeg/              # 便携 ffmpeg（B站音视频合并需要，见下方安装）
```

## 🚀 安装

要求：Python 3.10+，Windows / macOS / Linux 均可。

```bash
# 1. 进入项目目录，创建虚拟环境（Windows）
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux：
# python -m venv .venv && source .venv/bin/activate

# 2. 安装依赖
pip install requests yt-dlp
```

**ffmpeg（B站下载需要）**：下载 ffmpeg 解压到项目 `ffmpeg\` 目录，确保里面有 `ffmpeg.exe`（或直接 `pip install imageio-ffmpeg`，然后从包内提取 exe 放到 `ffmpeg\`）。没有 ffmpeg 时 B站会失败，抖音不受影响。

## 📱 抖音下载

### 第一步（一次性）：导出登录 Cookie

抖音有严格反爬，必须带你的登录 Cookie 才能解析。本仓库自带一个浏览器扩展来导出：

1. 打开 Edge 的 `edge://extensions/`（Chrome 用 `chrome://extensions/`），开启左下角 **「开发人员模式」**
2. 点 **「加载解压缩的扩展」**，选择本项目的 `extensions\cookie-export` 文件夹
3. 打开 [douyin.com](https://www.douyin.com) 并保持登录
4. 点浏览器工具栏的扩展图标 → **「导出抖音 Cookie」**，浏览器会下载 `douyin_cookies.txt`
5. 把 `douyin_cookies.txt` 移到项目根目录（覆盖已有文件即可）

### 第二步：下载

双击 `douyin.bat`，粘贴分享链接回车即可；或命令行：

```bash
# 单条链接（可粘贴整段分享文案）
.venv\Scripts\python.exe douyin.py "https://v.douyin.com/<id 隐去>/"

# 批量（links.txt 每行一条）
.venv\Scripts\python.exe douyin.py links.txt

# 指定保存目录
.venv\Scripts\python.exe douyin.py "链接" -o 我的目录
```

图集会保存为 `downloads\作者_描述\01.jpg ...`；实况图图集每张图会多一个同编号的 `.mp4`。

## 🎬 B站下载

无需 Cookie。双击 `bilibili.bat`，粘贴链接回车：

- `BV<id 隐去>` —— **裸 BV 号，直接粘贴即可**
- `av123456`
- `b23.tv/xxxxx` 短链
- 完整链接 `https://www.bilibili.com/video/BV...`

1080p / 4K 需要大会员，免费用户自动下载最高可用画质，视频 + 音轨用 ffmpeg 合并为一个 mp4。

## ❓ 常见问题

| 问题 | 解决 |
|---|---|
| 下载时提示 Cookie 失效 / 解析不到内容 | 重新打开 douyin.com 点扩展导出，覆盖 `douyin_cookies.txt` |
| 图集图片带「抖音号」水印 | 更新到最新版；新版默认走无水印源 |
| B站提示 ffmpeg 相关错误 | 确认 `ffmpeg\ffmpeg.exe` 存在（见安装） |
| 抖音视频 403 / 黑屏 | 一般也是 Cookie 过期，重新导出 |

## ⚠️ 免责声明

- 本项目仅供个人学习、归档使用，**请勿将无水印内容二次传播或商用**
- 尊重创作者与平台版权，下载内容仅限本人使用
- 本工具依赖平台接口，接口变动可能导致失效；Cookie 请妥善保管，勿分享给他人
