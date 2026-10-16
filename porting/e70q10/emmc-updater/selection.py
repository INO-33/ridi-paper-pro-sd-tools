"""Shared fixed partition selection and plain-data SD control schema."""
import argparse,hashlib,re
ORDER=('system','vendor','boot')
RANGES={'system':('system.raw.gz',172032,2097152),'vendor':('vendor.raw.gz',14733312,524288),'boot':('boot.raw.gz',104448,65536)}
def targets(value):
 parts=list(ORDER) if value=='all' else value.split(',')
 if not parts or len(set(parts))!=len(parts) or any(p not in ORDER for p in parts):raise ValueError('targets must be boot, system, vendor, or a comma-separated combination')
 return tuple(p for p in ORDER if p in parts)
def roles(rows):
 result=[]
 for row in rows:
  if len(row)!=5:raise ValueError('Bad payload manifest')
  found=[name for name in ORDER if row[:3]==list(map(str,RANGES[name]))]
  if len(found)!=1 or not re.fullmatch('[0-9a-f]{64}',row[3]) or not re.fullmatch('[0-9a-f]{64}',row[4]):raise ValueError('Bad fixed partition manifest')
  result.extend(found)
 if not result or tuple(result)!=tuple(p for p in ORDER if p in result) or len(result)!=len(set(result)):raise ValueError('Duplicate, unordered or empty manifest')
 return tuple(result)
def control(manifest,selected,automatic=True,reboot=True):
 return f'format=1\nmanifest={manifest}\ntargets={",".join(selected)}\nautostart={int(automatic)}\nreboot={int(reboot)}\n'.encode()
def parse_control(data,manifest,available):
 fields={}
 for line in data.decode('ascii').splitlines():
  key,sep,value=line.partition('=')
  if not sep or key in fields:raise ValueError('Malformed/duplicate update.conf key')
  fields[key]=value
 if set(fields)!={'format','manifest','targets','autostart','reboot'} or fields['format']!='1' or fields['manifest']!=manifest or fields['autostart'] not in ('0','1') or fields['reboot'] not in ('0','1'):raise ValueError('Invalid update.conf')
 selected=targets(fields['targets'])
 if ','.join(selected)!=fields['targets'] or not set(selected)<=set(available):raise ValueError('Selected targets absent from package')
 return selected,fields['autostart']=='1',fields['reboot']=='1'
def sd_options(args):
 parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--targets');parser.add_argument('--manual',action='store_true');parser.add_argument('--no-reboot',action='store_true')
 return parser.parse_args(args)
def sd_plan(report,options):
 available=roles(report['manifest']);selected=targets(options.targets) if options.targets else tuple(report['targets'])
 if not set(selected)<=set(available):raise ValueError('Selected target is absent from package')
 automatic=report['automatic'] and not options.manual;reboot=report['automatic_reboot'] and not options.no_reboot
 config=control(report['manifest_sha256'],selected,automatic,reboot)
 skipped={RANGES[p][0] for p in ORDER if p not in selected}
 if 'boot' not in selected:skipped.add('boot-emmc.img')
 names=set(report['files'])-skipped
 checks={name:report['checksums'][name] for name in names if name!='SHA256SUMS'}
 checks['update.conf']=hashlib.sha256(config).hexdigest()
 checksum_data=''.join(checks[n]+'  '+n+'\n' for n in sorted(checks)).encode()
 checks['SHA256SUMS']=hashlib.sha256(checksum_data).hexdigest()
 metadata={'update.conf':config,'SHA256SUMS':checksum_data}
 size=sum(report['sizes'][n] for n in names if n not in metadata)+sum(map(len,metadata.values()))
 return {'targets':selected,'control':config,'names':names,'automatic':automatic,'reboot':reboot,'checksums':checks,'metadata':metadata,'file_bytes':size,'required_bytes':size+(64<<20)}
