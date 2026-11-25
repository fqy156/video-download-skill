/**
 * 抖音视频详情抓取（Chrome CDP，零依赖，Node 18+ 自带 fetch/WebSocket）
 *
 * 用法：
 *   1. 先起带调试端口的 Chrome（独立 profile，别用用户日常 profile）：
 *      chrome --headless=new --remote-debugging-port=9222 \
 *        --user-data-dir=<tmp>/cdpprofile --mute-audio
 *   2. 运行本脚本（与启动浏览器放在同一条命令里，避免后台进程被回收）：
 *      node scripts/douyin_cdp.mjs <video_id>
 *   3. 输出 JSON：desc / author / duration_ms / candidates（含各档位 bit_rate 与直链）
 *      选 bitRate 最大的一档下载即可（通常 normal_1080_0），下载时带 UA + Referer。
 *
 * 说明：抖音短视频的 aweme/detail 接口需要 a_bogus 签名，无法直接调；
 * 本脚本让真实浏览器执行页面 JS，再从 CDP 网络层取回接口响应体。
 */
import { setTimeout as sleep } from "node:timers/promises";

const PORT = process.env.CDP_PORT || 9222;
const VIDEO_ID = process.argv[2];
const TARGET_URL = `https://www.douyin.com/video/${VIDEO_ID}`;

async function getPageTarget() {
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const list = await r.json();
      const page = list.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch {}
    await sleep(250);
  }
  throw new Error("CDP 端口未就绪");
}

const page = await getPageTarget();
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => {
  ws.onopen = res;
  ws.onerror = (e) => rej(new Error("ws error"));
});

let msgId = 0;
const pending = new Map();
const handlers = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m);
    pending.delete(m.id);
  } else if (m.method) {
    handlers.forEach((h) => h(m));
  }
};
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const id = ++msgId;
    pending.set(id, (m) => (m.error ? rej(new Error(method + ": " + m.error.message)) : res(m.result)));
    ws.send(JSON.stringify({ id, method, params }));
  });

const detailResponses = new Map();
const mediaUrls = new Set();

handlers.push(async (m) => {
  if (m.method === "Network.responseReceived") {
    const { requestId, response } = m.params;
    if (response.url.includes("aweme/v1/web/aweme/detail")) {
      detailResponses.set(requestId, response.url);
    }
    if (/douyinvod\.com|\.mp4/.test(response.url) && response.mimeType?.includes("video")) {
      mediaUrls.add(response.url);
    }
  }
  if (m.method === "Network.loadingFinished" && detailResponses.has(m.params.requestId)) {
    try {
      const body = await send("Network.getResponseBody", { requestId: m.params.requestId });
      const text = body.base64Encoded
        ? Buffer.from(body.body, "base64").toString("utf8")
        : body.body;
      await done(text);
    } catch (e) {
      await done(null, String(e));
    }
  }
});

let finished = false;
let resolveDone;
const donePromise = new Promise((r) => (resolveDone = r));
async function done(text, err) {
  if (finished) return;
  finished = true;
  resolveDone({ text, err });
}
setTimeout(() => done(null, "timeout"), 45000);

await send("Network.enable", { maxTotalBufferSize: 100 * 1024 * 1024 });
await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false,
});
await send("Page.navigate", { url: TARGET_URL });

const { text, err } = await donePromise;

if (!text) {
  console.log(JSON.stringify({ ok: false, err, mediaUrls: [...mediaUrls] }, null, 2));
  process.exit(0);
}

let data;
try {
  data = JSON.parse(text);
} catch {
  console.log(JSON.stringify({ ok: false, err: "detail JSON 解析失败", head: text.slice(0, 300) }));
  process.exit(0);
}

const aweme = data?.aweme_detail;
if (!aweme) {
  console.log(JSON.stringify({ ok: false, err: "无 aweme_detail", keys: Object.keys(data || {}) }));
  process.exit(0);
}

const video = aweme.video || {};
const brList = (video.bit_rate || []).map((b) => ({
  gear: b.gear_name,
  quality: b.quality_type,
  bit_rate: b.bit_rate,
  urls: b.play_addr?.url_list || [],
}));
const cands = [];
if (video.play_addr?.url_list?.length) {
  cands.push({ source: "play_addr", urls: video.play_addr.url_list });
}
if (video.play_addr_h264?.url_list?.length) {
  cands.push({ source: "play_addr_h264", urls: video.play_addr_h264.url_list });
}
for (const b of brList) if (b.urls.length) cands.push({ source: b.gear, bitRate: b.bit_rate, urls: b.urls });

console.log(
  JSON.stringify(
    {
      ok: true,
      desc: aweme.desc,
      author: aweme.author?.nickname,
      duration_ms: video.duration,
      ratio: video.ratio,
      candidates: cands,
      bit_rates: brList.map(({ urls, ...rest }) => rest),
    },
    null,
    2
  )
);
ws.close();
process.exit(0);
