#!/usr/bin/env python3
from pathlib import Path,PureWindowsPath
import sys,types,tempfile,subprocess,json,os
from unittest.mock import patch
from package import validate,plan,stage,fields
import devices
OUT=Path(sys.argv[1]).resolve();report=validate(OUT.with_suffix('.tar'))
with tempfile.TemporaryDirectory() as td:
 w=Path(td);m=w/'sd';m.mkdir()
 selected=plan(report,'install-test','all');conf=fields(selected['metadata']['update.conf'])
 assert conf['userdata']==conf['partitioning']=='preserve' and conf['backup']=='required'
 assert conf['job']!=fields(plan(report,'install-test','all')['metadata']['update.conf'])['job']
 stage(report,selected,m,8,verify_mount=False)
 assert fields((m/'e70q10-update/update.conf').read_bytes())==conf
 control=(Path(__file__).parent/'ram-control.sh').read_text().replace('@MANIFEST@',report['manifest']);test=w/'parser.sh';test.write_text(control+'\nread_control "$1"\n')
 folder=w/'config';folder.mkdir();c=folder/'update.conf';valid=selected['metadata']['update.conf']
 for bad in [None,valid.replace(b'userdata=preserve',b'userdata=create'),valid.replace(b'partitioning=preserve',b'partitioning=create'),valid.replace(b'backup=required',b'backup=none'),valid.replace(b'cache=create',b'cache=preserve'),valid+b'job=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n']:
  c.write_bytes(valid if bad is None else bad);r=subprocess.run(['sh',str(test),str(folder)],capture_output=True);assert (r.returncode==0)==(bad is None)
 d={'id':'3','identity':'sd','serial':'serial','bytes':15931539456,'sector':512,'transport':'USB','system':False,'readonly':False}
 calls=[]
 def ps(code):calls.append(code);return '[0]' if 'Select-Object -ExpandProperty DiskNumber' in code else 'F'
 admin=types.SimpleNamespace(windll=types.SimpleNamespace(shell32=types.SimpleNamespace(IsUserAnAdmin=lambda:True)))
 with patch.object(devices,'os',types.SimpleNamespace(name='nt')),patch.object(devices,'Path',PureWindowsPath),patch.object(devices,'ctypes',admin),patch.object(devices,'windows_volume_root',return_value='C:\\'),patch.object(devices,'checked_disk',return_value=d),patch.object(devices,'ps',side_effect=ps),patch.object(devices,'check_mount'):
  devices.format_disk('3',devices.fingerprint(d),'C:\\한글경로\\image.tar')
 assert 'Get-CimInstance Win32_PageFileUsage' in calls[-1] and 'Initialize-Disk -PartitionStyle MBR' in calls[-1] and '-MbrType FAT32' in calls[-1]
 assert calls[-1].index("throw 'pagefile disk'")<calls[-1].index('Clear-Disk')
 calls=[]
 with patch.object(devices,'os',types.SimpleNamespace(name='nt')),patch.object(devices,'Path',PureWindowsPath),patch.object(devices,'ctypes',admin),patch.object(devices,'windows_volume_root',return_value='E:\\'),patch.object(devices,'checked_disk',return_value=d),patch.object(devices,'ps',side_effect=lambda code:(calls.append(code) or '[3]')):
  try:devices.format_disk('3',devices.fingerprint(d),'E:\\image.tar')
  except ValueError:pass
  else:raise AssertionError('archive-on-target not rejected')
 assert not any('Clear-Disk' in code for code in calls)
 result={'SD_copy_readback':'passed on temporary folder','schema4_preservation_policy':'passed','fresh_job':'unique for every preparation','Windows_format':'mocked success, pagefile/identity recheck, archive-on-target refusal, FAT32 MBR and UTF8 path transport','Windows_physical_run':'not available on Linux'}
 logs=Path('/home/juwon/ridi/.orchestrator/logs/emmc-windows-20261012');(logs/'windows-logic-validation.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS: SD stage/readback + strict preserving policy + Windows storage adapter contract')
