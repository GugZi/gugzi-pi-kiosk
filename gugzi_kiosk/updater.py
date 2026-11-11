#!/usr/bin/env python3
"""Install a tested release published by the configured GitHub repository.

Designed to be launched separately from the kiosk controller (systemd-run).
No remote URL is accepted from MQTT. Secrets and device-specific settings stay local.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

CONFIG = Path('/etc/gugzi-kiosk/config.json')
ROOT = Path('/opt/gugzi-kiosk')
STATUS = Path('/var/lib/gugzi-kiosk/update_status.json')
API = 'https://api.github.com/repos/{repo}/releases/latest'
ASSET = 'gugzi-pi-kiosk.zip'
HASH = ASSET + '.sha256'
MAX_SIZE = 10 * 1024 * 1024


def status(installed=None, latest=None, in_progress=None, error=None):
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    try:
        old = json.loads(STATUS.read_text())
    except (OSError, ValueError):
        old = {}
    if installed is not None:
        old['installed_version'] = installed
    if latest is not None:
        old['latest_version'] = latest
    if in_progress is not None:
        old['in_progress'] = in_progress
    if error is not None:
        old['error'] = str(error)[:200]
    tmp = STATUS.with_suffix('.tmp')
    tmp.write_text(json.dumps(old))
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATUS)


def installed_version():
    try:
        return (ROOT / 'current/VERSION').read_text().strip()
    except OSError:
        return '1.0.0'


def repo_name():
    cfg = json.loads(CONFIG.read_text())
    name = cfg.get('update', {}).get('repository', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', name):
        raise ValueError('Configure update.repository as owner/repo in /etc/gugzi-kiosk/config.json')
    return name


def request_json(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'GugZi-Pi-Kiosk-Updater',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status != 200:
            raise RuntimeError('GitHub API status: ' + str(resp.status))
        return json.load(resp)


def get_release():
    release = request_json(API.format(repo=repo_name()))
    tag = release.get('tag_name', '')
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise RuntimeError('Unexpected release tag: ' + tag)
    assets = {a['name']: a['browser_download_url'] for a in release.get('assets', [])}
    if ASSET not in assets or HASH not in assets:
        raise RuntimeError('Release does not contain zip + sha256 assets')
    prefix = f'https://github.com/{repo_name()}/releases/download/{tag}/'
    for name in (ASSET, HASH):
        if not assets[name].startswith(prefix):
            raise RuntimeError('Unexpected release download URL')
    return tag[1:], assets


def download(url, dest, limit=MAX_SIZE):
    request = urllib.request.Request(url, headers={'User-Agent': 'GugZi-Pi-Kiosk-Updater'})
    with urllib.request.urlopen(request, timeout=40) as response, dest.open('wb') as file:
        total = 0
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise RuntimeError('Release exceeds download size limit')
            file.write(chunk)


def extract_safe(zip_path, location):
    with zipfile.ZipFile(zip_path) as archive:
        entries = archive.infolist()
        if sum(item.file_size for item in entries) > MAX_SIZE:
            raise RuntimeError('Release content is too large')
        for item in entries:
            p = Path(item.filename)
            if p.is_absolute() or '..' in p.parts or not item.filename.startswith('gugzi-pi-kiosk/'):
                raise RuntimeError('Invalid release path')
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError('Symlink in release archive')
        archive.extractall(location)
    source = location / 'gugzi-pi-kiosk'
    for name in ('VERSION', 'install.sh', 'requirements.txt', 'gugzi-kiosk', 'systemd/gugzi-kiosk.service', 'gugzi_kiosk/controller.py', 'gugzi_kiosk/smart.py', 'scripts/cursor-cec.sh'):
        if not (source / name).is_file():
            raise RuntimeError('Release is missing ' + name)
    return source


def check_version(version):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid release version')


def install():
    if os.geteuid() != 0:
        raise SystemExit('Run as root (sudo gugzi-kiosk update)')
    old_version = installed_version()
    status(installed=old_version, in_progress=True, error='')
    destination = None
    old_target = None
    moved = False
    try:
        version, assets = get_release()
        check_version(version)
        status(latest=version)
        if version == old_version:
            print('Already up to date:', version)
            status(in_progress=False)
            return

        with tempfile.TemporaryDirectory(prefix='gugzi-update-') as td:
            work = Path(td)
            release_zip = work / ASSET
            checksum = work / HASH
            download(assets[ASSET], release_zip)
            download(assets[HASH], checksum, limit=2048)
            digest = hashlib.sha256(release_zip.read_bytes()).hexdigest()
            line = checksum.read_text().strip().splitlines()[0]
            expected = line.split()[0]
            if not re.fullmatch(r'[a-f0-9]{64}', expected) or digest != expected:
                raise RuntimeError('SHA256 verification failed')
            if len(line.split()) > 1 and line.split()[-1].lstrip('*') != ASSET:
                raise RuntimeError('Unexpected SHA256 filename')
            source = extract_safe(release_zip, work)
            if (source / 'VERSION').read_text().strip() != version:
                raise RuntimeError('Version file does not match GitHub release')
            subprocess.run([sys.executable, '-m', 'py_compile', str(source/'gugzi_kiosk/controller.py')], check=True)
            subprocess.run([sys.executable, '-m', 'py_compile', str(source/'gugzi_kiosk/updater.py')], check=True)

            destination = ROOT / 'releases' / version
            if destination.exists():
                raise RuntimeError('Version directory already exists: ' + str(destination))
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Dependencies first: failure leaves the previous release untouched.
            subprocess.run([str(ROOT/'venv/bin/pip'), 'install', '-r', str(source/'requirements.txt')], check=True, timeout=240)
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', '.git'))
            old_target = (ROOT / 'current').resolve(strict=True)
            temp_link = ROOT / 'current.new'
            if temp_link.is_symlink():
                temp_link.unlink()
            temp_link.symlink_to(destination)
            temp_link.replace(ROOT / 'current')
            moved = True
            # CLI and controller resolve through /opt/gugzi-kiosk/current.
            subprocess.run(['systemctl', 'restart', 'gugzi-kiosk.service'], check=True)
            time.sleep(6)
            subprocess.run(['systemctl', 'is-active', '--quiet', 'gugzi-kiosk.service'], check=True)
            status(installed=version, in_progress=False)
            print('Installed:', version)
    except Exception as exc:
        if moved and old_target is not None:
            tmp = ROOT / 'current.new'
            if tmp.is_symlink():
                tmp.unlink()
            tmp.symlink_to(old_target)
            tmp.replace(ROOT / 'current')
            subprocess.run(['systemctl', 'restart', 'gugzi-kiosk.service'], check=False)
        status(in_progress=False, error=exc)
        raise


if __name__ == '__main__':
    install()
