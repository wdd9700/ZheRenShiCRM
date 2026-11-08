'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID, createHash } = require('node:crypto');
const transport = require('./ota-transport.cjs');
const { verifyManifest, authorizeRelease, ReleaseState, compareVersions, verifyBoundInstallerSync, verifyPackageBytesSync } = require('./signed-manifest.cjs');
function createPinnedInstaller(policy, { dataDirectory, currentVersion, stateStore, appAdapter } = {}) {
  const { NsisUpdater } = require('electron-updater');
  const cacheDirectory = path.join(dataDirectory, 'ota-pinned');
  class PinnedInstaller extends NsisUpdater {
    async verifySignature(file) {
      if (!this.authorizedReceipt || file !== this.authorizedReceipt.file) throw new Error('没有已授权的签名 manifest / 安装包');
      verifyBoundInstallerSync(this.authorizedReceipt, policy, currentVersion, stateStore.load(), cacheDirectory);
      return null;
    }
    async prepareVerified(receipt) {
      verifyBoundInstallerSync(receipt, policy, currentVersion, stateStore.load(), cacheDirectory);
      this.authorizedReceipt = receipt;
      const hash = createHash('sha512'); for await (const chunk of fs.createReadStream(receipt.file)) hash.update(chunk);
      const helper = await this.getOrCreateDownloadHelper();
      await helper.setDownloadedFile(receipt.file, null, { version: receipt.release.manifest.version }, { info: { sha512: hash.digest('base64'), isAdminRightsRequired: false } }, path.basename(receipt.file), false);
    }
    doInstall(options) {
      const receipt = this.authorizedReceipt;
      if (!receipt || this.installerPath !== receipt.file || options.isAdminRightsRequired) throw new Error('pinned-key 安装状态或路径无效');
      verifyBoundInstallerSync(receipt, policy, currentVersion, stateStore.load(), cacheDirectory);
      this.authorizedReceipt = null;
      return super.doInstall(options);
    }
  }
  const updater = new PinnedInstaller(null, appAdapter);
  updater.autoDownload = false; updater.autoInstallOnAppQuit = false; updater.allowDowngrade = false;
  updater.allowPrerelease = false; updater.disableWebInstaller = true; updater.disableDifferentialDownload = true; updater.logger = null;
  updater.verifyUpdateCodeSignature = async () => { throw new Error('pinned-key 策略禁止未绑定 manifest 的默认签名入口'); };
  return updater;
}
class PinnedUpdateController {
  constructor(policy, { dataDirectory, currentVersion, confirm, flush, installerFactory = createPinnedInstaller, network = transport } = {}) {
    if (!path.isAbsolute(dataDirectory) || !currentVersion || typeof confirm !== 'function' || typeof flush !== 'function') throw new Error('pinned-key 更新上下文缺失');
    this.policy = policy; this.currentVersion = currentVersion; this.confirm = confirm; this.flush = flush; this.network = network;
    this.cacheDirectory = path.join(dataDirectory, 'ota-pinned'); this.stateStore = new ReleaseState(dataDirectory);
    this.stateStore.load();
    this.installer = installerFactory(policy, { dataDirectory, currentVersion, stateStore: this.stateStore });
    this.installer.on('error', () => { this.state = 'failed'; this.receipt = null; });
    this.state = 'idle'; this.busy = false; this.receipt = null;
  }
  status() { return { state: this.state, version: this.release?.manifest.version ?? null, trust: this.policy.trust }; }
  async run(fn) {
    if (this.busy) throw new Error('更新操作进行中'); this.busy = true;
    try { return await fn(); } catch (error) { this.state = 'failed'; this.receipt = null; throw error; } finally { this.busy = false; }
  }
  check() {
    return this.run(async () => {
      this.state = 'checking'; this.receipt = null; this.release = null;
      const bytes = await this.network.fetchBytes(new URL('manifest.json', this.policy.feedUrl).href, this.policy, 16384);
      const signature = await this.network.fetchBytes(new URL('manifest.sig', this.policy.feedUrl).href, this.policy, 64);
      const release = authorizeRelease(verifyManifest(bytes, signature, this.policy), this.policy, this.currentVersion, this.stateStore.load());
      this.bytes = Buffer.from(bytes); this.signature = Buffer.from(signature); this.release = release;
      this.state = compareVersions(release.manifest.version, this.currentVersion) === 0 ? 'current' : 'available';
      return this.status();
    });
  }
  download() {
    return this.run(async () => {
      if (this.state !== 'available' || !this.release) throw new Error('没有已验签可下载更新');
      if (!await this.confirm('download', this.release.manifest.version)) return this.status();
      this.state = 'downloading';
      const release = authorizeRelease(verifyManifest(this.bytes, this.signature, this.policy), this.policy, this.currentVersion, this.stateStore.load());
      fs.mkdirSync(this.cacheDirectory, { recursive: true });
      if (fs.lstatSync(this.cacheDirectory).isSymbolicLink()) throw new Error('更新缓存不能是链接');
      const file = path.join(this.cacheDirectory, release.manifest.sequence + '-' + release.manifestSha256 + '-' + release.manifest.file);
      const temporary = file + '.' + randomUUID() + '.part';
      const receipt = { file, bytes: Buffer.from(this.bytes), signature: Buffer.from(this.signature), release };
      try {
        if (!fs.existsSync(file)) {
          await this.network.downloadFile(new URL(release.manifest.file, this.policy.feedUrl).href, this.policy, temporary, release.manifest.size);
          verifyPackageBytesSync(temporary, release.manifest);
          fs.renameSync(temporary, file);
        }
        verifyBoundInstallerSync(receipt, this.policy, this.currentVersion, this.stateStore.load(), this.cacheDirectory);
        this.stateStore.accept(release, this.policy, this.currentVersion);
        await this.installer.prepareVerified(receipt);
        this.receipt = receipt; this.state = 'ready'; return this.status();
      } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
    });
  }
  install() {
    return this.run(async () => {
      if (this.state !== 'ready' || !this.receipt) throw new Error('没有通过签名/摘要验证的更新');
      if (!await this.confirm('install', this.release.manifest.version)) return this.status();
      await this.flush();
      verifyBoundInstallerSync(this.receipt, this.policy, this.currentVersion, this.stateStore.load(), this.cacheDirectory);
      await this.installer.prepareVerified(this.receipt);
      this.state = 'installing'; this.installer.quitAndInstall(false, true); return this.status();
    });
  }
}
module.exports = { createPinnedInstaller, PinnedUpdateController };
