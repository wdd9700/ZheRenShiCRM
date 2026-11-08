'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { createHash } = require('node:crypto');
const { windowsTool } = require('./tunnel.cjs');
function validatePolicy(raw) {
  if (!raw || raw.enabled !== true) return null;
  const url = new URL(raw.feedUrl);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || !url.pathname.endsWith('/')) throw new Error('OTA 必须使用固定 HTTPS 发布目录');
  if (typeof raw.publisherName !== 'string' || !raw.publisherName.trim() || raw.publisherName.length > 512) throw new Error('OTA 缺少完整发布者 Subject');
  if (!Array.isArray(raw.certificateSha256) || raw.certificateSha256.length === 0 || !raw.certificateSha256.every(value => /^[a-fA-F0-9]{64}$/.test(value))) throw new Error('OTA 缺少证书 SHA256 pin');
  return { feedUrl: url.href, origin: url.origin, publisherName: raw.publisherName, certificateSha256: raw.certificateSha256.map(value => value.toUpperCase()) };
}
async function fileHash(file, algorithm = 'sha512') {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || !path.isAbsolute(file) || path.extname(file).toLowerCase() !== '.exe') throw new Error('安装器路径无效');
  const hash = createHash(algorithm);
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest('base64');
}
function parseSignature(stdout, stderr, file, policy) {
  if (stderr?.trim()) throw new Error('验签进程输出错误，拒绝更新');
  const result = JSON.parse(stdout.replace(/^\uFEFF/, '').trim());
  if (!result || result.Status !== 'Valid' || typeof result.Path !== 'string' || path.win32.resolve(result.Path).toLowerCase() !== path.win32.resolve(file).toLowerCase() || result.Subject !== policy.publisherName || !policy.certificateSha256.includes(result.CertificateSha256)) throw new Error('安装器签名、身份、证书或路径不符合发行策略');
  return true;
}
function verifySignature(file, policy, runner = execFile, powershell = () => windowsTool('WindowsPowerShell\\v1.0\\powershell.exe')) {
  return new Promise((resolve, reject) => {
    let command;
    try {
      if (!path.win32.isAbsolute(file) || file.startsWith('\\\\') || !policy?.publisherName) throw new Error('验签路径/发行策略无效');
      const literal = file.replace(/'/g, "''");
      command = "$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);" + `$s=Get-AuthenticodeSignature -LiteralPath '${literal}';` + "$h=[Security.Cryptography.SHA256]::Create();$pin=if($s.SignerCertificate){([BitConverter]::ToString($h.ComputeHash($s.SignerCertificate.RawData))).Replace('-','')}else{''};[pscustomobject]@{Status=$s.Status.ToString();Path=$s.Path;Subject=$s.SignerCertificate.Subject;CertificateSha256=$pin}|ConvertTo-Json -Compress";
      runner(powershell(), ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(command, 'utf16le').toString('base64')], { shell: false, windowsHide: true, timeout: 20000, maxBuffer: 65536, encoding: 'utf8' }, (error, stdout, stderr) => {
        if (error) { reject(new Error('验签进程失败或超时，拒绝更新')); return; }
        try { parseSignature(stdout, stderr, file, policy); resolve(); } catch (e) { reject(e); }
      });
    } catch (e) { reject(e); }
  });
}
async function verifyInstaller(file, policy, expectedSha512, signatureVerifier = verifySignature) {
  if (typeof expectedSha512 !== 'string' || !/^[a-zA-Z0-9+/]{86}==$/.test(expectedSha512)) throw new Error('发行摘要无效');
  const before = await fileHash(file);
  if (before !== expectedSha512) throw new Error('安装器 SHA512 不匹配');
  await signatureVerifier(file, policy);
  if (await fileHash(file) !== before) throw new Error('验签期间安装器发生变化');
  return { file, sha512: before };
}
module.exports = { validatePolicy, fileHash, parseSignature, verifySignature, verifyInstaller };
