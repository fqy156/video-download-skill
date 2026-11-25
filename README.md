# video-download

A **video-download skill** for AI agents: given a video URL, it picks the right download route by domain and saves the video locally — with battle-tested workarounds for each platform's anti-scraping.

Works on Windows / macOS / Linux (x64 & arm64). Not tied to any specific agent runtime or machine path.
The skill content (`SKILL.md`, `references/`) is written in Chinese — any LLM-based agent (WorkBuddy, Claude Code, etc.) can follow it regardless of the user's language.

> 中文说明见下方 [中文速览](#中文速览)。

## Supported platforms

| Platform | Approach | Notes |
|---|---|---|
| X / Twitter | yt-dlp + proxy + cookies | Age-restricted tweets supported (bring your own cookies) |
| YouTube | yt-dlp + proxy | Shorts & regular videos; optional H.264+AAC compatibility mode |
| Douyin (抖音) | Chrome CDP capture | Bypasses anti-scraping; up to 1080p progressive MP4 with audio |
| NetEase News (网易新闻) | detail API + TS segments | Lossless remux, multi-quality probing |

Other platforms follow a generic fallback ladder: yt-dlp → page HTML direct link → detail API → CDP capture.

## Install

Copy the whole folder into your agent's skill directory, e.g.:

- WorkBuddy: `~/.workbuddy/skills/video-download/`
- Claude Code: `~/.claude/skills/video-download/`

```bash
git clone <repo-url> <your-skills-dir>/video-download
```

## Usage

Tell your agent to download a video by URL — the agent reads `SKILL.md`, routes by domain, and executes. First run prepares the tools:

```bash
python scripts/ensure_tools.py            # locate/provision ffmpeg & ffprobe
python scripts/ensure_tools.py --ytdlp    # additionally ensure latest yt-dlp
```

Example output:

```json
{
  "platform": "win32",
  "ffmpeg": "C:/Users/you/AppData/Local/video-download/bin/ffmpeg.exe",
  "ffmpeg_source": "cache",
  "ffprobe": null,
  "ffprobe_source": "missing",
  "probe_hint": "no ffprobe; use `ffmpeg -i <file>` instead"
}
```

For Douyin, `scripts/douyin_cdp.mjs` captures the video detail API via Chrome DevTools Protocol (zero dependencies, Node 18+):

```bash
chrome --headless=new --remote-debugging-port=9222 \
  --user-data-dir="<tmp>/cdpprofile" --mute-audio about:blank &
sleep 5
node scripts/douyin_cdp.mjs <video_id> > detail.json
```

## Tool policy

| Tool | Policy | Why |
|---|---|---|
| ffmpeg / ffprobe | `PATH` → user cache dir → `pip install imageio-ffmpeg` | Stable, large, slow to download; fetch once, reuse forever |
| yt-dlp | install latest on every use | Anti-scraping changes weekly; a bundled old version ships bugs |
| cookies.txt | user-provided | Credentials, never distributed |
| Browser (CDP route) | system-installed Chrome/Chromium | No need to ship 100+ MB |

Cache lives in the user's cache directory (Windows `%LOCALAPPDATA%\video-download\bin`, macOS `~/Library/Caches/video-download/bin`, Linux `~/.cache/video-download/bin`; override with `VIDEO_DOWNLOAD_TOOLS_DIR`), so the repo stays lightweight.

## Repository layout

```
video-download/
├── SKILL.md               # skill entry: platform routing + env prep + pitfalls (Chinese)
├── references/
│   └── platforms.md       # full commands & platform-specific pitfalls per route
├── scripts/
│   ├── ensure_tools.py    # cross-platform tool locator/provisioner
│   └── douyin_cdp.mjs     # Douyin detail-API capture via CDP (zero deps)
└── .gitignore
```

## Notes

- Respect the target platform's terms of service and copyright; personal fair use only.
- In mainland China, set `PIP_INDEX_URL` (e.g. Aliyun/Tsinghua mirrors) for faster pip downloads; use `HTTPS_PROXY` for X/YouTube.

## 中文速览

给 AI Agent 用的视频下载技能：给出链接，按域名自动选路线下载到本地。覆盖 X / YouTube / 抖音 / 网易新闻四条实测路线，其他平台有通用兜底流程。工具（ffmpeg/yt-dlp）由脚本自动定位或补齐，缓存放在用户目录，仓库保持轻量。安装即把目录放进 Agent 的技能目录；使用时直接发链接即可。详细路线见 `references/platforms.md`。

## License

MIT — see [LICENSE](LICENSE).
