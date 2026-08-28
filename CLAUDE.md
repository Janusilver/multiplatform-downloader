# multiplatform-downloader · 多平台无水印下载器

功能：粘贴分享链接，下载**抖音 / 小红书 / 快手 / Instagram / X (Twitter)** 的图集无水印图片、实况动图、无水印视频；另有 **B站下载**（yt-dlp）。已实测：抖音图集（13/13）、实况图（4/4 mp4）、视频、B站（ffmpeg 合并 mp4）；小红书图文（3/3 原图）+ 视频、快手视频（匿名/带 Cookie）。另有 **Instagram**（单条/Reels/用户主页批量）与 **X**（单条推文，yt-dlp）——这两块真实媒体下载**待实测**（见「测试」）。

## 为什么这样设计（2026-08 实测结论）
- 抖音当前对**无 Cookie 的请求全部返回 JS 反爬/空响应**，旧版纯 requests 方案（无 Cookie）已失效。
- Edge/Chrome 的 Cookie 被 **App-Bound 加密**锁死，外部程序读不了 → 所以用**浏览器扩展**导出完整 Cookie（含 HttpOnly），绕开加密。
- 小红书/快手对 requests 的 **TLS 指纹有风控**：requests 直连详情页会被 302 到 404/sec 风控页或 JS 挑战。解法是 **curl_cffi**（`impersonate="chrome"`，伪装真实 Chrome TLS 指纹）——requests 保留给 CDN 下载直链用。
- 小红书**匿名（无 Cookie）访问笔记详情页必被风控**；快手匿名 + curl_cffi 可过首页，但搜索接口有验证码。登录导出 Cookie 是最稳路径。
- **Instagram / X 是国外站**，走代理（`--proxy` 或系统代理）。IG 网页端是服务端渲染 + 签名接口，拿不全媒体，改用**私有 API**（`i.instagram.com/api/v1`）拿完整媒体数据；X 媒体是平台原始 CDN 直链，天然无水印，直接交 **yt-dlp** 最省事（免手动解析、免去水印）。

## 工作流
1. **导出 Cookie（一次性安装）**：Edge 打开 `edge://extensions/` → 开启左下角"开发人员模式" → "加载解压缩的扩展" → 选 `extensions\cookie-export` 目录 → 打开各站点并保持登录 → 点扩展图标分别导出 → 把 `douyin_cookies.txt` / `xhs_cookies.txt` / `kuaishou_cookies.txt` / `instagram_cookies.txt` / `twitter_cookies.txt` 移到项目根目录。**前三平台可选**（小红书/快手匿名可用但可能风控，抖音必须），**X 可选**（匿名试一次，可能被登录墙），**Instagram 必需**（匿名拿不到数据）。
2. **命令行下载**（注意用 venv python，本机 `python` 是 Store stub）：

```bash
.venv/Scripts/python.exe douyin.py "链接" [-o 目录] [-c cookie文件]   # 抖音
.venv/Scripts/python.exe xhs.py "链接" [-o 目录] [-c cookie文件]      # 小红书
.venv/Scripts/python.exe kuaishou.py "链接" [-o 目录] [-c cookie文件] # 快手
.venv/Scripts/python.exe instagram.py "链接" [-o 目录] [-c cookie文件] [--proxy 代理] [--max N]  # Instagram（需 Cookie）
.venv/Scripts/python.exe twitter.py "链接" [-o 目录] [-c cookie文件] [--proxy 代理]  # X 单条推文（yt-dlp）
```

不带 `-o` 时默认保存到**脚本所在目录**的 `downloads/`（与运行目录无关，从哪跑都固定落同一处）。`douyin`/`xhs`/`kuaishou` 三脚本支持**裸输入**：直接贴链接（或含链接文本 / `txt` 文件每行一条）；`instagram` 还支持**用户主页批量**（默认最多 `--max` 50 条）；`twitter` **只支持单条 `/status/ID`**（主页批量 yt-dlp 不支持）。
3. **GUI / exe**：`gui.py` 自动分流六个平台，Cookie 文件名固定为 exe 同目录的 `douyin_cookies.txt` / `xhs_cookies.txt` / `kuaishou_cookies.txt` / `twitter_cookies.txt` / `instagram_cookies.txt`；**下载历史**自动记录到 exe 同目录 `history.json`（时间/平台/链接/结果，上限 200 条，点「历史」按钮查看，已被 .gitignore 排除）。**自动检查更新**：`APP_VERSION` 版本号 + `latest_release()`（启动线程查 GitHub latest release，直连失败回退 `127.0.0.1:7890` 代理，不打扰用户）→ 有新版本主线程弹窗跳转下载页；**发新版本 = 改 `APP_VERSION` + 打 `v*` tag**（CI 自动出包 + sync-meta 填 Release 正文）。README 有中英双版本（README.md / README.en.md，顶部互链）。
4. **B站**：双击 `bilibili.bat`，粘贴 BV/av/b23.tv 链接（无需 Cookie；1080p+ 需登录）。**支持裸输入**：只贴 BV 号/av 号/b23.tv 也会自动补全成完整 URL 再下。

## 实现要点（改前先读）
- `douyin.py`：短链→aweme_id→`aweme/v1/web/aweme/detail` API（带 Cookie，**无需签名**）→ 图集走 `url_list`（**无水印** jpeg，分辨率不变；`download_url_list` 带作者「抖音号」水印，已弃用），视频走 `video.play_addr.url_list` 去 `playwm`，**失败时用 snssdk 直链兜底**（`play_addr.uri` 即 video_id：`https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0`，2026-08-15 新增，纯增量未单独实测）。
- **图片 CDN 防盗链：下载图片只能带 UA，不能带 Cookie/Referer**（否则 403）。`download()` 处理（douyin.py 的通用下载函数，xhs/kuaishou 复用；带 session / 自定义 headers 时供视频等场景用）。
- 视频下载走带 session 的 `download()`，已实测（`playwm`→`play` 去水印成功）。
- `xhs.py`：链接→笔记 ID→curl_cffi GET `explore/{id}?xsec_token=...&xsec_source=...`（分享链接跳转后自带 xsec；裸 `explore/{id}` 无 xsec 会被风控 302 到 404/sec 页，会尝试从首页 feed 借 xsecToken）→ 解析 `window.__INITIAL_STATE__` 的 `note.noteDetailMap[id].note`。**`__INITIAL_STATE__` 混有 JS 字面量**（`undefined`、`new Map([])`），`json.loads` 前必须 `clean_js()` 清洗。**原图**：`imageList[].fileId` → `https://sns-img-bd.xhscdn.com/{fileId}`（无水印原图；旧字段 urlDefault 是 webp 压缩预览，直接拼会 404）；**实况图**：`imageList[].stream.EF4[0].masterUrl`；**视频**：优先 `video.consumer.originVideoKey`（原始无水印），退回 `video.media.stream` 的 EF4/EF5/EF7/EF6/h264/h265 各流 masterUrl（列表升序，取最后最高清）。**视频笔记判断**：`note.type=="video"` 优先于 imageList（视频笔记的 imageList 有 1~3 张封面，不能当图集下）。CDN 下载只带 UA（`download()`）。
- `kuaishou.py`：链接→photoId（短链跳转后 URL/query 里取）→ curl_cffi GET `short-video/{id}` → 解析 `window.__APOLLO_STATE__`（JSON 尾部有 IIFE，需剥掉 `;(function(){var s;...}());`）的 `defaultClient["VisionVideoDetailPhoto:{id}"]`。**水印结论（2026-08-15 实测+用户目检）**：快手网页的 H264（`photoUrl`/`manifest`，upic 路径）与 H265（`manifestH265`/`photoH265Url`，bs2 路径）**都不带平台水印**。**选档策略**：`video_urls()` 收集 H264+H265 全部候选（分辨率、码率），按（height, avgBitrate）降序取第一个=最佳画质（实测同 720p 时 H264 3.4Mbps 优于 H265 2Mbps）。manifest 是 Apollo 引用（`{"type":"id","id":"..."}`），必须用 `resolve_ref()` 递归到 `defaultClient` 取真实 `url`（`backupUrl` 是 `{"type":"json","json":[...]}`）。**图集**：`ext_params.atlas`（JSON 字符串/列表）里的 cdnUrls。作者昵称从 `VisionVideoDetailAuthor:{uid}` 取。CDN 下载要带 `Referer: https://www.kuaishou.com/`。App 接口（`v.m.chenzhongtech.com/rest/wd/photo/info`）2026-08 起需要签名（`result:50 签名验证失败`），未实现。
- `instagram.py`：IG 私有 API 自研。流程：链接 → shortcode → `_shortcode_to_pk`（base64 短码转数字 pk，`_CHARS` 表顺序 `A-Z a-z 0-9 - _`）→ `i.instagram.com/api/v1/media/{pk}/info/`；**用户主页**走 `users/web_profile_info/?username={u}` 拿 uid → `feed/user/{uid}` 分页拉（默认最多 `--max` 50），可批量全媒体。**必需 Cookie**（扩展导 `instagram_cookies.txt`，匿名拿不到数据）；IG API 对 requests TLS 指纹风控 429，**必须 `curl_cffi` 伪装 Chrome**（`impersonate="chrome"`）。**代理**：IG CDN 在海外，接口与下载都走 `--proxy`，无则自动 `detect_system_proxy()` 读系统代理。媒体提取 `extract_media` 递归：`media_type` 1=图 / 2=视频 / 8=图集（`carousel_media` 递归）；图片取 `image_versions2.candidates` 面积最大，视频取 `video_versions` 面积最大。**命名技巧**：图集不用 `Path.with_suffix`——作者名含点（如 `xx.uyvn`）时 `.with_suffix` 把点后当扩展名替换，导致多项目互相覆盖；用字符串拼接 `{shortcode}_{idx}` + `.part` + `os.replace` 原子改名。
- `twitter.py`（X）：yt-dlp 封装。流程：识别 `/status/ID` 单条 → 交 yt-dlp（`cookiefile` + 可选 proxy），`outtmpl`=`%(uploader)s_%(id)s.%(ext)s`，`nooverwrites` 跳过已存在。**用户主页批量 yt-dlp 不支持**（无主页提取器，只认 `/status/ID`），`is_profile` 检测到主页时明确提示局限。X 媒体为平台原始 CDN 直链，**天然无水印**（无需去水印处理，区别于抖音）。无 Cookie 匿名试一次，可能被登录墙挡。
- **B站**：`bilibili.bat` 调 yt-dlp `-f "bv*+ba/b"`（视频+音频合并，最高免费画质；1080p60 需大会员）。依赖项目内**便携 ffmpeg**（`ffmpeg/ffmpeg.exe`，从 `imageio-ffmpeg` pip 包提取，无需系统安装/管理员）。
- **图集"会动"分两种**：普通图集作品的 `video.play_addr` 是背景音乐 mp3（非视频），feed 轮播/缩放动效是前端渲染，无视频文件可下（已用 ANIM 帧检测确认纯静态）；但**实况图图集**（`images[i].live_photo_type=1` / `clip_type=5`）每张图**内嵌一个短视频 mp4**（`images[i].video.download_addr`，`watermark=0`），`douyin.py` 会把该张的**静态封面 jpg + 动图 mp4 都下**（同编号 `{i:02d}.jpg` + `{i:02d}.mp4`）。
- 扩展 `extensions\cookie-export`：Manifest V3，`chrome.cookies` 拿 HttpOnly，跳过了无名字的畸形 Cookie（`if (!c.name) continue`）。**五平台版**：`SITES` 字典配置 抖音/小红书/快手/X/Instagram 的域名与导出文件名（`.x.com` + `.instagram.com`，X 用 `.x.com` 而非 `twitter.com` 域）。
- 打包：`build.py` 需 `--collect-all curl_cffi`（否则 exe 里小红书/快手报缺 DLL）；GitHub Actions（`.github/workflows/build.yml`）用 imageio-ffmpeg 提取便携 ffmpeg，push `v*` 标签自动出 Release。

## 坑
- **抖音 web 接口签名（2026-08-25 复核更正，签名非必需）**：`aweme/v1/web/aweme/detail` **不需要** `a_bogus`/`X-Bogus`/`msToken` 签名。当天早先收到「status 200 + 空 body」，一度误判为签名加固，于是跑通 douyin-sign（a_bogus）验证——**最终实测：无签名、无 msToken、仅带登录 Cookie，8/8 全成功**（满 55KB 数据）。空 body 是**抖音概率性/临时风控**（短期连续请求触发），不是签名缺失。结论：**带登录 Cookie 即够用，不上签名依赖**（如需绕过可用 douyin-sign 的 a_bogus，可选非必需）。
- **空 body 风控要「停手」而不是「重试」**（2026-08-25 晚实测更正）：原先记的「隔几分钟重试即可」**不准确**。当晚为做对照实验密集打了十几次 `detail`，随后连续失败：等 4 分钟、8 分钟、15 分钟重试均为 `status=200 body=0`，累计 27 分钟不恢复；**停掉后台轮询、彻底不发请求之后，下一次请求立刻拿到完整 67916 字节**。判断：每次重试都在重置风控窗口，越试越不通。正确处置是**停止所有请求静置**，别开轮询。诊断时先看**响应头**（`X-Tt-Logid` / `Cookie_ttwidinfo_webid` 等都在，说明链路正常、纯属限流），只看 status/body 长度会误判。
- **图集水印**：`download_url_list` 是带「抖音号：xxx」水印的高清版（模板含 `~tplv-dy-water-v2:`），`url_list` 是无水印版（`~tplv-dy-aweme-images:q75`，分辨率不变、体积几乎相同）。默认下无水印版。
- **实况图动图水印**（2026-08-19 实测）：内嵌视频的 `download_addr.url_list[0]` **不保证是 `watermark=0`**，服务端可能把 `watermark=1` 档排在 `[0]`（同一 video_id 下 `watermark=0` → 干净 294KB，`watermark=1` → 带水印 503KB，实测参数交换有效）。下载前必须 `.replace("watermark=1", "watermark=0")` 归一，不能直接取 `url_list[0]`。
- **实况图判据**：`douyin.py` 图集分支只对 `images[i].live_photo_type==1` / `clip_type==5`（实况图）下内嵌动图 mp4；**不能只看 `video.url_list` 非空**——普通图集作品的 `video.play_addr` 是背景音乐 mp3（非视频），否则会误下 BGM。
- **小红书 `__INITIAL_STATE__` 是 JS 赋值的 JSON**，混有 `undefined` / `new Map([])` 等字面量，必须先 `clean_js()` 清洗再 `json.loads`。被风控时页面是 404/sec 页，特征是 900KB 左右、`sec_` 出现在跳转 URL 里。
- **快手 `__APOLLO_STATE__` 有 IIFE 尾巴**，必须替换掉才能 `json.loads`。
- Cookie 过期（几周）：重新打开对应站点点扩展导出，覆盖对应 cookies.txt。
- 私密/已删除/强制登录的作品解析不到。
- **下载原子化**（2026-08-25；2026-08-28 三份拷贝合并为 douyin.py 的通用 `download()`，xhs/kuaishou 删本地版改复用，返回统一为 `(bool, Content-Type)`）：写临时文件 `<dest>.part` 成功后 `os.replace` 原子改名，中断不留半截成品（旧版直写最终名，中断留半截 mp4 且 `getsize==0` 拦不住）。
- **已存在跳过**：目标文件已存在且非空则跳过（重复链接不重下）。只对**视频**（下到最终名）真正生效；图片走 `.tmp` 中转、`dest` 是临时文件，跳过判断天然不触发（图片重下会覆盖，代价低）。`twitter.py` 用 yt-dlp `nooverwrites` 本就是同行为。
- **Instagram 必须走代理**：IG CDN 在海外，直连会连接超时 / 429 风控；`--proxy` 或本机开「系统代理」自动读。
- **X 用户主页批量不支持**：yt-dlp 无主页提取器，只能 `/status/ID` 单条；`is_profile` 检测到主页会明确提示。
- **Instagram 图集作者名含点**（如 `xx.uyvn`）：不要用 `Path.with_suffix` 命名，会互相覆盖，用字符串拼接（已处理）。
- **域名判断禁用子串包含**（2026-08-25，CodeQL 告警 `xhs.py:214`）：`"xhslink.com" in url` 会被 `https://evil.com/?x=xhslink.com` 骗过。三个 `extract_url` 的**兜底分支**会返回文本里任意第一个 URL，配上子串判断就等于把登录 Cookie（douyin 是 session 级 `headers["Cookie"]`，xhs/kuaishou 是显式 Cookie 头）发给攻击者的 host——粘一条群里的伪装链接即可触发。现统一走 `douyin.host_allowed(url, HOSTS)`（`urlsplit().hostname` 精确匹配 + 子域），各脚本 `HOSTS` 常量取自各自 `URL_RE` 覆盖的域名。**兜底保留**（仍放行同域的未覆盖路径变体），只挡站外域名。
- **短链跳转一律不传 Cookie**（2026-08-25，配合上一条）：跳转**真的跨 host**（实测 `v.douyin.com → iesdouyin.com → www.douyin.com`），而 Cookie **头**不按域隔离，跟着跳到哪发到哪（cookie jar 按域隔离，不用管）。三处跳转均改为匿名：`xhs.py` / `kuaishou.py` 的 `get(url, "")`、`douyin.py` 的 `headers={"Cookie": None}`（per-request 设 None 才能摘掉 `s.headers["Cookie"]`，只传 UA 是**合并**不是替换）。实测依据：快手 3 条短链带/不带 Cookie 拿到的 photoId 全一致；**小红书 `xsec_token` 不依赖登录态**——它是短链自带的时效凭证，匿名跳转照样拿得到（这点原先没底，实测推翻了顾虑）。
- **requests 的 header Cookie 与 cookie jar 是两条独立路径**：jar 非空时**不会**覆盖 `session.headers["Cookie"]`（实测灌入假 ttwid，实际发出的仍是完整 8616 字节登录 Cookie，假值没混进去）。所以匿名跳转导致 jar 少一个 `ttwid` 无影响。排查时别把两者混为一谈。
- 别二次传播无水印作品，仅个人归档。

## 测试
- `douyin.py` 已用真实链接实测通过：图集（13/13 原图）、实况图动图（4/4 mp4）、视频（无水印 mp4）。
- `kuaishou.py` 已实测通过（2026-08-15）：真实作品页链接（`short-video/3x7edaa985qmhqy`），匿名与带 Cookie 均成功。**水印排查结论（用户目检确认）**：H264（4.89MB）与 H265（2.93MB）都**没有**水印；曾误判 H264 带水印（实为小红书视频）。已改为按（分辨率,码率）选最佳画质（优先 H264 高码率）。App 接口需签名（`result:50`），未实现。
- `xhs.py` 已实测通过（2026-08-15，带登录 Cookie）：图文笔记 3/3 原图（走 `fileId` → `sns-img-bd.xhscdn.com`）、视频笔记 mp4（`media.stream.EF4` 最高清）。**视频水印（最终结论）**：网页流（sns-video-v2）带「小红书号」水印；**网页端数据层已彻底不暴露干净源**——8/8 视频笔记的 SSR `video` 只有 `media/mediaV2/image/capa`，无 `consumer.originVideoKey`；真浏览器（playwright + `_webmsxyw` 签名 + 注入 Cookie）调 feed API 能过风控（code 0）但数据空/minimal，也拿不到 originVideoKey（风控还会在 code 0 / code -101 间横跳）。**结论：小红书视频水印在网页接口下无解**（数据层封死，非签名问题），保持页面解析 + 水印提示。实况图（Live Photo）代码已支持（`imageList[].stream.EF4` masterUrl），已实测通过（3 图+3 mp4）。裸 `explore/{id}` 无 xsec 会被风控，需分享链接（带 xsec_token）或恰好出现在首页 feed。playwright 曾用于探索小红书签名（2026-08-15），已卸载，不打包。
- `instagram.py` / `twitter.py`：**URL 识别单测**（`tests/test_urls.py`，免联网纯 assert）已通过（IG 7 组 / X 9 组）。真实媒体下载**未在本机实测**（需真 cookie + 代理 + 海外网络），代码逻辑按 IG 私有 API / yt-dlp 封装，等链接实测后再补结论。
- **单测跑法**：`.venv/Scripts/python.exe tests/test_urls.py`（无 pytest 依赖，纯 assert）。已覆盖 IG/X/抖音/小红书/快手的 `extract_url` 与 `host_allowed`，含站外域名冒充样本（期望 `None`/`False`），共 35 条。
- **2026-08-25 域名白名单 + 匿名跳转实测**：白名单三平台端到端全过（抖音图集 13/13、小红书视频、快手视频，`.part`/`.tmp` 零残留）。匿名跳转三平台端到端全过：**快手** `v.kuaishou.com/bg4URK`、**小红书** `xhslink.com/m/...`（4/4）、**抖音** `v.douyin.com/j5POryBzxME`（13 jpg + 1 实况 mp4，与既有记录一致），`.part`/`.tmp` 零残留。过程中抖音一度风控空 body，用对照组排除了代码原因（**完全不跳转直接打 detail 同样空 body**），静置后恢复即通过。
- **2026-08-25 三条修复（原子下载 + 已存在跳过 + 实况图判据）**：
  - `test_urls.py` 无回归（URL 逻辑未动）；三脚本 `py_compile` 通过。
  - **kuaishou / xhs 已实车验证**：下载成功、`.part` 零残留、重跑 0.6s 跳过且 mtime/size 不变（重复链接不重下）。
  - **douyin 实况图判据 2026-08-25 实车复测通过**（三条真实链接，接口无签名）：
    - 头顶长草（13 张）：13 jpg + **1 个真实况 mp4**（`12.mp4`，349KB，`ftypisom` 视频头）——逐张判对，仅真实况下 mp4。
    - 泳衣 ootd（4 张）：4 jpg + **4 个 mp4**（281K~395K，全 `ftypisom`）——**4 张全真实况图**，逐一判对。
    - 古早蓝裙（9 张）：**9 jpg + 0 mp4**——**普通图集不误下背景音乐**，判据正确。
    - 全程 `.part`/`.tmp` **零残留**。判据：`is_live` 用 `live_photo_type==1`/`clip_type==5` 权威字段。
- 打包：本地 PyInstaller 实测通过（55.8MB，curl_cffi 已进包）。

## 跨助手同步（Claude Code ↔ ZCode）
- 修改本文件里的规则/约定时，必须同步更新对方工具的对应文件：ZCode 项目级 `AGENTS.md`（若不存在则提醒用户是否共建，别静默只改一边）——两端是一份内容的两个载体，只改一边必分叉。
