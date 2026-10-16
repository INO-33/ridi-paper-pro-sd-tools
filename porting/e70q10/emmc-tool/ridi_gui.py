#!/usr/bin/env python3
"""Python/Tk SD preparation app. Desktop logic is shared with Windows/Linux."""
from pathlib import Path
import sys,os,json,ctypes,queue,threading,datetime,argparse,subprocess,contextlib
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import gui_backend as backend

PHASES={'validate-backup':'복원 백업 전체 검증','boot-prepare':'부트 이미지 준비','convert-system':'시스템 이미지 준비','convert-vendor':'벤더 이미지 준비','convert-boot':'부트 이미지 준비','validate':'PC 이미지 검증','format':'SD 포맷','mount':'SD 연결 확인','copy':'SD 파일 복사','flush':'SD 저장 완료 대기','verify':'SD 읽기 검증'}
INFO={'restore':'선택한 백업 시점으로 OS·파티션·사용자 데이터를 모두 되돌립니다.\n같은 기기의 백업만 허용하며 SD는 포맷하지 않습니다.', 'install':'Android 4.4 → 8 · 파티션을 구성하고 OS를 설치합니다.\n기기의 기존 사용자 데이터는 초기화됩니다.',
      'update':'이미 Android 8인 기기의 선택한 파티션을 업데이트합니다.\n각 파티션의 전체 이미지를 기록하며 userdata·misc·cache를 보존합니다.',
}

class LogSink:
 def __init__(self,events):self.events=events;self.buffer=''
 def write(self,s):
  self.buffer+=s
  while '\n' in self.buffer:
   line,self.buffer=self.buffer.split('\n',1)
   if line:self.events.put(('log',line))
  return len(s)
 def flush(self):pass

class App:
 def __init__(self,root,runtime=None,cache=None):
  self.root=root;self.events=queue.Queue();self.busy=False;self.prepared=None;self.disks={};self.last_phase='';self.closed=False
  appdir=(Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent);self.runtime=Path(runtime or appdir/'runtime.zip')
  self.cache=Path(cache or (Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'RidiPaperPro'))
  self.cache.mkdir(parents=True,exist_ok=True);self.logfile=self.cache/('gui-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
  root.title('RIDI Paper Pro · Android 8 SD 도구');root.geometry('860x760');root.minsize(820,680);root.configure(bg='#f4f6fa')
  style=ttk.Style(root);style.theme_use('clam');font=('Malgun Gothic' if os.name=='nt' else 'Noto Sans CJK KR',10)
  style.configure('.',font=font);style.configure('TFrame',background='#f4f6fa');style.configure('TLabel',background='#f4f6fa',foreground='#25324a')
  style.configure('TLabelframe',background='#f4f6fa');style.configure('TLabelframe.Label',background='#f4f6fa',foreground='#25324a',font=(font[0],11,'bold'))
  style.configure('TButton',padding=(12,7));style.configure('Primary.TButton',background='#2459bf',foreground='white');style.map('Primary.TButton',background=[('active','#18479e'),('disabled','#a8b9d8')])
  style.configure('TCheckbutton',background='#f4f6fa');style.configure('TRadiobutton',background='#f4f6fa');style.configure('TProgressbar',background='#2459bf')
  header=tk.Frame(root,bg='#182c4a',height=84);header.pack(fill='x');header.pack_propagate(False)
  tk.Label(header,text='RIDI PAPER PRO',bg='#182c4a',fg='#a8c5f8',font=(font[0],10,'bold')).pack(anchor='w',padx=24,pady=(12,0))
  tk.Label(header,text='Android 8 · SD 준비 도구',bg='#182c4a',fg='white',font=(font[0],19,'bold')).pack(anchor='w',padx=24)
  footer=ttk.Frame(root,padding=(22,8,22,14));footer.pack(side='bottom',fill='x')
  holder=ttk.Frame(root);holder.pack(fill='both',expand=True)
  canvas=tk.Canvas(holder,bg='#f4f6fa',highlightthickness=0);scroll=ttk.Scrollbar(holder,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=scroll.set)
  scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
  body=ttk.Frame(canvas,padding=(22,14));item=canvas.create_window(0,0,window=body,anchor='nw')
  body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
  canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
  def wheel(e):
   canvas.yview_scroll(-1 if getattr(e,'num',0)==4 else 1 if getattr(e,'num',0)==5 else int(-e.delta/120),'units');return 'break'
  root.bind('<MouseWheel>',wheel);root.bind('<Button-4>',wheel);root.bind('<Button-5>',wheel)
  self._log_view=None
  self.folder=tk.StringVar(value=str(appdir/'images'));self.mode=tk.StringVar(value='update');self.backup_before=tk.BooleanVar(value=False);self.backup_defaults={'install':True,'update':False,'restore':False};self.previous_mode='update';self.update_roles=None;self.card=tk.StringVar();self.format_sd=tk.BooleanVar(value=True);self.roles={r:tk.BooleanVar(value=True) for r in ('boot','system','vendor')};self.tools=tk.StringVar(value=str(appdir/'platform-tools'));self.serial=tk.StringVar()
  inputs=ttk.LabelFrame(body,text='1  이미지 또는 복원할 백업 폴더',padding=12);inputs.pack(fill='x',pady=(0,10))
  self.folder_entry=ttk.Entry(inputs,textvariable=self.folder);self.folder_entry.pack(side='left',fill='x',expand=True)
  self.browse_btn=ttk.Button(inputs,text='폴더 선택',command=self.browse);self.browse_btn.pack(side='left',padx=(8,0))
  options=ttk.LabelFrame(body,text='2  작업 선택',padding=(12,8));options.pack(fill='x',pady=(0,10));self.radios=[]
  for value,label in [('install','Android 8 업그레이드'),('update','증분 업데이트'),('restore','백업으로 롤백')]:
   radio=ttk.Radiobutton(options,text=label,variable=self.mode,value=value,command=self.changed_mode);radio.pack(anchor='w',pady=2);self.radios.append(radio)
  self.mode_info=ttk.Label(options,text=INFO['update'],wraplength=770,foreground='#536078');self.mode_info.pack(anchor='w',pady=(5,7))
  checks=ttk.Frame(options);checks.pack(anchor='w');ttk.Label(checks,text='업데이트 대상:').pack(side='left',padx=(0,14));self.checks=[]
  for r in ('boot','system','vendor'):
   c=ttk.Checkbutton(checks,text=r,variable=self.roles[r],command=self.invalidate);c.pack(side='left',padx=(0,18));self.checks.append(c)
  self.backup_check=ttk.Checkbutton(options,text='기록 전에 eMMC 전체 백업 (boot0/boot1 포함)',variable=self.backup_before,command=self.invalidate);self.backup_check.pack(anchor='w',pady=(9,0))
  ttk.Label(options,text='선택하면 백업과 SD 읽기 검증이 끝난 뒤 OS를 기록합니다.',foreground='#68738a').pack(anchor='w')
  disk=ttk.LabelFrame(body,text='3  SD카드 · 16GB 이상',padding=12);disk.pack(fill='x',pady=(0,10));row=ttk.Frame(disk);row.pack(fill='x')
  self.cards=ttk.Combobox(row,textvariable=self.card,state='readonly');self.cards.pack(side='left',fill='x',expand=True)
  self.scan_btn=ttk.Button(row,text='새로고침',command=self.scan);self.scan_btn.pack(side='left',padx=(8,0))
  self.format_check=ttk.Checkbutton(disk,text='SD를 FAT32로 포맷하고 준비 (SD의 기존 내용 삭제)',variable=self.format_sd,command=self.invalidate);self.format_check.pack(anchor='w',pady=(8,0))
  ttk.Label(disk,text='포맷을 끄면 기존 FAT32 SD의 백업 폴더를 유지합니다.',foreground='#68738a').pack(anchor='w')
  progress_frame=ttk.Frame(footer);progress_frame.pack(fill='x',pady=(3,8));self.status_text=tk.StringVar(value='이미지 폴더와 SD카드를 선택하세요.');ttk.Label(progress_frame,textvariable=self.status_text,wraplength=790).pack(anchor='w')
  self.bar=ttk.Progressbar(progress_frame,mode='determinate',maximum=100);self.bar.pack(fill='x',pady=(7,0))
  self.details=tk.Text(body,height=4,wrap='word',bg='white',fg='#526079',font=(font[0],9),relief='flat',state='disabled')
  actions=ttk.Frame(footer);actions.pack(fill='x');self.prepare_btn=ttk.Button(actions,text='SD카드 준비',style='Primary.TButton',command=self.prepare);self.prepare_btn.pack(side='left')
  self.boot_btn=ttk.Button(actions,text='준비한 SD 작업 실행 · RAM 부팅',command=self.boot,state='disabled');self.boot_btn.pack(side='left',padx=8)
  self.result_btn=ttk.Button(actions,text='SD 결과 확인',command=self.result);self.result_btn.pack(side='right');ttk.Button(actions,text='상세 로그',command=self.show_log).pack(side='right',padx=8)
  self.next_text=tk.StringVar(value='SD 준비 후: 안전 제거 → 기기에 삽입 → USB 연결 → fastboot 진입');ttk.Label(footer,textvariable=self.next_text,wraplength=790,foreground='#68738a').pack(anchor='w',pady=(9,0))
  self.controls=[self.folder_entry,self.browse_btn,self.cards,self.scan_btn,self.format_check,self.backup_check,*self.radios,*self.checks,self.prepare_btn,self.result_btn]
  self.folder.trace_add('write',lambda *a:self.invalidate());self.cards.bind('<<ComboboxSelected>>',lambda e:self.invalidate())
  root.protocol('WM_DELETE_WINDOW',self.close);root.after(100,self.poll);root.after(150,self.scan)
 def invalidate(self):
  if not self.busy:self.prepared=None;self.boot_btn.configure(state='disabled')
 def changed_mode(self):
  self.invalidate();mode=self.mode.get();old=self.previous_mode
  self.backup_defaults[old]=self.backup_before.get();self.backup_before.set(self.backup_defaults[mode])
  if old=='update' and mode=='install':
   self.update_roles={r:v.get() for r,v in self.roles.items()}
   for v in self.roles.values():v.set(True)
  elif old=='install' and mode=='update' and self.update_roles:
   for r,v in self.roles.items():v.set(self.update_roles[r])
  if mode=='restore':
   self.saved_format=self.format_sd.get();self.format_sd.set(False);self.backup_before.set(False)
  elif old=='restore':self.format_sd.set(getattr(self,'saved_format',False))
  self.backup_check.configure(state='disabled' if mode=='restore' else 'normal');self.format_check.configure(state='disabled' if mode=='restore' else 'normal')
  self.previous_mode=mode;self.mode_info.configure(text=INFO[mode])
  for c in self.checks:c.configure(state='normal' if mode=='update' else 'disabled')
 def browse(self):
  folder=filedialog.askdirectory(parent=self.root,title='백업의 작업ID 폴더 (device.txt가 있는 곳)' if self.mode.get()=='restore' else 'boot.img / system.img / vendor.img가 있는 폴더',initialdir=self.folder.get())
  if folder:self.folder.set(folder)
 def show_log(self):
  if self._log_view is not None and self._log_view.winfo_exists():self._log_view.winfo_toplevel().lift();return
  win=tk.Toplevel(self.root);win.title('SD 작업 로그');win.geometry('780x420');text=tk.Text(win,wrap='word',font=('TkDefaultFont',10));text.pack(fill='both',expand=True);self._log_view=text
  if self.logfile.exists():text.insert('end',self.logfile.read_text(encoding='utf-8'))
  text.configure(state='disabled');text.see('end')
 def append_log(self,line):
  with self.logfile.open('a',encoding='utf-8') as f:f.write(line+'\n')
  self.details.configure(state='normal');self.details.insert('end',line+'\n');self.details.see('end');self.details.configure(state='disabled')
  if self._log_view is not None and self._log_view.winfo_exists():
   self._log_view.configure(state='normal');self._log_view.insert('end',line+'\n');self._log_view.see('end');self._log_view.configure(state='disabled')
 def set_busy(self,value):
  self.busy=value
  for c in self.controls:c.configure(state='disabled' if value else 'normal')
  if not value:self.cards.configure(state='readonly');self.changed_mode_restore()
  self.boot_btn.configure(state='normal' if not value and self.prepared else 'disabled')
 def changed_mode_restore(self):
  for c in (self.backup_check,self.format_check):c.configure(state='disabled' if self.mode.get()=='restore' else 'normal')
  for c in self.checks:c.configure(state='normal' if self.mode.get()=='update' else 'disabled')
 def job(self,kind,fn):
  if self.busy:return
  self.set_busy(True);self.bar.configure(mode='indeterminate');self.bar.start(12)
  def run():
   try:
    with contextlib.redirect_stdout(LogSink(self.events)):
     result=fn()
    self.events.put(('done',(kind,result)))
   except backend.Cancelled as e:self.events.put(('cancelled',str(e)))
   except Exception as e:self.events.put(('error',str(e)))
  threading.Thread(target=run,daemon=False).start()
 def scan(self):self.status_text.set('SD카드 검색 중…');self.job('scan',backend.candidates)
 def consent(self,summary):
  event=threading.Event();answer=[];self.events.put(('confirm',(summary,event,answer)));event.wait();return answer[0]
 def progress(self,phase,done,total):self.events.put(('progress',(phase,done,total)))
 def prepare(self):
  if not self.card.get() or self.card.get() not in self.disks:messagebox.showerror('SD 선택','SD카드를 선택하세요.',parent=self.root);return
  mode=self.mode.get();selected=tuple(r for r in ('system','vendor','boot') if mode=='install' or (mode=='update' and self.roles[r].get()))
  req=backend.Request(Path(self.folder.get()),self.runtime,self.disks[self.card.get()]['id'],mode,selected,self.format_sd.get(),backup_before=self.backup_before.get())
  self.prepared=None;self.status_text.set('이미지와 SD 작업을 준비하고 있습니다…');self.last_phase=''
  self.job('prepare',lambda:backend.prepare(req,self.cache,self.consent,self.progress))
 def boot(self):
  if not self.prepared:return
  state=self.prepared
  tools=Path(self.tools.get())
  if not (tools/('fastboot.exe' if os.name=='nt' else 'fastboot')).is_file():tools=None
  try:backend.platform_tool('fastboot',tools)
  except ValueError:
   folder=filedialog.askdirectory(parent=self.root,title='fastboot가 있는 Android platform-tools 폴더 선택')
   if not folder:return
   self.tools.set(folder)
  self.status_text.set('fastboot 연결을 확인하고 RAM 이미지를 전송합니다…')
  def run():
   tools=Path(self.tools.get())
   if not (tools/('fastboot.exe' if os.name=='nt' else 'fastboot')).is_file():tools=None
   exe=backend.platform_tool('fastboot',tools);ids=backend.connected(exe)
   if not ids:raise ValueError('fastboot 기기가 없습니다. SD 삽입과 USB 연결·fastboot 진입을 확인하세요.')
   serial=None
   if len(ids)>1:
    event=threading.Event();answer=[];self.events.put(('serial',(ids,event,answer)));event.wait();serial=answer[0]
    if not serial:raise backend.Cancelled('기기 선택을 취소했습니다')
   return backend.boot(state,tools,serial)
  self.job('boot',run)
 def result(self):
  if self.card.get() not in self.disks:messagebox.showerror('SD 연결','SD를 PC에 연결하고 새로고침하세요.',parent=self.root);return
  disk=self.disks[self.card.get()]['id'];self.job('result',lambda:backend.status(backend.mounted_volume(backend.devices.checked_disk(disk))))
 def poll(self):
  try:
   while True:
    kind,value=self.events.get_nowait()
    if kind=='log':self.append_log(value)
    elif kind=='progress':
     phase,done,total=value;label=PHASES.get(phase,phase)
     if phase!=self.last_phase:self.append_log(label);self.last_phase=phase
     if total:
      self.bar.stop();self.bar.configure(mode='determinate');pct=min(100,done/total*100);self.bar['value']=pct;self.status_text.set(f'{label} · {pct:.0f}%')
     else:self.bar.configure(mode='indeterminate');self.bar.start(12);self.status_text.set(label+'…')
    elif kind=='confirm':
     s,event,answer=value;d=s['disk'];target=' / '.join(s['targets']) or '백업 전용';erase='SD의 모든 파티션과 데이터가 삭제됩니다.' if s['format'] else '기존 FAT32 SD의 업데이트 폴더를 교체합니다. 백업 폴더는 유지합니다.'
     body=f'{d["id"]} · {d["name"]} · {d["bytes"]/1e9:.1f}GB\n\n{erase}\n\n작업: {backend.LABELS[s["operation"]]}\n대상: {target}\n'
     if s['operation']=='install':body+='\n기기에서는 기존 userdata를 초기화하고 Android 8을 설치합니다.\n'
     elif s['operation']=='restore':body+='\n현재 OS·앱·책·설정 등 모든 사용자 데이터와 파티션 표가 백업 시점으로 덮어써집니다.\n대상 기기 CID: '+s['restore_cid']+'\n실기기 복원 검증 전인 기능입니다.\n'
     else:body+='\n기기의 userdata·misc·cache·파티션 표는 보존합니다.\n'
     if s['operation']!='restore':body+='\neMMC 전체 백업: '+('실행 후 OS 기록' if s['backup']=='required' else '생략')+'\n'
     body+='\n이 SD와 작업으로 진행할까요?';answer.append(messagebox.askyesno('SD 작업 확인',body,parent=self.root,default='no'));event.set()
    elif kind=='serial':
     ids,event,answer=value;dialog=tk.Toplevel(self.root);dialog.title('fastboot 기기 선택');dialog.transient(self.root);dialog.grab_set();v=tk.StringVar(value=ids[0]);ttk.Label(dialog,text='작업할 기기를 선택하세요').pack(padx=20,pady=10);ttk.Combobox(dialog,textvariable=v,values=ids,state='readonly').pack(padx=20)
     def choose():answer.append(v.get());event.set();dialog.destroy()
     def cancel():answer.append(None);event.set();dialog.destroy()
     ttk.Button(dialog,text='선택',command=choose).pack(pady=12);dialog.protocol('WM_DELETE_WINDOW',cancel)
    elif kind in ('error','cancelled'):
     self.bar.stop();self.bar.configure(mode='determinate');self.bar['value']=0;self.set_busy(False);self.status_text.set(value);self.append_log(value)
     if kind=='error':messagebox.showerror('작업 중단',value,parent=self.root)
    elif kind=='done':
     job,result=value;self.bar.stop();self.bar.configure(mode='determinate');self.bar['value']=100
     if job=='scan':
      old=self.card.get();self.disks={f'{d["id"]} · {d["name"] or "SD카드"} · {d["bytes"]/1e9:.1f}GB':d for d in result};self.cards['values']=list(self.disks)
      self.card.set(old if old in self.disks else next(iter(self.disks)) if len(self.disks)==1 else '')
      self.status_text.set('이미지 폴더와 작업을 선택하고 SD카드를 준비하세요.' if result else 'SD를 PC 카드리더에 연결한 뒤 새로고침하세요.');self.bar['value']=0
     elif job=='prepare':
      self.prepared=result;self.status_text.set('SD 준비 완료 · 파일 복사와 읽기 검증을 통과했습니다.');self.next_text.set('SD 안전 제거 → Paper Pro에 삽입 → USB 연결·fastboot 진입 → 준비한 SD 작업 실행');self.append_log('RAM 이미지: '+result['ram'])
     elif job=='boot':self.status_text.set('RAM 부팅 전송 완료 · 기기 화면에서 진행 상황을 확인하세요.');self.append_log(result.strip());self.next_text.set('실제 작업 완료 여부는 기기 화면 또는 SD 결과 확인으로 확인합니다.')
     elif job=='result':
      success=result.get('exit')=='0';self.status_text.set('기기 작업 성공' if success else '기기 작업 실패 또는 진행 중');self.append_log(json.dumps(result,ensure_ascii=False));messagebox.showinfo('SD 작업 결과',('성공' if success else '실패/미완료')+'\n작업: '+result.get('operation','')+'\n대상: '+result.get('targets',''),parent=self.root)
     self.set_busy(False)
  except queue.Empty:pass
  if not self.closed:self.root.after(100,self.poll)
 def close(self):
  if self.busy:self.root.bell();self.status_text.set('진행 중인 작업이 끝난 뒤 창을 닫아주세요.');return
  self.closed=True;self.root.destroy()

def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path);p.add_argument('--cache',type=Path);a=p.parse_args()
 if os.name=='nt' and not ctypes.windll.shell32.IsUserAnAdmin():
  shell=ctypes.windll.shell32;shell.ShellExecuteW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int];shell.ShellExecuteW.restype=ctypes.c_void_p
  args=subprocess.list2cmdline(sys.argv[1:] if getattr(sys,'frozen',False) else [str(Path(__file__).resolve()),*sys.argv[1:]])
  gui_python=Path(sys.executable).with_name('pythonw.exe');executable=sys.executable if getattr(sys,'frozen',False) else (str(gui_python) if gui_python.is_file() else sys.executable)
  result=shell.ShellExecuteW(None,'runas',executable,args,str(Path(__file__).resolve().parent),1)
  if result and result>32:return
  root=tk.Tk();root.withdraw();messagebox.showerror('관리자 권한','SD 준비에는 관리자 권한이 필요합니다. 실행 권한을 허용하고 다시 시작하세요.');root.destroy();return
 root=tk.Tk();App(root,a.runtime,a.cache);root.mainloop()
if __name__=='__main__':main()
