'use strict';
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const { spawn } = require('node:child_process');
const { validateConnection } = require('./settings.cjs');
function windowsTool(relative) {
  const root = process.env.SystemRoot;
  if (!root || !/^[a-z]:\\windows$/i.test(root)) throw new Error('无法确定可信 Windows 系统目录');
  const tool = path.win32.join(root, 'System32', relative);
  if (!fs.existsSync(tool)) throw new Error('Windows 系统组件不存在：' + relative);
  return tool;
}
function sshArguments(c) {
  validateConnection(c);
  return ['-F', 'NUL', '-N', '-T', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none', '-o', 'PasswordAuthentication=no', '-o', 'PreferredAuthentications=publickey', '-o', 'GlobalKnownHostsFile=NUL', '-o', `UserKnownHostsFile="${c.knownHostsFile}"`, '-i', c.identityFile, '-L', `127.0.0.1:18088:127.0.0.1:${c.remotePort}`, `${c.user}@${c.host}`];
}
function portFree() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', () => reject(new Error('127.0.0.1:18088 已占用；请明确选择外部隧道模式，不会换端口或结束占用进程')));
    server.listen(18088, '127.0.0.1', () => server.close(() => resolve()));
  });
}
function portReady() {
  return new Promise(resolve => {
    const socket = net.connect({ host: '127.0.0.1', port: 18088 });
    socket.setTimeout(250);
    socket.once('connect', () => { socket.destroy(); resolve(true); });
    socket.once('error', () => resolve(false));
    socket.once('timeout', () => { socket.destroy(); resolve(false); });
  });
}
class Tunnel {
  constructor(onExit) { this.child = null; this.onExit = onExit; }
  async start(c) {
    if (this.child) throw new Error('本客户端已有隧道；关闭客户端后可重新配置');
    for (const file of [c.identityFile, c.knownHostsFile]) if (!fs.statSync(file).isFile()) throw new Error('SSH 路径不是文件');
    await portFree();
    const child = spawn(windowsTool('OpenSSH\\ssh.exe'), sshArguments(c), { windowsHide: true, shell: false, stdio: ['ignore', 'ignore', 'pipe'] });
    this.child = child;
    let failure = null;
    child.once('error', () => { failure = new Error('无法启动 Windows OpenSSH'); });
    child.once('exit', code => {
      if (this.child === child) { this.child = null; this.onExit?.(code); }
      failure = new Error('SSH 已退出；检查连接、用户专属密钥及已核验 known_hosts（不会自动接受主机密钥）');
    });
    child.stderr.on('data', () => {});
    for (let i = 0; i < 170; i++) {
      if (failure) throw failure;
      if (await portReady()) {
        await new Promise(resolve => setTimeout(resolve, 200));
        if (failure) throw failure;
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    this.stop();
    throw new Error('SSH 隧道启动超时');
  }
  stop() { const child = this.child; this.child = null; if (child) child.kill(); }
}
module.exports = { windowsTool, sshArguments, portFree, portReady, Tunnel };
