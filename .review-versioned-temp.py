import subprocess, tempfile, pathlib, hashlib, ast
BASH='D:/Program Files/Git/bin/bash.exe'
BR='feat/remote-trial-deployment-package-c010400'
def blob(rev,path): return subprocess.check_output(['git','show',rev+':'+path]).decode()
sources={v:blob(v,'deploy/remote/trial.sh') for v in [BR,'eaffe942']}
mock=r'''
require_docker() { :; }
python3() { :; }
verify_image_identity() { :; }
docker_cli() {
    printf 'docker %s\n' "$*" >> "$RUNTIME/events"
    if [ "$1" = load ]; then return 0; fi
    case "$*" in
      *'{{.Id}}'*) printf '%s\n' "$3" ;;
      *configurator*) printf '%s exited 0\n' "$(cat "$RUNTIME/running")" ;;
      *) printf '%s running\n' "$(cat "$RUNTIME/running")" ;;
    esac
}
compose() {
    printf 'compose %s\n' "$*" >> "$RUNTIME/events"
    case "$1" in
      stop) [ "${MODE:-}" != stopfail ] ;;
      up)
        printf '%s\n' "$NEW_CONFIG" > "$RUNTIME/running"
        case "${MODE:-}" in
          upfail|rollbackfail|stopfail) return 73 ;;
          term) kill -TERM $$ ;;
        esac ;;
      *) printf 'sitehash\n' ;;
    esac
}
backup() { printf 'backup-four-readable\n' >> "$RUNTIME/events"; }
mv() {
    case "${MODE:-}:$1" in
      renamefail:*/.release.env.site-update-*) return 74 ;;
      rollbackfail:*/.image.env.rollback-*) return 75 ;;
    esac
    command mv "$@"
}
'''
A='sha256:'+'1'*64
B='sha256:'+'2'*64
C='sha256:'+'3'*64
with tempfile.TemporaryDirectory(prefix='review-versioned-',dir='.') as td:
 root=pathlib.Path(td).resolve()
 remote=root/'tools'; remote.mkdir()
 (remote/'docker.sh').write_text('')
 (remote/'image-rootfs-layers.txt').write_text(A+'\n')
 archive=root/'image.tar'; archive.write_bytes(b'synthetic archive explicit verifier mock')
 sha='sha256:'+hashlib.sha256(archive.read_bytes()).hexdigest()
 def release(config):
  return '\n'.join(f'{k}={v}' for k,v in dict(CRM_IMAGE_CONFIG=config,CRM_IMAGE_INDEX=A,CRM_IMAGE_PLATFORM_MANIFEST=A,CRM_IMAGE_ARCHIVE_SHA256=sha,CRM_RESOURCE_IMPORT_COMMIT='a'*40,CRM_TEAM_ACCESS_COMMIT='b'*40,CRM_UPSTREAM_CRM_COMMIT='c'*40).items())+'\n'
 (remote/'release.env').write_text(release(A))
 releases={}
 for k in [A,B,C]:
  p=root/k[-1];p.mkdir();(p/'release.env').write_text(release(k));(p/'image-rootfs-layers.txt').write_text(k+'\n');releases[k]=p
 def make(name):
  p=root/name;p.mkdir();(p/'.env').write_text('synthetic-only\n');(p/'image.env').write_text('CRM_IMAGE='+A+'\n');(p/'migrated-twice').write_text('done');(p/'running').write_text(A+'\n');return p
 def run(rt,action='update',config=B,rev=BR,mode='',extra=''):
  # Original functions and set-e behavior retained, only external services explicitly mocked.
  src=sources[rev]
  funcs=src[src.index('usage() {'):src.rindex('\ncase "$ACTION" in')]
  pre=f'''set -eu\nREMOTE='{remote.as_posix()}'\nRUNTIME='{rt.as_posix()}'\nENV_FILE="$RUNTIME/.env"\nIMAGE_FILE="$RUNTIME/image.env"\nPROJECT=crm-trial-c010400\nSITE=crm.localhost\nACTION=help\nset --\nCONFIRM_SITE_UPDATE=1\nMODE={mode}\nUPDATE_RELEASE_DIR='{releases[config].as_posix()}'\nIMAGE_ARCHIVE='{archive.as_posix()}'\n'''
  call={'update':'update_site_image','stop':'maintenance_stop','restore':'restore_old_lock'}[action]
  r=subprocess.run([BASH,'-s'],input=pre+funcs+'\n'+mock+'\n'+extra+'\n'+call+'\n',text=True,capture_output=True)
  return r
 def show(label,r,rt): print(label,'rc='+str(r.returncode),'lock='+ (rt/'image.env').read_text().strip(),'state='+((rt/'site-update.state').read_text().strip() if (rt/'site-update.state').exists() else 'absent'), 'stop='+str('compose stop' in (rt/'events').read_text() if (rt/'events').exists() else False)); print('  ',r.stderr.strip()[-400:])
 for legacy in [False,True]:
  rt=make('legacy' if legacy else 'new')
  r=run(rt,rev='eaffe942' if legacy else BR);assert r.returncode==0,r.stderr
  show('first legacy='+str(legacy),r,rt)
  r=run(rt,config=C);assert r.returncode==0,r.stderr;show('second legacy='+str(legacy),r,rt)
  r=run(rt,config=C);assert r.returncode!=0;show('repeat',r,rt)
 for mode in ['renamefail','rollbackfail','stopfail','term']:
  rt=make(mode);assert run(rt,rev='eaffe942').returncode==0
  r=run(rt,config=C,mode=mode);assert r.returncode!=0;show('second '+mode,r,rt)
  if mode!='rollbackfail': assert (rt/'image.env').read_text().strip()=='CRM_IMAGE='+B
  assert (rt/'release.env').read_text()==release(B)
  if mode=='renamefail':
   r=run(rt,action='stop');show('manual stop after rollback',r,rt)
   r=run(rt,action='restore');show('restore after manual stop',r,rt)
   print('  metadata exists:',(rt/'release.env').exists(),(rt/'image-rootfs-layers.txt').exists())
 # Both-new generations: manual stop rewrites failed C to B and restore picks B's A backup.
 rt=make('wrong-generation');assert run(rt).returncode==0
 r=run(rt,config=C,mode='renamefail');assert r.returncode!=0
 assert run(rt,action='stop').returncode==0
 r=run(rt,action='restore');show('WRONG GENERATION restore',r,rt)
 # Missing state with retained first-update evidence is accepted.
 rt=make('missing-state');assert run(rt,rev='eaffe942').returncode==0
 (rt/'site-update.state').unlink()
 r=run(rt,config=C);show('missing state existing metadata',r,rt)
 # Current running image mismatches current lock; update succeeds.
 rt=make('wrong-running');assert run(rt,rev='eaffe942').returncode==0
 (rt/'running').write_text(A+'\n')
 r=run(rt,config=C);show('wrong running before second',r,rt)
 # Current config repeated after old first round: new generation paths do not yet exist.
 rt=make('old-repeat');assert run(rt,rev='eaffe942').returncode==0
 r=run(rt,config=B);show('old repeat config',r,rt)
 chk=subprocess.run([BASH,'-s'],input=f'test -f "{rt.as_posix()}/.release.env.site-update-{B}.tmp"',text=True)
 print('old-repeat wrote temporary metadata:',chk.returncode==0)
for p in ['trial.sh','docker.sh','preflight.sh','apply-tools-update.sh']:
 r=subprocess.run([BASH,'-n'],input=blob(BR,'deploy/remote/'+p),text=True,capture_output=True);assert r.returncode==0,r.stderr
for p in ['verify_backup.py','verify_image_archive.py']:ast.parse(blob(BR,'deploy/remote/'+p))
print('syntax and Python AST PASS; all synthetic fixtures removed')
