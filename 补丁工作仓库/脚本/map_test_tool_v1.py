"""Independent map-test controller: stdlib UI, bounded mailbox writes, no injected threads/input hooks."""
import argparse,csv,ctypes,hashlib,json,math,struct,subprocess,time,zipfile,sys
from ctypes import wintypes as wt
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog,filedialog
from probe_map_position_readonly_v1 import Module,ROOT,WORK
from map_test_catalog_rules_v1 import testable,display_name,NON_MAP_SCENES
from newpal_processes_v1 import game_pids

DATA=WORK/'地图开发/地图测试工具'
BRIDGE=WORK/'候选版本/map-test-v1'
FROZEN=bool(getattr(sys,'frozen',False))
LOG_DATA=DATA
if FROZEN:
 WORK=Path(sys._MEIPASS)/'work'
 DATA=WORK/'地图开发/地图测试工具'
 BRIDGE=WORK/'候选版本/map-test-v1'
 LOG_DATA=Path(sys.executable).resolve().parent
 ROOT=next((p for p in LOG_DATA.parents if (p/'NewPAL_Release.exe').is_file()),LOG_DATA)

def game_root():
 """Portable builds find the game beside/above the EXE, or ask once on connect."""
 global ROOT
 if (ROOT/'NewPAL_Release.exe').is_file():return ROOT
 config=LOG_DATA/'传送器配置.json'
 if FROZEN and config.exists():
  saved=Path(json.loads(config.read_text(encoding='utf-8'))['game_directory'])
  if (saved/'NewPAL_Release.exe').is_file():ROOT=saved;return ROOT
 if FROZEN:
  selected=filedialog.askopenfilename(title='选择已安装地图测试运行桥的游戏EXE',filetypes=[('新仙剑游戏','NewPAL_Release.exe')])
  if selected and Path(selected).name.casefold()=='newpal_release.exe':
   ROOT=Path(selected).resolve().parent
   config.write_text(json.dumps({'game_directory':str(ROOT)},ensure_ascii=False,indent=2),encoding='utf-8')
   return ROOT
 raise RuntimeError('未找到游戏EXE，请将传送器放在游戏目录内，或连接时选择游戏EXE')
BLOCK=0x60800000
RESULTS={1:'瞬移完成',2:'当前处于战斗/剧情/菜单/切图，未执行',3:'地图未收录',4:'坐标越界',5:'测试已停止或连接已过期',6:'原生加载未返回目标地图',10:'正在加载'}

def compatibility_rules():
 return json.loads((DATA/'传送接口兼容规则.json').read_text(encoding='utf-8'))

class Catalog:
 def __init__(self):
  self.data=json.loads((DATA/'可定位地图.json').read_text(encoding='utf-8-sig'));self.rows=[r for r in self.data['scenes'] if testable(r['scene_id'])]
  for r in self.rows:r['name']=display_name(r['scene_id'],r['resource_id'],r.get('native_name',r['name']))
  self.data['scenes']=self.rows;self.data['scene_count']=len(self.rows);self.byid={r['scene_id']:r for r in self.rows};self.cache={}
 def grid(self,row):
  rid=row['resource_id']
  if rid not in self.cache:
   with zipfile.ZipFile(DATA/'原生格数据.zip') as z:raw=z.read(f'{rid}.bin')
   if len(raw)!=row['grid_bytes'] or hashlib.sha256(raw).hexdigest()!=row['grid_sha256']:raise ValueError('原生格数据校验失败')
   self.cache[rid]=struct.unpack('<%dI'%(len(raw)//4),raw)
  return self.cache[rid]
 def landing(self,id,x,y,snap=True,limit=8):
  row=self.byid[id];w,h=row['width'],row['height']
  if not(0<=x<w and 0<=y<h):raise ValueError(f'坐标应在 0..{w-1} / 0..{h-1} 格内')
  grid=self.grid(row)
  def valid(i):return not(grid[i]&BLOCK) and bool(grid[i]&0xf000) and not(grid[i]&255)
  if not snap:
   flag=grid[y*w+x]
   if flag&BLOCK or flag&255:raise ValueError('该格是墙体/特殊区或触发区，请选择附近道路')
   return x,y
  if valid(y*w+x):return x,y
  candidates=((i%w,i//w) for i in range(w*h) if valid(i))
  point=min(candidates,key=lambda p:(p[0]-x)**2+(p[1]-y)**2,default=None)
  if point is None:raise ValueError('本图没有可确认的候选道路格，可取消吸附后手选非墙格')
  if limit is not None and math.dist(point,(x,y))>limit:raise ValueError('附近8格内没有候选道路，请直接点击可见通路')
  return point

class Game:
 def __init__(self):
  game_root()
  self.k=ctypes.WinDLL('kernel32',use_last_error=True);k=self.k
  definitions={
   'OpenProcess':([wt.DWORD,wt.BOOL,wt.DWORD],wt.HANDLE),'CloseHandle':([wt.HANDLE],wt.BOOL),
   'CreateToolhelp32Snapshot':([wt.DWORD,wt.DWORD],wt.HANDLE),
   'Module32FirstW':([wt.HANDLE,ctypes.POINTER(Module)],wt.BOOL),'Module32NextW':([wt.HANDLE,ctypes.POINTER(Module)],wt.BOOL),
   'ReadProcessMemory':([wt.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)],wt.BOOL),
   'WriteProcessMemory':([wt.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)],wt.BOOL)}
  for name,(args,ret) in definitions.items():getattr(k,name).argtypes=args;getattr(k,name).restype=ret
  ids=game_pids()
  if len(ids)!=1:raise RuntimeError('请先从Steam启动受支持的原版或补丁版游戏，读档进入可走动地图；仅保留一个游戏进程')
  self.pid=ids[0];self.base=None;self.handle=None
  self.runtime_address=None
  from map_test_compat_v2 import select_contract,validate_runtime
  contract=select_contract((ROOT/'NewPAL_Release.exe').read_bytes(),compatibility_rules())
  integrated=contract['kind']=='integrated';profile=contract.get('profile')
  self.state=contract.get('state',{})
  self.compatibility=contract['label']
  snap=k.CreateToolhelp32Snapshot(0x18,self.pid)
  if snap in (None,ctypes.c_void_p(-1).value):raise ctypes.WinError(ctypes.get_last_error())
  try:
   m=Module();m.dwSize=ctypes.sizeof(m);ok=k.Module32FirstW(snap,ctypes.byref(m))
   while ok:
    if m.szModule.lower()=='newpal_release.exe':
     if Path(m.szExePath).resolve()!= (ROOT/'NewPAL_Release.exe').resolve():raise RuntimeError('运行中的游戏不属于当前项目目录')
     self.base=m.modBaseAddr;break
    ok=k.Module32NextW(snap,ctypes.byref(m))
  finally:k.CloseHandle(snap)
  if not self.base:raise RuntimeError('未找到游戏主模块')
  self.handle=k.OpenProcess(0x1038,False,self.pid)
  if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
  try:
   validate_runtime(lambda rva,n:self.read(0x400000+rva,n),self.base,contract)
   if not integrated:
    from portable_map_bridge_v1 import attach
    self.runtime_address,self.state=attach(self,profile,(DATA/'运行桥地图尺寸.bin').read_bytes())
   if self.read(self.state['magic'],8)!=b'NMT1\x01\0\0\0':raise RuntimeError('运行中的游戏没有匹配测试运行桥；请正常重启游戏')
  except Exception:self.close();raise
 def read(self,va,n):
  buf=ctypes.create_string_buffer(n);got=ctypes.c_size_t()
  runtime=getattr(self,'runtime_address',None)
  addr=va if runtime is not None and runtime<=va<runtime+0x4000 else self.base+va-0x400000
  if not self.k.ReadProcessMemory(self.handle,addr,buf,n,ctypes.byref(got)) or got.value!=n:raise ctypes.WinError(ctypes.get_last_error())
  return buf.raw
 def u(self,va):return int.from_bytes(self.read(va,4),'little')
 def write(self,va,data):
  allowed={(self.state['enabled'],4),(self.state['heartbeat'],4),(self.state['request'],4),(self.state['scene'],12)}
  if (va,len(data)) not in allowed:raise ValueError('工具仅允许写入专用测试邮箱')
  buf=ctypes.create_string_buffer(data);got=ctypes.c_size_t()
  runtime=getattr(self,'runtime_address',None)
  addr=va if runtime is not None and runtime<=va<runtime+0x4000 else self.base+va-0x400000
  if not self.k.WriteProcessMemory(self.handle,addr,buf,len(data),ctypes.byref(got)) or got.value!=len(data):raise ctypes.WinError(ctypes.get_last_error())
 def put(self,key,value):self.write(self.state[key],struct.pack('<I',value&0xffffffff))
 def renew(self):self.put('heartbeat',self.u(0x53a584));self.put('enabled',1)
 def stop(self):self.put('enabled',0)
 def snapshot(self):
  scene=self.u(0x53d064);slot=self.u(0x53a5fc);count=self.u(0x52cda0);xy=None
  if 0<count<=2048 and slot<count:
   world=struct.unpack('<HH',self.read(0x53e8c8+slot*0x48+4,4));xy=[v//16 for v in world]
  if scene!=self.u(0x53d064):xy=None
  return dict(scene=scene,xy=xy,mode=self.u(0x531b80),result=self.u(self.state['result']),ack=self.u(self.state['ack']),request=self.u(self.state['request']),busy=self.u(self.state['busy']))
 def send(self,scene,x,y):
  if not testable(scene):raise ValueError('835—877为插画/制作人员表，已禁止作为地图瞬移目标')
  if not self.u(self.state['enabled']):raise RuntimeError('请先在测试窗口开启连接')
  if self.u(self.state['request'])!=self.u(self.state['ack']) or self.u(self.state['busy']):raise RuntimeError('上一条瞬移尚未完成')
  sequence=(self.u(self.state['request'])+1)&0xffffffff
  self.write(self.state['scene'],struct.pack('<III',scene,x,y));self.put('request',sequence);return sequence
 def close(self):
  if self.handle:self.k.CloseHandle(self.handle);self.handle=None

def record(kind,**data):
 with (LOG_DATA/'测试记录.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(time=datetime.now().isoformat(timespec='seconds'),kind=kind,**data),ensure_ascii=False)+'\n')

class App:
 def __init__(self,root,catalog):
  self.root=root;self.catalog=catalog;self.game=None;self.origin=None;self.pending=None;self.photo=None;self.row=None
  root.title('新仙剑 · 地图验证工具');root.geometry('1140x780');root.minsize(1000,680)
  style=ttk.Style(root);style.configure('.',font=('Microsoft YaHei UI',10))
  top=ttk.Frame(root,padding=8);top.pack(fill='x')
  ttk.Button(top,text='连接游戏 · 开始无限不遇敌测试',command=self.connect).pack(side='left')
  ttk.Button(top,text='结束测试',command=self.stop).pack(side='left',padx=8)
  ttk.Button(top,text='返回测试起点',command=self.back).pack(side='left')
  self.status=tk.StringVar(value='未连接。先从Steam启动并读档，再点“连接游戏”。');ttk.Label(root,textvariable=self.status,padding=(8,2)).pack(fill='x')
  ttk.Label(root,text='测试期间拦截普通遇敌与存档；关闭工具后3秒内恢复。剧情强制战斗仍可能触发。结束后请重新读取正常存档。',padding=(8,2)).pack(fill='x')
  main=ttk.Panedwindow(root,orient='horizontal');main.pack(fill='both',expand=True,padx=8,pady=5)
  left=ttk.Frame(main,width=300);right=ttk.Frame(main);main.add(left,weight=0);main.add(right,weight=1)
  self.query=tk.StringVar();entry=ttk.Entry(left,textvariable=self.query);entry.pack(fill='x');self.query.trace_add('write',lambda *_:self.filter())
  ttk.Label(left,text=f'按场景ID／名称搜索 · {len(catalog.rows)}个可定位场景').pack(anchor='w',pady=3)
  self.list=tk.Listbox(left,width=34,exportselection=False,font=('Microsoft YaHei UI',10));self.list.pack(fill='both',expand=True);self.list.bind('<<ListboxSelect>>',self.select)
  self.title=tk.StringVar(value='选择地图后，点击原画取格坐标');ttk.Label(right,textvariable=self.title).pack(anchor='w')
  self.canvas=tk.Canvas(right,background='#262626',highlightthickness=0);self.canvas.pack(fill='both',expand=True);self.canvas.bind('<Button-1>',self.pick)
  bar=ttk.Frame(right,padding=(0,6));bar.pack(fill='x');ttk.Label(bar,text='格X').pack(side='left');self.x=tk.StringVar(value='0');ttk.Entry(bar,textvariable=self.x,width=7).pack(side='left',padx=4)
  ttk.Label(bar,text='格Y').pack(side='left');self.y=tk.StringVar(value='0');ttk.Entry(bar,textvariable=self.y,width=7).pack(side='left',padx=4)
  self.snap=tk.BooleanVar(value=True);ttk.Checkbutton(bar,text='吸附附近候选道路',variable=self.snap).pack(side='left',padx=4)
  ttk.Button(bar,text='瞬移到此处',command=self.warp).pack(side='left',padx=6)
  buttons=ttk.Frame(right);buttons.pack(fill='x');ttk.Button(buttons,text='定位当前所在地图',command=self.locate).pack(side='left');ttk.Button(buttons,text='记录此处地图问题',command=self.problem).pack(side='left',padx=5)
  ttk.Label(root,text='原画用于选点，不代表每张手绘地图已开发。坐标单位为格（1格=16世界像素）；道路吸附是静态候选检查，动态障碍需实机确认。',padding=8).pack(fill='x')
  self.filter();root.protocol('WM_DELETE_WINDOW',self.close);root.after(1000,self.pulse)
 def filter(self):
  q=self.query.get().strip().casefold();self.filtered=[r for r in self.catalog.rows if q in f"{r['scene_id']} {r['name']} {r['category']}".casefold()]
  self.list.delete(0,'end')
  for r in self.filtered:self.list.insert('end',f"{r['scene_id']:03}  {r['name']}  [{r['width']}×{r['height']}]")
 def select(self,event=None):
  if not self.list.curselection():return
  self.row=self.filtered[self.list.curselection()[0]];r=self.row;self.title.set(f"{r['scene_id']} · {r['name']}  格尺寸{r['width']}×{r['height']}  / 原画资源{r['resource_id']}")
  self.canvas.delete('all');self.photo=None;self.scale=1
  try:
   if r['image']:
    image=tk.PhotoImage(file=str(WORK/r['image']));factor=max(1,math.ceil(image.width()/780),math.ceil(image.height()/570));self.scale=factor*r.get('preview_scale',1);self.photo=image.subsample(factor,factor)
    self.canvas.create_image(0,0,image=self.photo,anchor='nw')
   else:self.canvas.create_text(20,20,text='本场景没有原画预览，可填写格坐标',fill='white',anchor='nw')
   try:x,y=self.catalog.landing(r['scene_id'],r['width']//2,r['height']//2,True,None)
   except ValueError:x,y=r['width']//2,r['height']//2
   self.x.set(x);self.y.set(y);self.cross()
  except Exception as e:messagebox.showerror('原画加载',str(e))
 def pick(self,e):
  if not self.row:return
  x,y=int(e.x*self.scale//16),int(e.y*self.scale//16)
  if x>=self.row['width'] or y>=self.row['height']:return
  try:x,y=self.catalog.landing(self.row['scene_id'],x,y,self.snap.get())
  except ValueError as err:self.status.set(str(err));return
  self.x.set(x);self.y.set(y);self.cross()
 def cross(self):
  self.canvas.delete('target');x=int(self.x.get())*16/self.scale;y=int(self.y.get())*16/self.scale
  self.canvas.create_oval(x-6,y-6,x+6,y+6,outline='#ffd55c',width=2,tags='target');self.canvas.create_line(x-10,y,x+10,y,fill='#ffd55c',tags='target');self.canvas.create_line(x,y-10,x,y+10,fill='#ffd55c',tags='target')
 def connect(self):
  if self.game:return
  try:
   self.game=Game();state=self.game.snapshot()
   if state['mode']!=0 or state['xy'] is None or state['scene'] not in self.catalog.byid:raise RuntimeError('请先读档进入能自由走动的地图')
   self.origin=(state['scene'],*state['xy']);self.game.renew();self.status.set('测试已开启：无限普通不遇敌；请选择地图和落点');record('start',origin=self.origin);self.locate()
  except Exception as e:
   if self.game:self.game.close();self.game=None
   messagebox.showerror('连接失败',str(e))
 def stop(self):
  if self.game:
   try:self.game.stop();record('stop')
   except OSError:pass
   self.game.close();self.game=None
  self.pending=None;self.status.set('测试已结束，正常遇敌规则已恢复；请读回正常存档。')
 def submit(self,scene,x,y):
  if not self.game:raise RuntimeError('请先连接游戏开启测试')
  state=self.game.snapshot();seq=self.game.send(scene,x,y);self.pending=dict(seq=seq,scene=scene,x=x,y=y,source=state)
  self.status.set('瞬移请求已提交；若游戏在后台暂停，切回游戏即可执行。')
 def warp(self):
  try:
   if not self.row:raise ValueError('请先选择地图')
   x,y=self.catalog.landing(self.row['scene_id'],int(self.x.get()),int(self.y.get()),self.snap.get());self.x.set(x);self.y.set(y);self.cross();self.submit(self.row['scene_id'],x,y)
  except Exception as e:messagebox.showerror('未执行瞬移',str(e))
 def back(self):
  try:
   if not self.origin:raise RuntimeError('尚无测试起点')
   self.submit(*self.origin)
  except Exception as e:messagebox.showerror('返回起点',str(e))
 def locate(self):
  if not self.game:return
  state=self.game.snapshot();id=state['scene']
  self.query.set('');index=next((i for i,r in enumerate(self.filtered) if r['scene_id']==id),None)
  if index is None:return
  self.list.selection_clear(0,'end');self.list.selection_set(index);self.list.see(index);self.select()
  if state['xy']:self.x.set(state['xy'][0]);self.y.set(state['xy'][1]);self.cross()
 def problem(self):
  if not self.game:return
  text=simpledialog.askstring('记录地图问题','描述人物点、道路、出口或迷雾的问题：')
  if text:record('problem',state=self.game.snapshot(),note=text);self.status.set('问题已记录到'+str(LOG_DATA/'测试记录.jsonl'))
 def pulse(self):
  if self.game:
   try:
    self.game.renew();state=self.game.snapshot()
    if self.pending and state['ack']==self.pending['seq'] and not state['busy'] and state['result']!=10:
     record('warp_result',request=self.pending,state=state);self.pending=None;self.status.set(RESULTS.get(state['result'],'等待游戏')+f"；当前场景{state['scene']}，坐标{state['xy']}；无限不遇敌开启")
   except Exception as e:self.stop();self.status.set('游戏已退出或连接断开：'+str(e))
  self.root.after(1000,self.pulse)
 def close(self):self.stop();self.root.destroy()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--list',action='store_true');ap.add_argument('--status',action='store_true');ap.add_argument('--send',nargs=3,type=int,metavar=('SCENE','X','Y'));ap.add_argument('--self-check',action='store_true');ap.add_argument('--check-exe',type=Path);ap.add_argument('--report',type=Path);args=ap.parse_args();catalog=Catalog()
 if args.list:
  print(json.dumps(catalog.data,ensure_ascii=True));return
 if args.status or args.send:
  game=Game()
  try:
   if args.send:
    scene,x,y=args.send;x,y=catalog.landing(scene,x,y,True);seq=game.send(scene,x,y);print(json.dumps(dict(request=seq,scene=scene,xy=[x,y],status='queued; active GUI session required')))
   else:print(json.dumps(game.snapshot()))
  finally:game.close()
  return
 root=tk.Tk();root.withdraw()
 if args.self_check:
  try:
   app=App(root,catalog);root.update_idletasks();assert len(app.filtered)==catalog.data['scene_count'] and not(set(catalog.byid)&NON_MAP_SCENES)
   previews=set()
   for row in catalog.rows:
    assert len(catalog.grid(row))==row['width']*row['height']
    if row['image'] and row['image'] not in previews:
     photo=tk.PhotoImage(file=str(WORK/row['image']));assert photo.width()>0 and photo.height()>0;previews.add(row['image'])
   app.list.selection_set(0);app.select();root.update_idletasks();assert app.photo is not None
   report=dict(status='passed; no game connection or memory writes',frozen=FROZEN,scenes=len(catalog.rows),grids=len(catalog.cache),previews=len(previews),compatibility_policy='interface regions; no whole-EXE hash allowlist',interface_contracts=[c['label'] for c in compatibility_rules()['contracts']])
   if args.check_exe:
    from map_test_compat_v2 import select_contract
    selected=select_contract(args.check_exe.read_bytes(),compatibility_rules())
    report['selected_interface']=selected['label'];report['whole_exe_hash_allowlist']=False
   if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
   if sys.stdout:print(json.dumps(report,ensure_ascii=True))
  finally:root.destroy()
  return
 k=ctypes.WinDLL('kernel32',use_last_error=True);k.CreateMutexW.argtypes=[ctypes.c_void_p,wt.BOOL,wt.LPCWSTR];k.CreateMutexW.restype=wt.HANDLE;k.CloseHandle.argtypes=[wt.HANDLE]
 mutex=k.CreateMutexW(None,True,'Local\\NewPAL_MapTestController_v1')
 if not mutex or ctypes.get_last_error()==183:
  if mutex:k.CloseHandle(mutex)
  messagebox.showerror('地图测试','已有一个测试窗口，请使用原窗口');root.destroy();return
 app=None
 try:app=App(root,catalog);root.deiconify();root.mainloop()
 finally:
  if app and app.game:app.stop()
  k.CloseHandle(mutex)

if __name__=='__main__':main()
