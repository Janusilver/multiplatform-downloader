# multiplatform-downloader · 多平台无水印下载器

功能：粘贴分享链接，下载**抖音 / 小红书 / 快手**的图集无水印图片、实况动图、无水印视频；另有 **B站下载**（yt-dlp）。已实测：抖音图集（13/13）、实况图（4/4 mp4）、视频、B站（ffmpeg 合并 mp4）；小红书图文（3/3 原图）+ 视频、快手视频（匿名/带 Cookie）。

## 为什么这样设计（2026-08 实测结论）
- 抖音当前对**无 Cookie 的请求全部返回 JS 反爬/空响应**，旧版纯 requests 方案（无 Cookie）已失效。
- Edge/Chrome 的 Cookie 被 **App-Bound 加密**锁死，外部程序读不了 → 所以用**浏览器扩展**导出完整 Cookie（含 HttpOnly），绕开加密。
- 小红书/快手对 requests 的 **TLS 指纹有风控**：requests 直连详情页会被 302 到 404/sec 风控页或 JS 挑战。解法是 **curl_cffi**（`impersonate="chrome"`，伪装真实 Chrome TLS 指纹）——requests 保留给 CDN 下载直链用。
- 小红书**匿名（无 Cookie）访问笔记详情页必被风控**；快手匿名 + curl_cffi 可过首页，但搜索接口有验证码。登录导出 Cookie 是最稳路径。

## 工作流
1. **导出 Cookie（一次性安装）**：Edge 打开 `edge://extensions/` → 开启左下角"开发人员模式" → "加载解压缩的扩展" → 选 `extensions\cookie-export` 目录 → 打开各站点并保持登录 → 点扩展图标分别导出 → 把 `douyin_cookies.txt` / `xhs_cookies.txt` / `kuaishou_cookies.txt` 移到项目根目录。
2. **命令行下载**（注意用 venv python，本机 `python` 是 Store stub）：

```bash
.venv/Scripts/python.exe douyin.py "链接" [-o 目录] [-c cookie文件]   # 抖音
.venv/Scripts/python.exe xhs.py "链接" [-o 目录] [-c cookie文件]      # 小红书
.venv/Scripts/python.exe kuaishou.py "链接" [-o 目录] [-c cookie文件] # 快手
```

不带 `-o` 时默认保存到**脚本所在目录**的 `downloads/`（与运行目录无关，从哪跑都固定落同一处）。
3. **GUI / exe**：`gui.py` 自动分流四个平台，Cookie 文件名固定为 exe 同目录的 `douyin_cookies.txt` / `xhs_cookies.txt` / `kuaishou_cookies.txt`；**下载历史**自动记录到 exe 同目录 `history.json`（时间/平台/链接/结果，上限 200 条，点「历史」按钮查看，已被 .gitignore 排除）。**自动检查更新**：`APP_VERSION` 版本号 + `latest_release()`（启动线程查 GitHub latest release，直连失败回退 `127.0.0.1:7890` 代理，不打扰用户）→ 有新版本主线程弹窗跳转下载页；**发新版本 = 改 `APP_VERSION` + 打 `v*` tag**（CI 自动出包 + sync-meta 填 Release 正文）。README 有中英双版本（README.md / README.en.md，顶部互链）。
4. **B站**：双击 `bilibili.bat`，粘贴 BV/av/b23.tv 链接（无需 Cookie；1080p+ 需登录）。**支持裸输入**：只贴 BV 号/av 号/b23.tv 也会自动补全成完整 URL 再下。

## 实现要点（改前先读）
- `douyin.py`：短链→aweme_id→`aweme/v1/web/aweme/detail` API（带 Cookie，**无需签名**）→ 图集走 `url_list`（**无水印** jpeg，分辨率不变；`download_url_list` 带作者「抖音号」水印，已弃用），视频走 `video.play_addr.url_list` 去 `playwm`，**失败时用 snssdk 直链兜底**（`play_addr.uri` 即 video_id：`https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0`，2026-08-15 新增，纯增量未单独实测）。
- **图片 CDN 防盗链：下载图片只能带 UA，不能带 Cookie/Referer**（否则 403）。`download_bare()` 处理。
- 视频下载走带 session 的 `download()`，已实测（`playwm`→`play` 去水印成功）。
- `xhs.py`：链接→笔记 ID→curl_cffi GET `explore/{id}?xsec_token=...&xsec_source=...`（分享链接跳转后自带 xsec；裸 `explore/{id}` 无 xsec 会被风控 302 到 404/sec 页，会尝试从首页 feed 借 xsecToken）→ 解析 `window.__INITIAL_STATE__` 的 `note.noteDetailMap[id].note`。**`__INITIAL_STATE__` 混有 JS 字面量**（`undefined`、`new Map([])`），`json.loads` 前必须 `clean_js()` 清洗。**原图**：`imageList[].fileId` → `https://sns-img-bd.xhscdn.com/{fileId}`（无水印原图；旧字段 urlDefault 是 webp 压缩预览，直接拼会 404）；**实况图**：`imageList[].stream.EF4[0].masterUrl`；**视频**：优先 `video.consumer.originVideoKey`（原始无水印），退回 `video.media.stream` 的 EF4/EF5/EF7/EF6/h264/h265 各流 masterUrl（列表升序，取最后最高清）。**视频笔记判断**：`note.type=="video"` 优先于 imageList（视频笔记的 imageList 有 1~3 张封面，不能当图集下）。CDN 下载只带 UA（`download()`）。
- `kuaishou.py`：链接→photoId（短链跳转后 URL/query 里取）→ curl_cffi GET `short-video/{id}` → 解析 `window.__APOLLO_STATE__`（JSON 尾部有 IIFE，需剥掉 `;(function(){var s;...}());`）的 `defaultClient["VisionVideoDetailPhoto:{id}"]`。**水印结论（2026-08-15 实测+用户目检）**：快手网页的 H264（`photoUrl`/`manifest`，upic 路径）与 H265（`manifestH265`/`photoH265Url`，bs2 路径）**都不带平台水印**。**选档策略**：`video_urls()` 收集 H264+H265 全部候选（分辨率、码率），按（height, avgBitrate）降序取第一个=最佳画质（实测同 720p 时 H264 3.4Mbps 优于 H265 2Mbps）。manifest 是 Apollo 引用（`{"type":"id","id":"..."}`），必须用 `resolve_ref()` 递归到 `defaultClient` 取真实 `url`（`backupUrl` 是 `{"type":"json","json":[...]}`）。**图集**：`ext_params.atlas`（JSON 字符串/列表）里的 cdnUrls。作者昵称从 `VisionVideoDetailAuthor:{uid}` 取。CDN 下载要带 `Referer: https://www.kuaishou.com/`。App 接口（`v.m.chenzhongtech.com/rest/wd/photo/info`）2026-08 起需要签名（`result:50 签名验证失败`），未实现。
- **B站**：`bilibili.bat` 调 yt-dlp `-f "bv*+ba/b"`（视频+音频合并，最高免费画质；1080p60 需大会员）。依赖项目内**便携 ffmpeg**（`ffmpeg/ffmpeg.exe`，从 `imageio-ffmpeg` pip 包提取，无需系统安装/管理员）。
- **图集"会动"分两种**：普通图集作品的 `video.play_addr` 是背景音乐 mp3（非视频），feed 轮播/缩放动效是前端渲染，无视频文件可下（已用 ANIM 帧检测确认纯静态）；但**实况图图集**（`images[i].live_photo_type=1` / `clip_type=5`）每张图**内嵌一个短视频 mp4**（`images[i].video.download_addr`，`watermark=0`），`douyin.py` 会把该张的**静态封面 jpg + 动图 mp4 都下**（同编号 `{i:02d}.jpg` + `{i:02d}.mp4`）。
- 扩展 `extensions\cookie-export`：Manifest V3，`chrome.cookies` 拿 HttpOnly，跳过了无名字的畸形 Cookie（`if (!c.name) continue`）。**三平台版**：`SITES` 字典配置 抖音/小红书/快手 的域名与导出文件名。
- 打包：`build.py` 需 `--collect-all curl_cffi`（否则 exe 里小红书/快手报缺 DLL）；GitHub Actions（`.github/workflows/build.yml`）用 imageio-ffmpeg 提取便携 ffmpeg，push `v*` 标签自动出 Release。

## 坑
- **图集水印**：`download_url_list` 是带「抖音号：xxx」水印的高清版（模板含 `~tplv-dy-water-v2:`），`url_list` 是无水印版（`~tplv-dy-aweme-images:q75`，分辨率不变、体积几乎相同）。默认下无水印版。
- **实况图动图水印**（2026-08-19 实测）：内嵌视频的 `download_addr.url_list[0]` **不保证是 `watermark=0`**，服务端可能把 `watermark=1` 档排在 `[0]`（同一 video_id 下 `watermark=0` → 干净 294KB，`watermark=1` → 带水印 503KB，实测参数交换有效）。下载前必须 `.replace("watermark=1", "watermark=0")` 归一，不能直接取 `url_list[0]`。
- **小红书 `__INITIAL_STATE__` 是 JS 赋值的 JSON**，混有 `undefined` / `new Map([])` 等字面量，必须先 `clean_js()` 清洗再 `json.loads`。被风控时页面是 404/sec 页，特征是 900KB 左右、`sec_` 出现在跳转 URL 里。
- **快手 `__APOLLO_STATE__` 有 IIFE 尾巴**，必须替换掉才能 `json.loads`。
- Cookie 过期（几周）：重新打开对应站点点扩展导出，覆盖对应 cookies.txt。
- 私密/已删除/强制登录的作品解析不到。
- 别二次传播无水印作品，仅个人归档。

## 测试
- `douyin.py` 已用真实链接实测通过：图集（13/13 原图）、实况图动图（4/4 mp4）、视频（无水印 mp4）。
- `kuaishou.py` 已实测通过（2026-08-15）：真实作品页链接（`short-video/<id 隐去>`），匿名与带 Cookie 均成功。**水印排查结论（用户目检确认）**：H264（4.89MB）与 H265（2.93MB）都**没有**水印；曾误判 H264 带水印（实为小红书视频）。已改为按（分辨率,码率）选最佳画质（优先 H264 高码率）。App 接口需签名（`result:50`），未实现。
- `xhs.py` 已实测通过（2026-08-15，带登录 Cookie）：图文笔记 3/3 原图（走 `fileId` → `sns-img-bd.xhscdn.com`）、视频笔记 mp4（`media.stream.EF4` 最高清）。**视频水印（最终结论）**：网页流（sns-video-v2）带「小红书号」水印；**网页端数据层已彻底不暴露干净源**——8/8 视频笔记的 SSR `video` 只有 `media/mediaV2/image/capa`，无 `consumer.originVideoKey`；真浏览器（playwright + `_webmsxyw` 签名 + 注入 Cookie）调 feed API 能过风控（code 0）但数据空/minimal，也拿不到 originVideoKey（风控还会在 code 0 / code -101 间横跳）。**结论：小红书视频水印在网页接口下无解**（数据层封死，非签名问题），保持页面解析 + 水印提示。实况图（Live Photo）代码已支持（`imageList[].stream.EF4` masterUrl），已实测通过（3 图+3 mp4）。裸 `explore/{id}` 无 xsec 会被风控，需分享链接（带 xsec_token）或恰好出现在首页 feed。playwright 曾用于探索小红书签名（2026-08-15），已卸载，不打包。
- 打包：本地 PyInstaller 实测通过（55.8MB，curl_cffi 已进包）。
