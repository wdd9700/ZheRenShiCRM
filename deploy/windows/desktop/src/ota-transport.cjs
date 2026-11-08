'use strict';
const https = require('node:https');
const fs = require('node:fs');
const { Transform } = require('node:stream');
const { pipeline } = require('node:stream/promises');
function trustedUrl(value, policy) {
  try {
    const url = new URL(value); const base = new URL(policy.feedUrl);
    return url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash && url.origin === base.origin && url.pathname.startsWith(base.pathname) && !url.pathname.includes('%') && !url.pathname.includes('\\');
  } catch { return false; }
}
function responseFor(url, policy, maxBytes, requester = https.get) {
  if (!trustedUrl(url, policy)) return Promise.reject(new Error('OTA URL 不在固定 HTTPS 发布目录'));
  return new Promise((resolve, reject) => {
    let settled = false;
    let deadline;
    const request = requester(url, { agent: false, rejectUnauthorized: true, headers: { 'Accept-Encoding': 'identity', 'User-Agent': 'PhilosopherStoneCRM-OTA/1' }, timeout: 15000 }, response => {
      response.once('close', () => clearTimeout(deadline));
      if (response.statusCode !== 200 || (response.headers['content-encoding'] && response.headers['content-encoding'] !== 'identity')) { response.destroy(); reject(new Error('OTA 非200/压缩响应或重定向被拒绝')); return; }
      const length = response.headers['content-length'];
      if (length !== undefined && (!/^\d+$/.test(length) || Number(length) > maxBytes)) { response.destroy(); reject(new Error('OTA 响应大小超限')); return; }
      settled = true; resolve(response);
    });
    deadline = setTimeout(() => request.destroy(new Error('OTA 请求总时限超出')), 300000);
    request.once('timeout', () => request.destroy(new Error('OTA 网络空闲超时')));
    request.once('error', error => { clearTimeout(deadline); if (!settled) reject(error); });
  });
}
function limiter(maxBytes) {
  let count = 0;
  return new Transform({ transform(chunk, _encoding, callback) { count += chunk.length; callback(count > maxBytes ? new Error('OTA 流内容超限') : null, chunk); } });
}
async function fetchBytes(url, policy, maxBytes) {
  const response = await responseFor(url, policy, maxBytes);
  const chunks = []; let count = 0;
  for await (const chunk of response) { count += chunk.length; if (count > maxBytes) { response.destroy(); throw new Error('OTA 清单内容超限'); } chunks.push(chunk); }
  return Buffer.concat(chunks);
}
async function downloadFile(url, policy, target, size) {
  const response = await responseFor(url, policy, size);
  const length = response.headers['content-length'];
  if (length !== undefined && Number(length) !== size) { response.destroy(); throw new Error('OTA Content-Length 不符'); }
  await pipeline(response, limiter(size), fs.createWriteStream(target, { flags: 'wx', mode: 0o600 }));
  if (fs.statSync(target).size !== size) throw new Error('OTA 下载不完整');
}
module.exports = { trustedUrl, responseFor, limiter, fetchBytes, downloadFile };
