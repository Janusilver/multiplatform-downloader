# douyin-dl · 抖音图文/视频无水印下载器

功能：粘贴抖音分享链接，下载**图集无水印图片**、**实况图动图 mp4** 或**无水印视频**；另有 **B站下载**（`bilibili.bat`，yt-dlp）。已实测：图集（13/13）、实况图（4/4 mp4）、视频、B站（ffmpeg 合并 mp4）。

## 为什么这样设计（2026-08 实测结论）
- 抖音当前对**无 Cookie 的请求全部返回 JS 反爬/空响应**，旧版纯 requests 方案（无 Cookie）已失效。
- Edge/Chrome 的 Cookie 被 **App-Bound 加密**锁死，外部程序读不了 → 所以用**浏览器扩展**导出完整 Cookie（含 HttpOnly），绕开加密。

## 工作流
1. **导出 Cookie（一次性安装）**：Edge 打开 `edge://extensions/` → 开启左下角"开发人员模式" → "加载解压缩的扩展" → 选 `extensions\cookie-export` 目录 → 打开 `douyin.com` → 点扩展图标 → "导出抖音 Cookie" → 浏览器下载 `douyin_cookies.txt`，移动到项目根目录。
2. **抖音下载**：双击 `douyin.bat`，粘贴链接回车；或命令行（注意用 venv python，本机 `python` 是 Store stub）：

```bash
.venv/Scripts/python.exe douyin.py "https://v.douyin.com/<id 隐去>/"      # 单条
.venv/Scripts/python.exe douyin.py links.txt                         # 批量（每行一条）
.venv/Scripts/python.exe douyin.py "链接" -o 保存目录                # 指定目录
```
3. **B站**：双击 `bilibili.bat`，粘贴 BV/av/b23.tv 链接（无需 Cookie；1080p+ 需登录）。**支持裸输入**：只贴 BV 号/av 号/b23.tv 也会自动补全成完整 URL 再下。

## 实现要点（改前先读）
- `douyin.py`：短链→aweme_id→`aweme/v1/web/aweme/detail` API（带 Cookie，**无需签名**）→ 图集走 `url_list`（**无水印** jpeg，分辨率不变；`download_url_list` 带作者「抖音号」水印，已弃用），视频走 `video.play_addr.url_list` 去 `playwm`。
- **图片 CDN 防盗链：下载图片只能带 UA，不能带 Cookie/Referer**（否则 403）。`download_bare()` 处理。
- 视频下载走带 session 的 `download()`，已实测（`playwm`→`play` 去水印成功）。
- **B站**：`bilibili.bat` 调 yt-dlp `-f "bv*+ba/b"`（视频+音频合并，最高免费画质；1080p60 需大会员）。依赖项目内**便携 ffmpeg**（`ffmpeg/ffmpeg.exe`，从 `imageio-ffmpeg` pip 包提取，无需系统安装/管理员）。
- **图集"会动"分两种**：普通图集作品的 `video.play_addr` 是背景音乐 mp3（非视频），feed 轮播/缩放动效是前端渲染，无视频文件可下（已用 ANIM 帧检测确认纯静态）；但**实况图图集**（`images[i].live_photo_type=1` / `clip_type=5`）每张图**内嵌一个短视频 mp4**（`images[i].video.download_addr`，`watermark=0`），`douyin.py` 会把该张的**静态封面 jpg + 动图 mp4 都下**（同编号 `{i:02d}.jpg` + `{i:02d}.mp4`）。
- 扩展 `extensions\cookie-export`：Manifest V3，`chrome.cookies` 拿 HttpOnly，跳过了无名字的畸形 Cookie（`if (!c.name) continue`）。

## 坑
- **图集水印**：`download_url_list` 是带「抖音号：xxx」水印的高清版（模板含 `~tplv-dy-water-v2:`），`url_list` 是无水印版（`~tplv-dy-aweme-images:q75`，分辨率不变、体积几乎相同）。默认下无水印版。
- Cookie 过期（几周）：重新打开 douyin.com 点扩展导出，覆盖 `douyin_cookies.txt`。
- 私密/已删除/强制登录的作品解析不到。
- 别二次传播无水印作品，仅个人归档。

## 测试
`douyin.py` 已用真实链接实测通过：图集（13/13 原图）、实况图动图（4/4 mp4）、视频（无水印 mp4）。
