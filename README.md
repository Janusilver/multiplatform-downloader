# multiplatform-downloader · 多平台无水印下载器

粘贴分享链接，一键下载**抖音 / 小红书 / 快手**的**无水印图集原图、实况动图、无水印视频**（小红书视频若走网页流可能带小红书号水印）、**B站视频**（BV 号 / av 号 / b23.tv，自动合并画质 + 音轨），以及 **X (Twitter)** 的无水印**单条推文**、**Instagram** 的无水印**帖子 / Reels / 主页批量**。六个平台一个窗口搞定。

> 纯个人工具，仅供**个人归档学习**，尊重创作者版权，请勿二次传播无水印内容。

**[English](README.en.md)**

[![Build](https://img.shields.io/github/actions/workflow/status/Janusilver/multiplatform-downloader/build.yml?label=build)](https://github.com/Janusilver/multiplatform-downloader/actions)
[![GitHub stars](https://img.shields.io/github/stars/Janusilver/multiplatform-downloader?style=flat-square)](https://github.com/Janusilver/multiplatform-downloader/stargazers)
[![GitHub license](https://img.shields.io/badge/license-All%20Rights%20Reserved-lightgrey)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python)](https://www.python.org/)

## 📸 界面预览

| 主界面 | 下载历史 |
|---|---|
| ![主界面](docs/gui-main.png) | ![下载历史](docs/gui-history.png) |

## ✨ 功能特性

| 平台 | 支持内容 | 需要 Cookie |
|---|---|---|
| 抖音 | 图集无水印原图、实况图（封面 jpg + 动图 mp4）、无水印视频 | ✅ 必需 |
| 小红书 | 图文无水印原图、动图 mp4、视频（网页流可能带小红书号水印） | 建议（匿名可能被风控） |
| 快手 | 无水印视频、图集 | 建议（匿名可用） |
| B站 | 视频 + 音轨自动合并，裸 BV 号直接粘贴 | ❌ 不需要 |
| X (Twitter) | 单条推文（视频 / 图片），天然无水印 | 建议（匿名可能被登录墙挡住） |
| Instagram | 帖子图集 / Reels / 用户主页批量，天然无水印 | 建议（匿名大概率失败） |

- ✅ **智能识别链接**：粘贴整段分享文案也能自动提取链接，自动分流到对应平台
- ✅ **剪贴板识别**：复制链接后程序自动检测，输入框上方出现提示条，点一下即可加入下载队列
- ✅ **下载历史**：自动记录每次下载（时间 / 平台 / 链接 / 结果），点「历史」查看，JSON 持久化到 `history.json`
- ✅ **自动检查更新**：启动时后台检测 GitHub 新版本，发现更新弹窗一键跳转下载
- ✅ **批量下载**：txt 每行一个链接，内置限速避免触发风控
- ✅ 失败自动重试、Windows 编码自动处理

## 🚀 免环境版（Windows exe，无需装 Python）

给「不想装 Python」的人：**clone 或下载本仓库后，直接双击 `release\多平台下载器.exe`**，粘贴分享链接即可下载。exe 已内置 Python 运行时、yt-dlp、curl_cffi、ffmpeg，无需任何安装。

**需要的东西**：

| 文件 | 作用 |
|---|---|
| `release\多平台下载器.exe` | 主程序，双击即用 |
| `extensions\cookie-export\` | 浏览器扩展：导出抖音 / 小红书 / 快手 / X / Instagram Cookie（B站不需要） |
| `douyin_cookies.txt` | 抖音 Cookie（必需），放到 exe **旁边** |
| `xhs_cookies.txt` | 小红书 Cookie（建议），放到 exe 旁边 |
| `kuaishou_cookies.txt` | 快手 Cookie（建议），放到 exe 旁边 |
| `twitter_cookies.txt` | X Cookie（建议，匿名可能被登录墙挡住），放到 exe 旁边 |
| `instagram_cookies.txt` | Instagram Cookie（建议，匿名大概率失败），放到 exe 旁边 |

**首次使用（4 步）**：

1. **装扩展**：Edge 打开 `edge://extensions/`（Chrome 用 `chrome://extensions/`）→ 开启左下角「开发人员模式」→「加载解压缩的扩展」→ 选 `cookie-export` 文件夹
2. **导出抖音 Cookie**（必需）：打开 [douyin.com](https://www.douyin.com) 并保持登录 → 点扩展图标 → 导出 → 把 `douyin_cookies.txt` 放到 exe 同目录
3. **导出小红书 / 快手 Cookie**（建议）：分别打开已登录的 [xiaohongshu.com](https://www.xiaohongshu.com) 和 [kuaishou.com](https://www.kuaishou.com)，各点一次导出，同样放到 exe 同目录
4. **导出 X / Instagram Cookie**（下载 X/IG 时建议）：分别打开已登录的 [x.com](https://x.com) 和 [instagram.com](https://www.instagram.com)，各点一次导出，同样放到 exe 同目录
5. **双击 exe**：粘贴链接点「开始下载」，文件保存到 `downloads\`

> 💡 只下 B站：一个 Cookie 都不用。只下抖音：第一步 + 第二步即可。小红书 / 快手不导 Cookie 也能用，但被风控的概率更高。

**⚠️ Windows 提示「已保护你的电脑」**：因为没做代码签名，属正常现象，点「更多信息」→「仍要运行」。

> 想自己打包？先装好 venv 并准备好 `ffmpeg\ffmpeg.exe`（见下「安装」），双击 `build.bat`，输出到 `dist\多平台下载器.exe`（约 56MB，启动解压需等 3–15 秒属正常），并自动复制一份到 `release\`。
>
> 也可以不用本地打包：**push 一个 `v*` 标签或在 Actions 页面手动触发**，[GitHub Actions](.github/workflows/build.yml) 会自动构建 exe 并发布 Release。

## 📦 目录结构

```
multiplatform-downloader/
├── douyin.py            # 抖音核心下载器
├── xhs.py               # 小红书下载器（curl_cffi 伪装 Chrome）
├── kuaishou.py          # 快手下载器（__APOLLO_STATE__ 解析）
├── twitter.py           # X 下载器（yt-dlp 封装）
├── instagram.py         # Instagram 下载器（自研私有 API，curl_cffi 伪装 Chrome TLS）
├── douyin.bat           # 抖音下载入口（双击运行）
├── xhs.bat              # 小红书下载入口（双击运行）
├── kuaishou.bat         # 快手下载入口（双击运行）
├── bilibili.bat         # B站下载入口（双击运行）
├── gui.py               # 六平台一体 GUI 入口（PyInstaller 打包用）
├── build.bat            # 打包入口：装依赖 + 调 build.py
├── build.py             # PyInstaller 打包脚本（自动排除 tcl 干扰源）
├── .github/workflows/   # build.yml 自动打包 release；sync-meta.yml 同步 Release 正文
├── docs/                # 界面截图（README 用）
├── LICENSE              # 保留所有权利（个人学习使用）
├── .gitignore           # Cookie / 下载内容 / 打包产物不提交
├── release/
│   └── 多平台下载器.exe   # 免环境版成品（clone 后双击即用）
├── extensions/
│   └── cookie-export/   # 浏览器扩展：一键导出五平台 Cookie
├── douyin_cookies.txt   # 【隐私】抖音 Cookie，已被 .gitignore 排除
├── xhs_cookies.txt      # 【隐私】小红书 Cookie，已被 .gitignore 排除
├── kuaishou_cookies.txt # 【隐私】快手 Cookie，已被 .gitignore 排除
├── downloads/           # 下载文件默认保存目录
└── ffmpeg/              # 便携 ffmpeg（B站音视频合并需要，见下方安装）
```

## 🚀 安装（源码运行）

要求：Python 3.10+，Windows / macOS / Linux 均可。

```bash
# 1. 进入项目目录，创建虚拟环境（Windows）
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux：
# python -m venv .venv && source .venv/bin/activate

# 2. 安装依赖（curl_cffi 用于小红书/快手反风控）
pip install requests yt-dlp curl_cffi
```

**ffmpeg（B站下载需要）**：下载 ffmpeg 解压到项目 `ffmpeg\` 目录，确保里面有 `ffmpeg.exe`（或直接 `pip install imageio-ffmpeg`，然后从包内提取 exe 放到 `ffmpeg\`）。没有 ffmpeg 时 B站会失败，其他平台不受影响。

## 📱 抖音下载

### 第一步（一次性）：导出登录 Cookie

抖音有严格反爬，必须带你的登录 Cookie 才能解析：

1. 打开 Edge 的 `edge://extensions/`（Chrome 用 `chrome://extensions/`），开启左下角 **「开发人员模式」**
2. 点 **「加载解压缩的扩展」**，选择本项目的 `extensions\cookie-export` 文件夹
3. 打开 [douyin.com](https://www.douyin.com) 并保持登录
4. 点浏览器工具栏的扩展图标 → **「导出抖音 Cookie」**，浏览器会下载 `douyin_cookies.txt`
5. 把 `douyin_cookies.txt` 移到项目根目录（覆盖已有文件即可）

### 第二步：下载

双击 `douyin.bat`，粘贴分享链接回车即可；或命令行：

```bash
.venv\Scripts\python.exe douyin.py "https://v.douyin.com/xxxx/"
.venv\Scripts\python.exe douyin.py links.txt          # 批量
.venv\Scripts\python.exe douyin.py "链接" -o 我的目录  # 指定目录
```

不带 `-o` 时默认保存到脚本所在目录的 `downloads\`（与运行目录无关）。图集会保存为 `downloads\作者_描述\01.jpg ...`；实况图图集每张图会多一个同编号的 `.mp4`。

## 📕 小红书下载

支持 `xhslink.com` 短链、`explore/{id}`、`discovery/item/{id}`、`user/profile/{uid}/{id}`。建议先登录导出 `xhs_cookies.txt`（匿名可用，但可能被风控拦成 404 页）。

```bash
.venv\Scripts\python.exe xhs.py "https://xhslink.com/xxxx/"
.venv\Scripts\python.exe xhs.py links.txt
```

- **图片**：优先用 `imageList[].fileId` 拼 **sns-img-bd 原图直链**（无水印原图；旧结构笔记退回 CDN token 还原）
- **视频**：优先下载 `originVideoKey` **原始无水印文件**；但 2026-08 实测网页端多数笔记已不暴露该字段，退回最高清网页流（**可能带小红书号水印**，日志会提示）
- **动图（Live Photo）**：每张图额外下载内嵌的 mp4

## 🟠 快手下载

支持 `v.kuaishou.com` 短链、`short-video/{id}`、`f/{id}`、`v.m.chenzhongtech.com/fw/photo/{id}`。匿名可用，登录导出 `kuaishou_cookies.txt` 更稳。

```bash
.venv\Scripts\python.exe kuaishou.py "https://v.kuaishou.com/xxxx/"
.venv\Scripts\python.exe kuaishou.py links.txt
```

视频自动选**最高画质档**（按分辨率+码率排序；实测 H264 720p/3.4Mbps 与 H265 720p/2Mbps 均**无水印**，优先高码率 H264）；图集走 `ext_params.atlas`。

## 🎬 B站下载

无需 Cookie。双击 `bilibili.bat`，粘贴链接回车：

- `BV19tge67EQ4` —— **裸 BV 号，直接粘贴即可**
- `av123456`
- `b23.tv/xxxxx` 短链
- 完整链接 `https://www.bilibili.com/video/BV...`

1080p / 4K 需要大会员，免费用户自动下载最高可用画质，视频 + 音轨用 ffmpeg 合并为一个 mp4。

## 🐦 X / 📷 Instagram 下载

- **X**：走 yt-dlp，支持**单条推文**（`/status/ID`）；**主页批量暂不支持**（yt-dlp 无 X 用户主页提取器）。媒体是原始 CDN 直链，**天然无水印**。
- **Instagram**：自研私有 API（curl_cffi 伪装 Chrome TLS），支持**单条**（帖子 / Reels）与**用户主页批量**；图集 / 轮播**全媒体提取**（图片 + 视频一次全下）。

```bash
.venv\Scripts\python.exe twitter.py "https://x.com/user/status/123"            # X 单条推文
.venv\Scripts\python.exe instagram.py "https://www.instagram.com/p/CxAb12345/" # 帖子（图集全提取）
.venv\Scripts\python.exe instagram.py "https://www.instagram.com/reel/AbC/"    # Reels
.venv\Scripts\python.exe instagram.py "https://www.instagram.com/user/" --max 10  # 主页批量
```

> **前提**：X 现需登录态（匿名可能被登录墙挡住）；IG 需登录 session（匿名大概率失败）——用浏览器扩展导出 `twitter_cookies.txt` / `instagram_cookies.txt` 放脚本 / exe 旁。
>
> **代理**：两平台服务器在国外，国内直连不稳。GUI「代理」框**启动时自动读取系统代理**（Clash 等开了「系统代理」就自动填入 `127.0.0.1:7890`），也可手动改 / 清空；CLI 不传 `--proxy` 时同样自动检测。国内四平台不受影响，留空即直连。

## ❓ 常见问题

| 问题 | 解决 |
|---|---|
| 抖音下载提示 Cookie 失效 / 解析不到内容 | 重新打开 douyin.com 点扩展导出，覆盖 `douyin_cookies.txt` |
| 小红书提示「笔记数据获取失败」 | 裸 `explore/{id}` 链接会被风控，改用**分享链接**（带 xsec_token，如 xhslink 短链）重试；或导出 `xhs_cookies.txt` 后重试；或链接本身已删除 |
| 快手提示「页面无 __APOLLO_STATE__」 | 同样先导出 `kuaishou_cookies.txt`；或链接已删除 |
| 小红书视频带「小红书号」水印 | 该笔记没有原始文件源（originVideoKey），网页流自带水印；属于平台行为，暂无法绕过 |
| 图集图片带水印 | 更新到最新版；新版默认走无水印源 |
| B站提示 ffmpeg 相关错误 | 确认 `ffmpeg\ffmpeg.exe` 存在（见安装） |
| exe 双击没反应 / 一直转圈 | **首次启动**需解压 55MB + Defender 扫描，等 30–60 秒属正常（鼠标转圈）；第二次起只需 3–15 秒；报错看同目录 `error.log` |
| 改了代码重新打包，启动还提示去 GitHub 下载更新 | 更新检测比对的是「exe 内置版本号 vs GitHub 最新 Release tag」；改了代码但没升 `APP_VERSION`（gui.py 顶部）就打包，exe 版本仍落后就会提示。改代码打包前记得同步升版本号并打新 tag |
| X 提示登录墙 / 下不动 | 导出 `twitter_cookies.txt`；X 服务器在国外，GUI「代理」框或 CLI `--proxy` 填代理地址（如 `http://127.0.0.1:7890`） |
| Instagram 下载失败 | 导出 `instagram_cookies.txt`（匿名大概率失败）；国外 CDN 需代理，同上 |
| 贴了链接却提示「未找到 XX 链接」 | 出于安全只接受**平台自家域名**（`v.douyin.com` / `xhslink.com` / `v.kuaishou.com` 及各主站域名）。站外链接即使文本里带平台域名关键词也会被拒——这是防止把你的登录 Cookie 发给第三方站点。另外短链跳转全程**不携带 Cookie** |

## ⚠️ 免责声明

- 本项目仅供个人学习、归档使用，**请勿将无水印内容二次传播或商用**
- 尊重创作者与平台版权，下载内容仅限本人使用
- 本工具依赖平台接口，接口变动可能导致失效；Cookie 请妥善保管，勿分享给他人
