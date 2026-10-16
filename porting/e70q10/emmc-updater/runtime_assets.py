"""Verify source-owned updater runtime and immutable installed-layout metadata."""
import hashlib,pathlib

def verify_assets(directory):
 directory=pathlib.Path(directory)
 checks=directory/'SHA256SUMS'
 if not checks.is_file():raise SystemExit('Updater runtime assets missing: '+str(checks))
 required={'ram-kernel.bin','ram-header.bin','busybox-arm','countbytes-arm','countbytes-host','tables/mbr.sector0.bin'}
 required|={'tables/original-mbr.sector0.bin'}|{f'tables/ebr.sector{x}.bin' for x in [169984,2269184,2402304,14731264,15257600]}
 names=set()
 for line in checks.read_text().splitlines():
  expected,name=line.split('  ',1);p=pathlib.PurePosixPath(name)
  if p.is_absolute() or '..' in p.parts or name in names:raise SystemExit('Invalid asset path')
  names.add(name);path=directory/name
  if not path.is_file():raise SystemExit('Updater runtime asset missing: '+str(path))
  if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise SystemExit('Updater runtime asset changed: '+str(path))
 if not required<=names:raise SystemExit('Incomplete updater runtime asset manifest')
 for name in ['busybox-arm','countbytes-arm','countbytes-host']:
  if not (directory/name).stat().st_mode&0o111:raise SystemExit('Updater runtime asset must be executable: '+name)
