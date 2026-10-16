#!/usr/bin/env python3
"""Run on Windows with Python 3.10+: build the portable Windows distribution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

NAME = 'PaperProSD'

def run(args):
    subprocess.run([str(a) for a in args], check=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app-dir', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--platform-tools', type=Path, help='Windows platform-tools directory')
    p.add_argument('--without-fastboot', action='store_true', help='Build without bundled fastboot; users select it later')
    p.add_argument('--images', type=Path, help='Optionally bundle boot.img/system.img/vendor.img')
    p.add_argument('--output', type=Path, help='New output directory; existing directories are refused')
    a = p.parse_args()
    if os.name != 'nt':
        p.error('Run this script on Windows. Linux cannot produce this Windows executable.')
    if sys.version_info < (3, 10):
        p.error('Python 3.10 or newer is required.')
    app = a.app_dir.resolve()
    if not (app/'runtime.zip').is_file():
        p.error('runtime.zip missing: use --app-dir with the extracted GUI bundle directory.')
    sys.path.insert(0, str(app))
    from folder_package import runtime_seed
    runtime_seed(app/'runtime.zip')  # Validate before downloading dependencies/building.
    for n in ('ridi_gui.py', 'gui_backend.py', 'GUI_README.md', 'licenses', 'rollback.py', 'ram-restore.sh'):
        if not (app/n).exists():
            p.error('Missing application file: '+n)
    tools = (a.platform_tools or app/'platform-tools').resolve()
    tool_names = ('fastboot.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll')
    if not a.without_fastboot:
        for n in tool_names:
            if not (tools/n).is_file():
                p.error('Missing '+str(tools/n)+'; supply --platform-tools or explicitly --without-fastboot.')
        if (tools/'fastboot.exe').read_bytes()[:2] != b'MZ':
            p.error('fastboot.exe must be a Windows binary.')
    if a.images:
        for n in ('boot.img', 'system.img', 'vendor.img'):
            if not (a.images/n).is_file():
                p.error('Missing OS image: '+n)
    output = (a.output or app/'windows-release').resolve()
    if output.exists():
        p.error('Output already exists. Select a new --output directory: '+str(output))
    venv = app/'.venv-pyinstaller'
    python = venv/'Scripts/python.exe'
    if not python.exists():
        run([sys.executable, '-m', 'venv', venv])
    run([python, '-m', 'pip', 'install', 'PyInstaller==6.22.3'])
    run([python, '-c', 'import tkinter; import struct; assert struct.calcsize("P")==8, "Use 64-bit Python"'])
    # Build in a temporary directory; large intermediates are removed on success/failure.
    with tempfile.TemporaryDirectory(prefix='paperpro-windows-') as td:
        work = Path(td)
        run([python, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
             '--windowed', '--uac-admin', '--noupx', '--name', NAME,
             '--paths', app, '--add-data', str(app/'ram-restore.sh')+';.', '--distpath', work/'dist', '--workpath', work/'work',
             '--specpath', work, app/'ridi_gui.py'])
        release = work/'dist'/NAME
        for n in ('runtime.zip', 'runtime.zip.sha256', 'GUI_README.md', 'ROLLBACK.md'):
            shutil.copy2(app/n, release/n)
        shutil.copytree(app/'licenses', release/'licenses')
        (release/'images').mkdir()
        if a.images:
            for n in ('boot.img', 'system.img', 'vendor.img'):
                shutil.copy2(a.images/n, release/'images'/n)
        else:
            (release/'images/README.txt').write_text('Put boot.img, system.img, vendor.img here, or select an image folder in the app.\n', encoding='utf-8')
        (release/'platform-tools').mkdir()
        if not a.without_fastboot:
            for n in tool_names:
                shutil.copy2(tools/n, release/'platform-tools'/n)
            if (tools/'NOTICE.txt').is_file():
                shutil.copy2(tools/'NOTICE.txt', release/'platform-tools/NOTICE.txt')
        (release/'BUILD.json').write_text(json.dumps({'python':sys.version, 'pyinstaller':'6.22.3', 'backup':'optional checkbox', 'fastboot_bundled':not a.without_fastboot, 'images_bundled':bool(a.images)}, indent=2), encoding='utf-8')
        output.mkdir(parents=True)
        shutil.copytree(release, output/NAME)
        archive = output/(NAME+'-windows-x64.zip')
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for f in sorted((output/NAME).rglob('*')):
                if f.is_file():
                    z.write(f, f.relative_to(output))
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
        digest=hashlib.sha256()
        with archive.open('rb') as stream:
            for chunk in iter(lambda:stream.read(4<<20), b''):digest.update(chunk)
        h=digest.hexdigest()
        Path(str(archive)+'.sha256').write_text(h+'  '+archive.name+'\n', encoding='ascii')
    print('READY:', output/NAME/(NAME+'.exe'))
    print('DISTRIBUTE:', archive)

if __name__ == '__main__':
    main()
