'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { generateKeyPairSync, createPrivateKey, createPublicKey, createHash, sign } = require('node:crypto');
const { windowsTool } = require('../src/tunnel.cjs');
const { FORMAT, validateManifest } = require('../src/signed-manifest.cjs');
function keyId(publicKey) { const key = publicKey?.type === 'public' ? publicKey : createPublicKey(publicKey); return createHash('sha256').update(key.export({ type: 'spki', format: 'der' })).digest('hex').slice(0, 32); }
function checkKeyDirectory(directory) {
  if (!path.isAbsolute(directory) || directory.startsWith('\\\\')) throw new Error('密钥目录必须是明确本机绝对路径');
  for (let current = directory; ; current = path.dirname(current)) { if (fs.lstatSync(current).isSymbolicLink()) throw new Error('密钥目录不能经过链接'); if (current === path.dirname(current)) break; }
  const literal = directory.replace(/'/g, "''");
  const script = "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User;$allowed=@($sid.Value,'S-1-5-18');" + `$dir='${literal}';` + "$acl=Get-Acl -LiteralPath $dir;if(!$acl.AreAccessRulesProtected -or $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value){throw 'Unprotected key directory'};foreach($item in @((Get-Item -LiteralPath $dir)) + @(Get-ChildItem -LiteralPath $dir -Force)){foreach($r in (Get-Acl -LiteralPath $item.FullName).GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){if($r.AccessControlType -eq 'Allow' -and $r.IdentityReference.Value -notin $allowed){throw 'Unexpected key access principal'}}}";
  execFileSync(windowsTool('WindowsPowerShell\\v1.0\\powershell.exe'), ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], { shell: false, windowsHide: true, timeout: 20000, stdio: ['ignore', 'ignore', 'pipe'] });
}
function generate(directory) {
  checkKeyDirectory(directory);
  if (fs.readdirSync(directory).length) throw new Error('密钥目录必须为空，拒绝覆盖任何已有文件');
  const pair = generateKeyPairSync('ed25519');
  fs.writeFileSync(path.join(directory, 'private-key.pem'), pair.privateKey.export({ type: 'pkcs8', format: 'pem' }), { flag: 'wx', mode: 0o600 });
  fs.writeFileSync(path.join(directory, 'public-key.pem'), pair.publicKey.export({ type: 'spki', format: 'pem' }), { flag: 'wx', mode: 0o600 });
  fs.writeFileSync(path.join(directory, 'key-id.txt'), keyId(pair.privateKey) + '\n', { flag: 'wx', mode: 0o600 });
}
function signRelease(installer, version, sequence, privateKey) {
  if (privateKey.asymmetricKeyType !== 'ed25519') throw new Error('发布私钥必须是 Ed25519');
  const stat = fs.lstatSync(installer); if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('安装器必须是普通文件');
  const manifest = validateManifest({ format: FORMAT, keyId: keyId(privateKey), version, sequence, platform: 'win32', arch: 'x64', file: path.basename(installer), size: stat.size, sha256: createHash('sha256').update(fs.readFileSync(installer)).digest('hex') });
  const bytes = Buffer.from(JSON.stringify(manifest, null, 2) + '\n', 'utf8');
  return { bytes, signature: sign(null, bytes, privateKey), publicKey: createPublicKey(privateKey).export({ type: 'spki', format: 'pem' }).toString(), manifest };
}
if (require.main === module) {
  try {
    const [mode, directory, installer, version, sequence, output] = process.argv.slice(2);
    if (mode === 'generate' && directory && process.argv.length === 4) generate(path.resolve(directory));
    else if (mode === 'sign' && output && process.argv.length === 8) {
      checkKeyDirectory(path.resolve(directory));
      const privateFile = path.join(directory, 'private-key.pem');
      if (fs.lstatSync(privateFile).isSymbolicLink()) throw new Error('私钥不能是链接');
      const key = createPrivateKey(fs.readFileSync(privateFile));
      const release = signRelease(path.resolve(installer), version, Number(sequence), key);
      if (fs.readFileSync(path.join(directory, 'key-id.txt'), 'utf8').trim() !== release.manifest.keyId) throw new Error('keyId 文件与私钥不符');
      fs.mkdirSync(output);
      fs.writeFileSync(path.join(output, 'manifest.json'), release.bytes, { flag: 'wx' });
      fs.writeFileSync(path.join(output, 'manifest.sig'), release.signature, { flag: 'wx' });
    } else throw new Error('用法: generate <安全空目录> 或 sign <密钥目录> <安装器> <版本> <序号> <全新输出目录>');
  } catch { process.stderr.write('离线发布操作失败；未输出私钥。检查明确路径、独占ACL、Ed25519密钥、文件名/版本和新输出目录。\n'); process.exitCode = 1; }
}
module.exports = { keyId, checkKeyDirectory, generate, signRelease };
