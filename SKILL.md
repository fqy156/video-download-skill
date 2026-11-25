---
name: video-download
description: 从各平台下载视频到本地的实战技能。覆盖四条已验证的技术路线：X/Twitter（yt-dlp + 代理 + cookies）、YouTube（yt-dlp + 代理 + 编解码选择）、抖音（Chrome CDP 抓取）、网易新闻/163（详情 API + TS 分片合并），并提供跨平台的工具自动补齐脚本。当用户要求"下载视频/保存视频/把某个链接的视频存到本地"，链接来自 X、YouTube、抖音、网易新闻或类似平台时使用此技能。
agent_created: true
---

# Video Download

## Overview

沉淀四条**实测跑通**的视频下载路线（X/Twitter、YouTube、抖音、网易新闻），外加可移植的环境准备与踩坑记录。核心流程：判断平台 → 选路线 → 下载 → 验证产物。

本技能不依赖任何特定 Agent 运行时或本机绝对路径：工具通过 `scripts/ensure_tools.py` 自动定位或补齐，支持 Windows / macOS / Linux 的 x64 与 arm64。

## 平台路由

根据视频链接的域名选择路线，详细步骤见 `references/platforms.md`：

| 链接特征 | 路线 | 难度 |
|---|---|---|
| `x.com` / `twitter.com` | 路线 A：yt-dlp + 代理 + cookies | 低 |
| `youtube.com` / `youtu.be` | 路线 D：yt-dlp + 代理 | 低 |
| `v.douyin.com` / `douyin.com` | 路线 B：Chrome CDP 抓取 | 高 |
| `c.m.163.com` / `163.com` / 网易新闻页 | 路线 C：详情 API + TS 分片合并 | 中 |
| 其他平台 | 先按通用排查顺序尝试（见下），失败后用路线 B 的 CDP 思路兜底 | - |

## 环境准备（共用）

**第一步先跑工具定位脚本**，不要手写下载命令、不要猜路径：

```bash
python scripts/ensure_tools.py            # 定位 ffmpeg / ffprobe，输出 JSON
python scripts/ensure_tools.py --ytdlp    # 额外确保 yt-dlp 为最新版
```

脚本按三级顺序查找，命中即返回，**不会重复下载**：

1. 系统 `PATH` 中的 `ffmpeg` / `ffprobe`（尊重用户已装环境，Linux/macOS 常见）
2. 用户级缓存目录（Windows `%LOCALAPPDATA%\video-download\bin`、macOS `~/Library/Caches/video-download/bin`、Linux `~/.cache/video-download/bin`；可用 `VIDEO_DOWNLOAD_TOOLS_DIR` 覆盖）
3. 前两级都没有 → `pip install imageio-ffmpeg`（PyPI 提供各平台预编译静态 ffmpeg），解出的可执行文件复制进缓存

缓存放在用户目录而不是技能目录，保证技能仓库/发布包始终轻量。

要点：

- **ffmpeg / ffprobe**：静态、稳定、体积大，定位一次进缓存复用。若环境里没有 `ffprobe`，脚本返回 `probe_hint`，改用 `ffmpeg -i <file>` 从 stderr 解析时长/分辨率。
- **yt-dlp**：**每次用最新版**，不缓存不打包。平台反爬持续变化，旧版会直接失效。脚本通过 `python -m yt_dlp` 调用；国内网络可设 `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/` 加速。
- **cookies.txt**：账号凭据，不随技能分发，由使用者自行导出（Netscape 格式）。
- **代理**：境外站点（X）通常需要代理，通过 `HTTPS_PROXY` / `--proxy` 传入，不要把地址写死在命令里。
- **验证产物**：`ffprobe` 检查时长、分辨率、音轨是否存在；不可用时用 `ffmpeg -i`。

## 工具打包策略（为什么不全打包）

| 工具 | 策略 | 理由 |
|---|---|---|
| ffmpeg / ffprobe | 首次运行自动获取并缓存 | 稳定、体积大、下载耗时；缓存后跨会话复用 |
| yt-dlp | 每次装最新版 | 周级更新，打包旧版等于自带 bug |
| cookies.txt | 使用者自备 | 凭据，不可共享 |
| 浏览器（CDP 路线） | 用系统已装 Chrome/Chromium | 无需分发，几十上百 MB |

## 通用排查顺序（未知平台）

1. `yt-dlp` 直接下载（国内站不加代理）。
2. 抓页面 HTML，找 m3u8 / mp4 直链。
3. 找平台的视频详情 API（参考路线 C：从详情页 URL 提取视频 ID → 调 API 拿真实地址，注意 Referer 与移动端 UA）。
4. 仍失败 → 走路线 B 的 CDP 方案抓媒体请求。

## 通用注意事项（踩坑记录）

- 若执行环境在命令结束时会回收后台进程，**起浏览器 + 抓取 + 下载要放在同一次命令里**完成，不要分步。
- Chrome 运行期间 Cookies 数据库被独占锁定，`--cookies-from-browser chrome` 常失败；让使用者手动导出 cookies.txt 更可靠。
- 清理中间文件优先「移动到临时子目录」，避免在受限环境里删除被拒；产出目录保持干净。
- 画质优先：同一视频多档位时选清晰度最高且**含音轨**的版本（如抖音 `play_addr` 的整段 MP4 优于播放器实际串流的 DASH 分片）。
- 大文件下载走国内镜像（清华 `pypi.tuna.tsinghua.edu.cn` / 阿里 `mirrors.aliyun.com`）可显著提速；直连 pythonhosted 可能被限速或中断。

## Resources

- `scripts/ensure_tools.py` — 跨平台工具定位/补齐，输出 ffmpeg、ffprobe 路径与 yt-dlp 版本。
- `scripts/douyin_cdp.mjs` — 抖音详情抓取（CDP 拦截 detail 接口，输出各清晰度直链）。
- `references/platforms.md` — 四条路线的完整命令、分步操作与平台特定的坑。
