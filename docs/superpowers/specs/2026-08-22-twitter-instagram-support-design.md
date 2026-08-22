# 设计：Twitter/X + Instagram 下载支持（v1.3.0）

日期：2026-08-22
状态：已获用户批准（2026-08-22）

## 背景与目标

多平台无水印下载器（douyin-dl）当前支持抖音/小红书/快手（自研解析）+ B站（yt-dlp）。
目标：加入 **Twitter/X** 和 **Instagram** 两个平台，支持**单条分享链接**和**用户主页批量**下载，
并完整集成到 CLI、GUI、exe 打包与公开发布流程。

需求约束（已与用户确认）：

- 平台范围：Twitter/X + Instagram 两个都做。
- 粒度：单条链接下载 + 用户主页批量（默认最近 50 条）。
- 前提：两平台需登录 Cookie + 代理；用户接受导 Cookie 流程。
- 项目会公开发布，不能只适配作者本机（代理不能硬编码，需可配置）。

## 实现路线

**复用 yt-dlp**（已装 2026.7.4，B站同一条路），新建薄封装脚本，解析全交给 yt-dlp 内置的
Twitter / Instagram 提取器。理由：

- 零新依赖；维护模式与 B站 一致（平台反爬变化 → 社区跟进 → 我们只升 yt-dlp 重打包）。
- 无水印天然满足（X/IG 原始 CDN 直链不带平台水印）。
- 浏览器扩展导出的 cookies.txt（Netscape 格式）yt-dlp 直接可用。

## 架构与组件

| 文件 | 动作 | 内容 |
|---|---|---|
| `twitter.py` | 新建 | 薄封装 yt-dlp 的 CLI。识别 X 单条推文（`x.com/<user>/status/<id>` / `twitter.com/...`）和用户主页（`x.com/<user>`），构造 yt-dlp 参数并下载 |
| `instagram.py` | 新建 | 同上。识别 IG 帖子（`instagram.com/p/<id>`）、Reels（`/reel/<id>`）、用户主页（`/<user>`） |
| `gui.py` | 修改 | `classify()` 加两个正则分支；把 B站 的 yt-dlp 调用抽成共用 `_run_ytdlp()`，X/IG/B站 三个平台共用；标题、欢迎语、剪贴板识别、平台名映射加两平台；新增「代理」输入框 |
| `extensions/cookie-export` | 修改 | `popup.js` 的 `SITES` 加 X（`x.com`/`twitter.com` → `twitter_cookies.txt`）与 IG（`instagram.com` → `instagram_cookies.txt`）；`manifest.json` 的 `host_permissions` 加对应域名 |
| `README.md` / `README.en.md` | 修改 | 加两平台用法、Cookie 导出、代理配置说明 |
| `.github/workflows/build.yml` | 不改 | `pip install yt-dlp` 装最新版 + 已 `--collect-all yt_dlp` |

## 关键设计决策

1. **Cookie**：`twitter_cookies.txt` / `instagram_cookies.txt`，浏览器扩展导出（Netscape 格式，
   含 HttpOnly），命名与位置跟现有 `douyin_cookies.txt` 一致（exe 同目录）。扩展是 MV3 +
   `chrome.cookies`，Chrome/Edge 通用，无需为不同浏览器单独开发。
2. **代理可配置（公开发布要求）**：不硬编码 `127.0.0.1:7890`。
   - GUI：新增「代理」输入框（留空 = 直连；填了 = 传给 yt-dlp 的 `proxy` 选项）。
   - CLI：`--proxy` 参数（默认空 = 直连），与 GUI 输入框共用语义。
   - README 说明：X/IG 建议配置代理（国内直连不稳定），但软件不强制。
3. **匿名兜底**：无 Cookie 时也尝试下载（yt-dlp 自己试 guest token / 匿名态），失败再提示
   「请导 Cookie」。X/IG 强制匿名大概率失败，但给普通用户试错机会。
4. **输出命名**（与 B站 风格一致，用 yt-dlp 的 outtmpl）：
   - 单条：`%(uploader)s_%(id)s_%(playlist_index)02d.%(ext)s`（多图/多视频有序号）
   - 主页批量：`%(uploader)s/%(id)s_%(title)s.%(ext)s`（按作者建子目录）
   - `--windows-filenames` 交给 yt-dlp 默认处理。
5. **批量上限**：默认 `--playlist-items 1:50`（最近 50 条），CLI `--max N` 调整。
6. **内容形态**：视频 + 图片全下。X 纯文字推文无媒体 → 提示「该推文无媒体」，不报错。

## 数据流

```
粘贴链接 → classify() 识别平台
  ├─ twitter / instagram → _run_ytdlp(url, 平台名)
  │     构造 opts：cookies（若存在）、proxy（若配置）、outtmpl、quiet、no_warnings
  │     yt_dlp.YoutubeDL(opts).download([url]) → downloads/
  └─ bili → 同一 _run_ytdlp()（B站 复用）
```

`_run_ytdlp()` 共用函数签名：`_run_ytdlp(url, name, cookies_path=None, proxy="", outtmpl=..., max_items=None)`。
B站 调用时额外追加 `ffmpeg_location`（便携 ffmpeg）和 `progress_hooks`（进度回调），这两项作为
B站 专属参数保留在调用处，不进共用函数主体。

**URL 识别顺序**（`classify()` 内正则匹配优先级）：
- X：先匹配 `x.com/twitter.com/<user>/status/<id>`（单条），再匹配 `x.com/<user>`（主页批量）。
- IG：先匹配 `/p/<id>`、`/reel/<id>`、`/tv/<id>`（单条），再匹配 `/<user>`（主页批量）；
  排除 `/accounts/`、`/direct/`、`/explore/` 等系统路径。

CLI：`.venv/Scripts/python.exe twitter.py "链接" [-o 目录] [-c cookie] [--proxy http://...] [--max N]`。

## 错误处理

- Cookie 缺失：不阻断，匿名试一次；yt-dlp 失败后提示导 Cookie（沿用现有「扩展导出」文案）。
- 代理不通 / 直连失败：yt-dlp 报错透传到日志，提示检查网络/代理配置。
- 链接失效 / 私密 / 需登录：yt-dlp 报错透传。
- 纯文字推文：无媒体时给明确提示，不当作失败。

## 测试计划

1. 本机实测 4 场景：X 单条视频、X 用户主页批量、IG 单条图集、IG Reels + IG 用户主页
   （需更新扩展 → Chrome 导 `twitter_cookies.txt` / `instagram_cookies.txt`，7890 在线）。
2. GUI 手动跑一轮（含代理输入框、剪贴板识别两平台）。
3. 无水印目检：下载文件确认无平台水印。
4. 全部通过 → `APP_VERSION` 1.2.1 → 1.3.0 → 本地 PyInstaller 打包验证 → 打 `v1.3.0` tag
   自动发 Release（CI 不变）。

## 发布注意

- commit 用项目级 noreply 匿名身份（已配置，无需每次覆盖）。
- `.gitignore` 确认 `twitter_cookies.txt` / `instagram_cookies.txt` 被排除（现有 cookie 文件
  已被忽略，需确认新增文件名也在忽略范围内，否则公开仓库泄露登录态）。
