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
def platform_command() -> list[str] | None:
 system=platform.system()
 if system=='Darwin': return ['brew','install','ffmpeg','espeak-ng']
 if system=='Windows': return ['winget','install','--exact','--accept-package-agreements','--accept-source-agreements','Gyan.FFmpeg','eSpeak-NG.eSpeak-NG']
 if shutil.which('apt-get'): return ['sudo','apt-get','install','-y','ffmpeg','espeak-ng']
 if shutil.which('dnf'): return ['sudo','dnf','install','-y','ffmpeg','espeak-ng']
 if shutil.which('pacman'): return ['sudo','pacman','-S','--needed','ffmpeg','espeak-ng']
 return None
def fetch(item: dict[str,str]) -> None:
 path=ROOT/item['path']; path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists() and sha(path)==item['sha256']: print('verified',path); return
 print('downloading',item['id']); urllib.request.urlretrieve(item['url'],path)
 if sha(path)!=item['sha256']: path.unlink(missing_ok=True); raise RuntimeError(f"checksum mismatch: {item['id']}")
def main() -> None:
 p=argparse.ArgumentParser(); p.add_argument('--interactive',action='store_true'); p.add_argument('--yes',action='store_true'); p.add_argument('--install-system',action='store_true'); p.add_argument('--download-models',action='store_true'); p.add_argument('--with-mfa',action='store_true'); a=p.parse_args()
 if a.interactive: a.install_system=yes('Install system tools (FFmpeg and eSpeak NG)?',a.yes); a.download_models=yes('Download pinned Kokoro and Whisper model weights?',a.yes); a.with_mfa=yes('Create the separate MFA alignment environment?',a.yes)
 if a.install_system:
  cmd=platform_command()
  if not cmd: raise RuntimeError('No supported system package manager; see docs/SETUP.md')
  run(*cmd)
 venv=ROOT/'.venv'
 if not venv.exists(): run(sys.executable,'-m','venv',str(venv))
 pip=venv/('Scripts/pip.exe' if platform.system()=='Windows' else 'bin/pip'); run(str(pip),'install','--upgrade','pip'); run(str(pip),'install','-e',str(ROOT))
 if a.download_models:
  for item in json.loads(LOCK.read_text())['models']: fetch(item)
 if a.with_mfa:
  mamba=shutil.which('micromamba') or shutil.which('mamba')
  if not mamba: raise RuntimeError('Install micromamba first; this is intentionally not downloaded implicitly. See docs/SETUP.md.')
  prefix=TOOLS/'mfa'; run(mamba,'create','-y','-p',str(prefix),'-c','conda-forge','montreal-forced-aligner')
  env={**os.environ,'MFA_ROOT_DIR':str(TOOLS/'mfa-root')}; subprocess.run([str(prefix/('Scripts/mfa.exe' if platform.system()=='Windows' else 'bin/mfa')),'model','download','acoustic','english_us_arpa'],check=True,env=env); subprocess.run([str(prefix/('Scripts/mfa.exe' if platform.system()=='Windows' else 'bin/mfa')),'model','download','g2p','english_us_arpa'],check=True,env=env)
 print('Run',venv/('Scripts/audiobook-harness.exe' if platform.system()=='Windows' else 'bin/audiobook-harness'),'doctor')
if __name__=='__main__': main()
