#!/usr/bin/env python3
"""Explicit opt-in, cross-platform bootstrap for Audiobook Harness."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, shutil, subprocess, sys, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; LOCK=ROOT/'models.lock.json'; TOOLS=ROOT/'.tools'

def run(*command: str) -> None: subprocess.run(command,check=True)
def yes(prompt: str, force: bool) -> bool: return force or input(prompt+' [y/N] ').strip().casefold() in {'y','yes'}
def sha(path: Path) -> str:
 h=hashlib.sha256();
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def platform_commands() -> list[list[str]] | None:
 system=platform.system()
 if system=='Darwin': return [['brew','install','ffmpeg','espeak-ng']]
 if system=='Windows': return [
  ['winget','install','--exact','--accept-package-agreements','--accept-source-agreements','Gyan.FFmpeg'],
  ['winget','install','--exact','--accept-package-agreements','--accept-source-agreements','eSpeak-NG.eSpeak-NG'],
 ]
 if shutil.which('apt-get'):
  install=['apt-get','install','-y','ffmpeg','espeak-ng']
  update=['apt-get','update']
  # Containers commonly run as root and deliberately omit sudo. On a normal
  # Linux workstation retain explicit privilege escalation rather than hiding it.
  if getattr(os, 'geteuid', lambda: 1)() != 0:
   sudo=shutil.which('sudo')
   if not sudo: raise RuntimeError('apt-get requires root or sudo; install FFmpeg and eSpeak NG manually.')
   install.insert(0,sudo); update.insert(0,sudo)
  return [update, install]
 if shutil.which('dnf'): return [['sudo','dnf','install','-y','ffmpeg','espeak-ng']]
 if shutil.which('pacman'): return [['sudo','pacman','-S','--needed','ffmpeg','espeak-ng']]
 return None
def fetch(item: dict[str,str]) -> None:
 path=ROOT/item['path']; path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists() and sha(path)==item['sha256']: print('verified',path); return
 print('downloading',item['id']); urllib.request.urlretrieve(item['url'],path)
 if sha(path)!=item['sha256']: path.unlink(missing_ok=True); raise RuntimeError(f"checksum mismatch: {item['id']}")
def main() -> None:
 p=argparse.ArgumentParser(); p.add_argument('--interactive',action='store_true'); p.add_argument('--yes',action='store_true'); p.add_argument('--install-system',action='store_true'); p.add_argument('--download-models',action='store_true'); p.add_argument('--with-verification',action='store_true'); p.add_argument('--with-mfa',action='store_true'); a=p.parse_args()
 if a.interactive: a.install_system=yes('Install system tools (FFmpeg and eSpeak NG)?',a.yes); a.download_models=yes('Install local ASR verification and download pinned Kokoro and Whisper model weights?',a.yes); a.with_mfa=yes('Create the separate MFA alignment environment?',a.yes)
 if a.download_models: a.with_verification=True
 if a.install_system:
  commands=platform_commands()
  if not commands: raise RuntimeError('No supported system package manager; see docs/SETUP.md')
  for command in commands: run(*command)
 venv=ROOT/'.venv'
 if not venv.exists(): run(sys.executable,'-m','venv',str(venv))
 pip=venv/('Scripts/pip.exe' if platform.system()=='Windows' else 'bin/pip'); run(str(pip),'install','--upgrade','pip'); target=f'{ROOT}[verification]' if a.with_verification else str(ROOT); run(str(pip),'install','-e',target)
 if a.download_models:
  for item in json.loads(LOCK.read_text())['models']: fetch(item)
 if a.with_mfa:
  mamba=shutil.which('micromamba') or shutil.which('mamba')
  if not mamba: raise RuntimeError('Install micromamba first; this is intentionally not downloaded implicitly. See docs/SETUP.md.')
  prefix=TOOLS/'mfa'; run(mamba,'create','-y','-p',str(prefix),'-c','conda-forge','montreal-forced-aligner')
  env={**os.environ,'MFA_ROOT_DIR':str(TOOLS/'mfa-root')}; mfa=str(prefix/('Scripts/mfa.exe' if platform.system()=='Windows' else 'bin/mfa'))
  subprocess.run([mfa,'model','download','acoustic','english_us_arpa'],check=True,env=env); subprocess.run([mfa,'model','download','g2p','english_us_arpa'],check=True,env=env)
  downloaded=[]
  for path in sorted((TOOLS/'mfa-root'/'pretrained_models').rglob('*')):
   if path.is_file(): downloaded.append({'path':str(path.relative_to(ROOT)),'sha256':sha(path)})
  (TOOLS/'mfa-installed-models.json').write_text(json.dumps({'source':'MFA model download command','files':downloaded},indent=2)+'\n')
 print('Run',venv/('Scripts/audiobook-harness.exe' if platform.system()=='Windows' else 'bin/audiobook-harness'),'doctor')
if __name__=='__main__': main()
