# 平台路线详解

四条路线均在 Windows 上实测跑通（2026 年 9–11 月），命令按**跨平台**写法给出；macOS / Linux 的差异在各条目的注释中说明。命令中的 `<FFMPEG>` / `<FFPROBE>` 指路线 0 输出的实际路径。

## 路线 0：准备工具（所有路线通用）

```bash
python scripts/ensure_tools.py            # 输出 ffmpeg / ffprobe 路径与来源
python scripts/ensure_tools.py --ytdlp    # 需要 yt-dlp 时再跑一次
```

拿到 JSON 里的 `ffmpeg` / `ffprobe` 字段值替换下文占位符。**不要重复下载工具**：脚本会命中 `PATH` 或用户级缓存目录（Windows `%LOCALAPPDATA%\video-download\bin`、macOS `~/Library/Caches/video-download/bin`、Linux `~/.cache/video-download/bin`）。国内网络可设 `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/` 加速 pip 环节。

## 路线 A：X / Twitter（yt-dlp）

**案例**：下载一条年龄限制推文的视频（3 分 08 秒，350MB）。

1. 准备工具：`python scripts/ensure_tools.py --ytdlp`
2. 年龄限制/登录墙：需要使用者提供 `cookies.txt`（Netscape 格式，用浏览器扩展从 x.com 导出）。
3. 下载（境外站点需代理，通过环境变量或 `--proxy` 传入，不要写死地址）：
   ```bash
   <YTDLP> --proxy "$HTTPS_PROXY" --cookies cookies.txt \
     -f "bv*+ba/b" --merge-output-format mp4 \
     --ffmpeg-location "<FFMPEG>" \
     -o "%(title)s.%(ext)s" "https://x.com/<user>/status/<tweet_id>"
   ```
   其中 `<YTDLP>` 为 `python -m yt_dlp`（脚本输出的 `launcher` 字段）。
4. yt-dlp 自动调用 ffmpeg 合并音视频流；完成后用 `<FFPROBE>` 验证时长/分辨率/音轨。

**坑**：
- 无代理时请求超时；cookies 缺失时年龄限制推文报 `Age-restricted`。
- **格式标签码率可能虚标（实测案例）**：X 的渐进式 MP4 格式名（如 `http-2176`）按元数据估算体积（42MB），实际 CDN 交付可能只有 ~15MB（约 740kbps）。真实画质以**下载后 ffprobe/ffmpeg 实测码率**为准，别信格式 ID 里的数字；源分辨率以上限为准，多档位往往只是码率差异。
- 优先渐进式格式（`-f b`，`http-*` 协议）：自带音轨、单文件免合并；HLS（`hls-*`）通常只有视频轨，需另配音轨合并。
- 推文含多段视频（分 P）时用 `--playlist-items` 选择，或直接去掉合并参数逐段下载。

## 路线 D：YouTube（yt-dlp）

**案例**：下载 Shorts 视频 `https://www.youtube.com/shorts/SFflxkXzTZQ`，产出 1080×1920 竖屏 MP4（1:27，38MB，25 秒内完成）。

1. 准备工具：`python scripts/ensure_tools.py --ytdlp`，并把输出的 `ffmpeg` 路径传给 `--ffmpeg-location`（ffmpeg 不在 PATH 时 yt-dlp 无法自动合并音视频）。
2. 下载（境外站点必须走代理）：
   ```bash
   <YTDLP> --proxy "$HTTPS_PROXY" \
     --ffmpeg-location "<FFMPEG>" \
     -f "bv*+ba/b" --merge-output-format mp4 \
     -o "%(title)s [%(id)s].%(ext)s" --no-playlist \
     "https://www.youtube.com/shorts/<video_id>"
   ```
   yt-dlp 自动下载最佳视频流 + 最佳音轨（如 mp4 + webm/opus），并调用 ffmpeg 合并成 mp4。
3. 用 `<FFPROBE>`（或 `ffmpeg -i`）验证时长、分辨率、音轨。

**坑与技巧**：
- **JS runtime 警告**：新版 yt-dlp 默认只启用 `deno` 作为 JS 运行时，没有它会有 "No supported JavaScript runtime" 警告，部分格式可能缺失（Shorts 实测仍可正常提取）。机器上有 Node 时可加 `--js-runtimes node` 消除警告、拿到更全的格式列表。
- **编解码兼容性（真实案例）**：`bv*+ba` 常选中 **AV1 10-bit HDR（bt2020/HLG）视频 + Opus 音轨**（如 format 699+251）。电脑本地播放没问题，但**上传微信后在手机上只有声音、没有图像**（手机解码器普遍没有 AV1 硬解，且 Opus-in-MP4 支持差）。需要分享/转发场景时锁定 H.264+AAC：
  ```bash
  -f "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[acodec^=mp4a]"
  # 或按 H.264 优先排序（分辨率优先）
  -S "res,ext:mp4:codec:h264"
  ```
  判定标准：`ffmpeg -i` 看到 `h264 ... yuv420p(tv, bt709)` + `aac` 即为全兼容版本；`av1 ... bt2020` / `opus` 即为仅本机可播版本。下载前先问用途：本地收藏用 AV1（画质最高），要转发就锁 H.264。
- Shorts 的短链 `youtu.be/<id>` 与 `/shorts/<id>` 都可直接用；带 `?si=...` 等跟踪参数不影响提取。
- `--no-playlist` 防止分享链接展开成整张歌单/合集。
- 公开视频不需要 cookies；年龄限制视频同路线 A，需用户提供 cookies.txt。
- 直播/ premiere 中的视频会报错，等结束再下。

## 路线 B：抖音（Chrome CDP 抓取）

**案例**：下载分享链接 `https://v.douyin.com/xxxx/` 对应视频，按 `bit_rate` 选档可拿到最高 1080p H.264+AAC 整段 MP4。

**背景**：抖音反爬严，以下常规手段**全部失效**——yt-dlp 报 `Fresh cookies are needed`；分享页 SSR 不内嵌视频地址；`aweme/v1/web/aweme/detail` 接口需要 `a_bogus` 签名。

**可行方案：系统 Chrome 起调试实例 + CDP 抓包**：

1. 启动调试实例（独立 profile，避免污染用户浏览器数据）：
   ```bash
   # Windows
   "C:/Program Files/Google/Chrome/Application/chrome.exe" --remote-debugging-port=9222 \
     --user-data-dir="<tmp>/cdpprofile" --headless=new "<真实视频URL>"
   # macOS: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
   # Linux: google-chrome 或 chromium
   ```
   **注意**：若执行环境在命令结束时会回收后台进程，启动浏览器、抓包、下载必须放在**同一次**命令调用内完成。
2. 抓详情：用技能自带脚本 `scripts/douyin_cdp.mjs`（零依赖，Node 18+ 即可），与浏览器启动放在**同一条命令**里：
   ```bash
   chrome --headless=new --remote-debugging-port=9222 \
     --user-data-dir="<tmp>/cdpprofile" --mute-audio about:blank &
   sleep 5
   node scripts/douyin_cdp.mjs <video_id> > detail.json
   taskkill //F //IM chrome.exe //T   # Linux/macOS: pkill -f remote-debugging-port
   ```
   脚本内部完成：CDP 连接 → `Network.enable` → 打开 `douyin.com/video/<id>` → 拦截 `aweme/v1/web/aweme/detail` 响应体 → 输出 `desc/author/duration_ms/candidates`。原理是让真实浏览器执行页面 JS（带 `a_bogus` 签名）再取回响应，比逆向签名可靠。
3. **关键**：detail JSON 中 `video.play_addr` / `play_addr_h264` 是**已含音轨的整段 MP4**（H.264+AAC），比播放器实际串流的 DASH 分片（仅视频轨、且为最低档）质量高得多。`video.bit_rate[]` 里还有完整档位表（`normal_1080_0` / `1080_1_1` / `720_x` 等）：**按 `bit_rate` 取最大值**那一档的 `play_addr.url_list[0]` 下载，即为该视频最高画质。无需 ffmpeg 合并。
   下载时带 `-A "<桌面 Chrome UA>" -e "https://www.douyin.com/"`，否则 403。
4. 产出存放在工作目录 `downloads/`，命名用视频标题（`desc` 首行或前 20 字，音乐类内容用「歌手 - 歌名.mp4」）。

**坑**：
- Chrome 运行期间 Cookies 数据库被独占锁定，`--cookies-from-browser chrome` 会失败。
- 中间文件（profile、抓包日志）放 `_tmp_douyin/` 之类独立子目录，交付时只保留成品。
- 参考环境：yt-dlp 最新版、ffmpeg 7.1.x、Node 18+、Chrome 120+。

## 路线 C：网易新闻 / 163（详情 API + TS 分片）

**案例**：下载 `https://c.m.163.com/news/v/<vid>.html` 的视频，产出 720p MP4（6:18，31MB）。

1. 抓页面 HTML，提取视频 ID（URL 末段，如 `VG7BJ095T`）与 m3u8 线索。
2. 调视频详情 API 拿真实地址：
   ```
   GET https://c.m.163.com/nc/video/detail/{vid}.html
   Headers:
     Referer: https://c.m.163.com/
     User-Agent: (iPhone UA)
   ```
   响应含 `mp4_url`、`m3u8`、时长、标题。
3. 若只有 TS 分片（形如 `/videolib1/.../SD/xxx-mobile-N.ts`）：先探测更高级别档位（HD/SHD），404 则用 SD（实际仍可能是 1280×720）；带 Referer 逐个下载分片。
4. 合并 TS 后无损转封装：
   ```bash
   <FFMPEG> -i merged.ts -c copy -bsf:a aac_adtstoasc -movflags +faststart out.mp4
   ```
5. `<FFPROBE>` 验证无解码错误后交付，文件名用视频实际标题。

**坑**：
- 分片下载必须带 Referer，否则 403。
- `mp4_url` 优先于 m3u8：能直接拿到整段 MP4 时跳过第 3、4 步。

## 交付规范

- 下载完成后报告：文件路径、大小、时长、分辨率、编码（来自 ffprobe 或 `ffmpeg -i`）。
- 产物默认放任务工作目录（如 `downloads/`）；使用者指定目录时从其指定。
- 不要把 cookies、抓包原始数据、浏览器 profile 混入交付目录。
