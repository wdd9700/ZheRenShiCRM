'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { validatePolicy, verifySignature, verifyInstaller } = require('./signature.cjs');
function trustedUpdateUrl(value, policy) {
  try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password && u.origin === policy.origin && u.pathname.startsWith(new URL(policy.feedUrl).pathname); } catch { return false; }
}
function createStrictUpdater(policy) {
  const { NsisUpdater } = require('electron-updater');
  class StrictUpdater extends NsisUpdater {
    async verifySignature(file) {
      return this.verifyUpdateCodeSignature([policy.publisherName], file);
    }
    doInstall(options) {
      const receipt = this.strictInstallReceipt;
      if (!receipt || options.isAdminRightsRequired || this.installerPath !== receipt.file || !fs.lstatSync(receipt.file).isFile() || createHash('sha512').update(fs.readFileSync(receipt.file)).digest('base64') !== receipt.sha512) throw new Error('安装前最终摘要/路径不符，拒绝安装');
      this.strictInstallReceipt = null;
      return super.doInstall(options);
    }
  }
  const updater = new StrictUpdater({ provider: 'generic', url: policy.feedUrl, channel: 'latest', useMultipleRangeRequest: false });
  updater.verifyUpdateCodeSignature = async (publishers, file) => {
    if (publishers.length !== 1 || publishers[0] !== policy.publisherName) throw new Error('发布者配置不匹配');
    await verifySignature(file, policy);
    return null;
  };
  updater.autoDownload = false;
  updater.autoInstallOnAppQuit = false;
  updater.allowDowngrade = false;
  updater.allowPrerelease = false;
  updater.disableWebInstaller = true;
  updater.disableDifferentialDownload = true;
  updater.logger = null;
  updater.netSession.setPermissionRequestHandler((_w, _p, callback) => callback(false));
  updater.netSession.webRequest.onBeforeRequest((details, callback) => callback({ cancel: !trustedUpdateUrl(details.url, policy) }));
  return updater;
}
class UpdateController {
  constructor(rawPolicy, { factory = createStrictUpdater, verifier = verifyInstaller, confirm, flush } = {}) {
    this.policy = validatePolicy(rawPolicy);
    this.verifier = verifier;
    this.confirm = confirm;
    this.flush = flush;
    this.state = this.policy ? 'idle' : 'disabled';
    this.receipt = null;
    this.updater = this.policy ? factory(this.policy) : null;
    this.busy = false;
    this.updater?.on('error', () => { this.state = 'failed'; this.receipt = null; });
  }
  status() { return { state: this.state, version: this.version ?? null }; }
  async run(operation) {
    if (!this.updater) throw new Error('OTA 未配置，已禁用；请使用经核验的安装包覆盖升级');
    if (this.busy) throw new Error('更新操作进行中');
    this.busy = true;
    try { return await operation(); }
    catch (e) { this.state = 'failed'; this.receipt = null; throw e; }
    finally { this.busy = false; }
  }
  check() {
    return this.run(async () => {
      this.receipt = null;
      this.state = 'checking';
      const result = await this.updater.checkForUpdates();
      const info = result?.updateInfo;
      const current = this.updater.currentVersion.version;
      if (!info || typeof info.version !== 'string' || !/^\d+\.\d+\.\d+$/.test(info.version)) throw new Error('发行版本信息无效');
      const newer = info.version.split('.').map(Number);
      const old = current.split('.').map(Number);
      const cmp = newer.findIndex((v, i) => v !== old[i]);
      if (cmp < 0 || newer[cmp] < old[cmp]) { this.state = 'current'; return this.status(); }
      if (info.packages || !Array.isArray(info.files) || info.files.length !== 1 || info.files[0].isAdminRightsRequired) throw new Error('仅接受完整 per-user x64 EXE 发布');
      const file = info.files[0];
      const url = new URL(file.url, this.policy.feedUrl);
      if (!trustedUpdateUrl(url.href, this.policy) || !url.pathname.endsWith('-x64.exe') || !/^[a-zA-Z0-9+/]{86}==$/.test(file.sha512) || !Number.isSafeInteger(file.size) || file.size < 1) throw new Error('发行文件 URL/摘要/大小无效');
      this.expected = { sha512: file.sha512, size: file.size };
      this.version = info.version;
      this.state = 'available';
      return this.status();
    });
  }
  download() {
    return this.run(async () => {
      if (this.state !== 'available') throw new Error('请先检查可用更新');
      if (!await this.confirm('download', this.version)) return this.status();
      this.state = 'downloading';
      const files = await this.updater.downloadUpdate();
      if (!Array.isArray(files) || files.length !== 1 || fs.statSync(files[0]).size !== this.expected.size) throw new Error('下载文件或大小不符');
      this.receipt = await this.verifier(files[0], this.policy, this.expected.sha512);
      if (this.updater.installerPath !== this.receipt.file) throw new Error('更新缓存路径不符');
      this.state = 'ready';
      return this.status();
    });
  }
  install() {
    return this.run(async () => {
      if (this.state !== 'ready' || !this.receipt) throw new Error('没有通过验证的待安装更新');
      if (!await this.confirm('install', this.version)) return this.status();
      await this.flush();
      this.receipt = await this.verifier(this.receipt.file, this.policy, this.expected.sha512);
      if (this.updater.installerPath !== this.receipt.file) throw new Error('安装缓存路径变化');
      this.updater.strictInstallReceipt = this.receipt;
      this.state = 'installing';
      this.updater.quitAndInstall(false, true);
      return this.status();
    });
  }
}
function loadPolicy(resources) {
  const file = path.join(resources, 'ota-policy.json');
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { if (e.code === 'ENOENT') return { enabled: false }; throw new Error('OTA 发行策略无法读取，拒绝启用'); }
}
module.exports = { trustedUpdateUrl, createStrictUpdater, UpdateController, loadPolicy };
