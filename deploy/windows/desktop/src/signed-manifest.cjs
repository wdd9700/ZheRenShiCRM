'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { createPublicKey, createHash, verify, randomUUID } = require('node:crypto');
const FORMAT = 'philosopher-crm-ota-v1';
const MAX_PACKAGE = 512 * 1024 * 1024;
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
function versionParts(value) {
  if (typeof value !== 'string' || !/^(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})$/.test(value)) throw new Error('OTA 版本必须是严格稳定版 x.y.z');
  return value.split('.').map(Number);
}
function compareVersions(a, b) { const x = versionParts(a); const y = versionParts(b); for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return Math.sign(x[i] - y[i]); return 0; }
function validatePinnedPolicy(raw, base) {
  if (typeof raw.keyId !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(raw.keyId) || !Number.isSafeInteger(raw.minSequence) || raw.minSequence < 1) throw new Error('缺少固定 keyId / 最低发布序号');
  if (typeof raw.publicKey !== 'string' || raw.publicKey.length > 2048 || !raw.publicKey.startsWith('-----BEGIN PUBLIC KEY-----') || raw.publicKey.includes('PRIVATE KEY')) throw new Error('缺少固定 Ed25519 公钥');
  const key = createPublicKey(raw.publicKey);
  if (key.asymmetricKeyType !== 'ed25519') throw new Error('OTA 公钥必须是 Ed25519');
  if (!/^\/[a-zA-Z0-9/_-]*\/$/.test(new URL(base.feedUrl).pathname) && new URL(base.feedUrl).pathname !== '/') throw new Error('固定发布目录不能含编码或特殊路径');
  return { ...base, trust: 'pinned-key-ed25519', keyId: raw.keyId, publicKey: key.export({ type: 'spki', format: 'pem' }).toString(), minSequence: raw.minSequence };
}
function validateManifest(value) {
  const keys = ['format', 'keyId', 'version', 'sequence', 'platform', 'arch', 'file', 'size', 'sha256'];
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length !== keys.length || !keys.every(key => Object.hasOwn(value, key))) throw new Error('签名 manifest 字段无效');
  versionParts(value.version);
  if (value.format !== FORMAT || value.platform !== 'win32' || value.arch !== 'x64' || typeof value.keyId !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(value.keyId) || !Number.isSafeInteger(value.sequence) || value.sequence < 1 || !Number.isSafeInteger(value.size) || value.size < 1 || value.size > MAX_PACKAGE || !/^[a-f0-9]{64}$/.test(value.sha256) || value.file !== `PhilosopherStoneCRM-Setup-${value.version}-x64.exe`) throw new Error('签名 manifest 平台/架构/文件/大小/摘要/序号无效');
  return Object.freeze(value);
}
function verifyManifest(bytes, signature, policy) {
  if (!Buffer.isBuffer(bytes) || bytes.length < 1 || bytes.length > 16384 || !Buffer.isBuffer(signature) || signature.length !== 64) throw new Error('manifest / Ed25519 签名长度无效');
  if (!verify(null, bytes, createPublicKey(policy.publicKey), signature)) throw new Error('manifest Ed25519 签名不可信');
  const decoded = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  const manifest = validateManifest(JSON.parse(decoded));
  if (manifest.keyId !== policy.keyId) throw new Error('签名 keyId 不符合客户端固定信任根');
  return { manifest, manifestSha256: sha256(bytes) };
}
function authorizeRelease(release, policy, currentVersion, state) {
  const m = release.manifest;
  if (m.sequence < policy.minSequence || compareVersions(m.version, currentVersion) < 0) throw new Error('拒绝版本/发布序号回退');
  if (state) {
    if (m.sequence < state.sequence || compareVersions(m.version, state.version) < 0 || (m.sequence === state.sequence && (release.manifestSha256 !== state.manifestSha256 || m.keyId !== state.keyId))) throw new Error('拒绝已见发布回退或同序号替换');
  }
  return release;
}
class ReleaseState {
  constructor(directory) { this.file = path.join(directory, 'ota-high-water.json'); }
  load() {
    if (!fs.existsSync(this.file)) return null;
    const stat = fs.lstatSync(this.file); if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 4096) throw new Error('OTA 高水位文件无效，拒绝覆盖');
    const value = JSON.parse(fs.readFileSync(this.file, 'utf8'));
    if (value.format !== 1 || !Number.isSafeInteger(value.sequence) || value.sequence < 1 || !/^[a-f0-9]{64}$/.test(value.manifestSha256) || typeof value.keyId !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(value.keyId)) throw new Error('OTA 高水位内容损坏，拒绝覆盖');
    versionParts(value.version);
    return value;
  }
  accept(release, policy, currentVersion) {
    const prior = this.load(); authorizeRelease(release, policy, currentVersion, prior);
    if (prior?.sequence === release.manifest.sequence) return;
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const temporary = this.file + '.' + randomUUID() + '.tmp';
    const m = release.manifest;
    try { fs.writeFileSync(temporary, JSON.stringify({ format: 1, sequence: m.sequence, version: m.version, keyId: m.keyId, manifestSha256: release.manifestSha256 }), { flag: 'wx', mode: 0o600 }); fs.renameSync(temporary, this.file); }
    finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
  }
}
function verifyBoundInstallerSync(receipt, policy, currentVersion, state, cacheDirectory) {
  const release = authorizeRelease(verifyManifest(receipt.bytes, receipt.signature, policy), policy, currentVersion, state);
  const expected = path.join(cacheDirectory, release.manifest.sequence + '-' + release.manifestSha256 + '-' + release.manifest.file);
  if (path.resolve(receipt.file) !== expected) throw new Error('安装器不在受控缓存路径');
  controlledCacheFileSync(receipt.file, cacheDirectory);
  verifyPackageBytesSync(receipt.file, release.manifest);
  return release;
}
function controlledCacheFileSync(file, cacheDirectory) {
  if (path.dirname(file) !== path.resolve(cacheDirectory) || fs.realpathSync(cacheDirectory).toLowerCase() !== path.resolve(cacheDirectory).toLowerCase()) throw new Error('安装器不在受控缓存路径');
  let stat;
  try { stat = fs.lstatSync(file); } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1 || fs.realpathSync(file).toLowerCase() !== path.resolve(file).toLowerCase()) throw new Error('更新缓存必须是受控普通文件，拒绝链接或其它类型');
  return stat;
}
function verifyPackageBytesSync(file, manifest) {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('签名安装包类型不符');
  if (stat.size !== manifest.size) throw Object.assign(new Error('签名安装包大小不符'), { code: 'OTA_PACKAGE_SIZE_MISMATCH' });
  const fd = fs.openSync(file, 'r'); const hash = createHash('sha256'); const buffer = Buffer.alloc(1024 * 1024);
  try { let count; while ((count = fs.readSync(fd, buffer, 0, buffer.length, null))) hash.update(buffer.subarray(0, count)); }
  finally { fs.closeSync(fd); }
  if (hash.digest('hex') !== manifest.sha256) throw Object.assign(new Error('签名安装包 SHA256 不匹配'), { code: 'OTA_PACKAGE_HASH_MISMATCH' });
}
module.exports = { FORMAT, MAX_PACKAGE, sha256, versionParts, compareVersions, validatePinnedPolicy, validateManifest, verifyManifest, authorizeRelease, ReleaseState, verifyBoundInstallerSync, verifyPackageBytesSync, controlledCacheFileSync };
