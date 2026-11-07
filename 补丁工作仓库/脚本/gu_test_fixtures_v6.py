"""Execute candidate x86 code with bounded inventory/resource/UI substitutes.

Tests do not attach to the game or claim real hardware/complete native inventory QA.
The original 004c3180 animation-completion driver executes in integration cases.
"""
import collections,hashlib,json,sys
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
import gu_batch_v6 as fix

class Machine:
 def __init__(self,data,plan,bag=None,recipes=None,eggs=None):
  self.u=Uc(UC_ARCH_X86,UC_MODE_32);self.u.mem_map(0x400000,0x2000000);self.u.mem_map(0,0x1000)
  for _,vs,rva,rs,rp in fix.pe.pe_info(data)[2]:self.u.mem_write(0x400000+rva,data[rp:rp+rs])
  self.plan=plan;self.bag=collections.Counter(bag or {});self.recipes=recipes or {(100,101):200};self.eggs=list(eggs or [])
  self.events=[];self.resources=[];self.draws=[];self.sounds=[];self.up=self.down=self.left=self.right=self.confirm=0;self.fail_at=None;self.mutations=0;self.record=200
  self.paint_order=[];self.hide_refresh_objects=False;self.objects={};self.flags={};self.cached_confirm=False;self.reenter_refresh=False;self.script_ready=1;self.names={};self.native_format=b'Made %%C6%s%%Q';self.cancel=0;self.native_font=False;self.recipe_reads=0
  self.w(0x599894,0x21ee000);self.w(0x531b50,10);self.w(0x58149c,3);self.w(0x531b64,10);self.w(0x531bec,500);self.w(0x531bf0,100)
  self.w(0x581518,100);self.w(0x58151c,101);self.seteggs();self.u.hook_add(UC_HOOK_CODE,self.hook)
 def w(self,p,v):self.u.mem_write(p,fix.pe.u32(v))
 def r(self,p):return int.from_bytes(self.u.mem_read(p,4),'little')
 def arg(self,i):return self.r(self.u.reg_read(UC_X86_REG_ESP)+4+4*i)
 def ret(self,v=0,cleanup=0):
  sp=self.u.reg_read(UC_X86_REG_ESP);self.u.reg_write(UC_X86_REG_EAX,v&0xffffffff);self.u.reg_write(UC_X86_REG_EIP,self.r(sp));self.u.reg_write(UC_X86_REG_ESP,sp+4+cleanup)
 def text(self,p):
  out=bytearray()
  for _ in range(512):
   b=self.u.mem_read(p,1)[0]
   if not b:break
   out.append(b);p+=1
  return bytes(out)
 def seteggs(self):
  self.w(0x59a2e8,0x2120000 if self.eggs else 0);self.w(0x59a2ec,len(self.eggs))
  for i,id in enumerate(self.eggs):
   n=0x2120000+32*i;self.w(n+4,n+24);self.w(n+24,id);self.w(n+16,n+32 if i+1<len(self.eggs) else 0)
 def slot(self,index,value=None):
  p=self.plan['symbols']['GuState']+4*index
  if value is not None:self.w(p,value)
  return self.r(p)
 def hook(self,u,pc,size,_):
  if pc==0x474850:
   self.paint_order.append('cursor');self.events.append(('cursor',pc));self.ret();return
  zeros={0x4cce10,0x4ccdc0,0x4e3370,0x4bba50,0x4eb000,0x4e97c0,0x4e04f0}
  if pc in zeros:
   self.events.append(('native',pc))
   if pc==0x4e3370 and 'GuCursor' in self.plan['symbols']:
    u.reg_write(UC_X86_REG_EIP,self.plan['symbols']['GuCursor']);return
   if pc==0x4bba50 and self.hide_refresh_objects:
    for obj in self.objects.values():self.flags[obj+0x28]=self.flags.get(obj+0x28,0)|1
   if pc in (0x4cce10,0x4ccdc0):
    p,bit=self.arg(0),self.arg(1);old=self.flags.get(p,0)
    self.flags[p]=(old|(1<<bit)) if pc==0x4cce10 else (old&~(1<<bit))
   if pc==0x4bba50 and self.reenter_refresh and self.r(0x531b50)==10 and self.r(0x58149c)>=3:
    u.reg_write(UC_X86_REG_EIP,self.plan['symbols']['GuUpdate'])
   else:self.ret()
  elif pc==0x4b4b90:self.events.append(('old-input',self.arg(0)));self.ret(7)
  elif pc==0x4ddf40:self.recipe_reads+=1;self.ret(self.recipes.get((self.arg(0),self.arg(1)),-1))
  elif pc==0x4dca10:
   id=self.arg(0);obj=0x2140000+id*0x80
   if self.bag[id]>0:self.w(obj+0x6c,id);self.ret(obj)
   else:self.ret(0)
  elif pc==0x4dcc20:
   id=self.arg(0);p=0x2180000+id*4;self.w(p,self.bag[id]);self.ret(p)
  elif pc==0x4e9630:
   id=self.arg(0);delta=self.arg(1);delta=delta if delta<0x80000000 else delta-0x100000000
   self.mutations+=1
   if self.mutations==self.fail_at:self.ret(0);return
   if 500<=id<600:
    if delta==1 and len(self.eggs)<99:self.eggs.append(id)
    elif delta==-1 and id in self.eggs:self.eggs.remove(id)
    self.seteggs()
   else:self.bag[id]=min(99,max(0,self.bag[id]+delta))
   self.events.append(('delta',id,delta));self.ret()
  elif pc in (0x4e1e80,0x4e0c90,0x4e1740,0x4e1bc0,0x4e0a90):self.ret({0x4e1e80:self.up,0x4e0c90:self.down,0x4e1740:self.left,0x4e1bc0:self.right,0x4e0a90:self.r(0x59a3ac) if self.cached_confirm else self.confirm}[pc])
  elif pc==0x4cb690:self.ret(self.script_ready)
  elif pc==0x4e0e00:self.ret(self.cancel)
  elif pc==0x4e0d10:self.cancel=0;self.ret()
  elif pc==0x4f3280:self.sounds.append(self.arg(0));self.ret()
  elif pc==0x4e4a70:self.ret(self.objects.get(self.arg(1),0))
  elif pc==0x4cd2d0:self.ret(1)
  elif pc==0x4e9d80:
   obj=self.object(self.arg(1));self.w(obj+8,self.arg(4));self.w(obj+12,self.arg(5));self.ret(obj)
  elif pc==0x4bc560:self.w(self.arg(1),10000);self.w(self.arg(2),1);self.ret()
  elif pc==0x4cec50:self.w(self.arg(1),10000);self.w(self.arg(2),1);self.ret()
  elif pc==0x4ce440:self.ret(0x21a1000)
  elif pc==0x4f85b0:
   assert self.arg(0)==0,'native item group is valid index zero'
   self.record=self.arg(1);self.ret(0x21b1000)
  elif pc==0x4dddb0:
   p=0x21b2000;self.u.mem_write(p,self.names.get(self.record,('Item'+str(self.record)).encode())+b'\0');self.ret(p)
  elif pc==0x4fb390:self.u.mem_write(0x21b3000,self.native_format+b'\0');self.ret(0x21b3000)
  elif pc==0x41a240:
   target,fmt,name=self.arg(0),self.text(self.arg(1)),self.text(self.arg(2))
   rendered=bytearray();i=0
   while i<len(fmt):
    if fmt[i:i+2]==b'%%':rendered+=b'%';i+=2
    elif fmt[i:i+2]==b'%s':rendered+=name;i+=2
    else:rendered.append(fmt[i]);i+=1
   assert len(rendered)<256
   self.u.mem_write(target,bytes(rendered)+b'\0');self.ret(target)
  elif pc==0x4cb710:self.events.append(('script',self.arg(0),self.text(0x588740)));self.script_ready=0;self.ret(1)
  elif pc==0x4af910:
   assert u.reg_read(UC_X86_REG_ECX)==0x570b38
   self.resources.append(self.text(self.arg(1)));self.ret(100+3*len(self.resources),12)
  elif pc==0x4afa10:
   assert u.reg_read(UC_X86_REG_ECX)==0x570b38
   self.paint_order.append('image');self.draws.append((self.arg(0),self.arg(2),self.arg(3)));self.ret(0,16)
  elif pc==0x4c7f50:
   if not self.native_font:self.paint_order.append('text');self.draws.append((self.text(self.arg(0)),self.arg(1),self.arg(2),self.arg(3)));self.ret()
  elif pc==0x48e4d0:self.ret((self.arg(0)<<11)|(self.arg(1)<<6)|self.arg(2))
  elif pc==0x4a4830:
   assert u.reg_read(UC_X86_REG_ECX) in (0x57fe60,0x57feb8);self.ret(0,4)
  elif pc==0x4a4960:
   ctx=u.reg_read(UC_X86_REG_ECX);assert ctx in (0x57fe60,0x57feb8)
   self.paint_order.append('text');self.draws.append((self.text(self.arg(3)),'native18brown' if ctx==0x57fe60 else 'native24',self.arg(1),self.arg(2)));self.ret(0,24)
 def call(self,name,args=()):
  va=self.plan['symbols'][name] if isinstance(name,str) else name;sp=0x230e000
  for i,v in enumerate([0x23ff000,*args]):self.w(sp+i*4,v)
  for reg,v in ((UC_X86_REG_ESP,sp),(UC_X86_REG_EBP,0x230d000),(UC_X86_REG_EBX,123),(UC_X86_REG_ESI,234),(UC_X86_REG_EDI,345)):self.u.reg_write(reg,v)
  try:self.u.emu_start(va,0x23ff000,count=3000000)
  except Exception as e:raise RuntimeError((name,hex(self.u.reg_read(UC_X86_REG_EIP)),self.events[-6:])) from e
  assert self.u.reg_read(UC_X86_REG_EIP)==0x23ff000,(name,'did not return')
  assert self.u.reg_read(UC_X86_REG_ESP)==sp+4,(name,'stack')
  for reg,v in ((UC_X86_REG_EBP,0x230d000),(UC_X86_REG_EBX,123),(UC_X86_REG_ESI,234),(UC_X86_REG_EDI,345)):assert self.u.reg_read(reg)==v,(name,'callee register',reg)
  return self.u.reg_read(UC_X86_REG_EAX)
 def object(self,id):
  if id not in self.objects:
   self.objects[id]=0x21c0000+0x100*len(self.objects)
   self.w(self.objects[id]+0x70,0x21a1000)
  return self.objects[id]
 def animate(self):
  self.object(0x642);self.object(0x643);self.object(0xaa)
  self.reenter_refresh=True;trace=[]
  for tick in range(10):
   before=self.bag.copy();held=(self.r(0x581518),self.r(0x58151c));draws=len(self.draws)
   self.call('GuDraw');assert len(self.draws)==draws,'overlay during native synthesis'
   self.call(0x4b7b70)
   trace.append((self.r(0x531b64),self.r(self.objects[0x642]+8),self.r(self.objects[0x643]+8)))
   assert self.bag==before and held==(self.r(0x581518),self.r(0x58151c)),'commit before native animation end'
  assert self.r(0x531b64)==0 and self.r(0x581520)==1
  self.call(0x4b7b70)
  return trace
 def prep(self,n):
  got=self.call('GuBuild',[n]);self.slot(2,n);return got

class NativeNames(Machine):
 """Execute native group/cache/name-field query over explicit private list records.
 Cache entries and names come from fixtures or the unmodified local gitem file.
 This does not emulate the game's file parser or claim a live snapshot.
 """
 def hook(self,u,pc,size,_):
  if pc==0x4f85b0:
   assert self.arg(0)==0
   item=self.arg(1);name=self.names.get(item,b'Name')
   header=0x59cb54;node=0x21b0100;pair=0x21b0200;record=0x21b0300;nn=0x21b0400;payload=0x21b0500
   for p,words in [(header,[node,1,0,node,0,0,0]),(node,[8,pair,record,0,0]),(pair,[0,item]),(record,[nn,1,0,nn,0,0,0]),(nn,[4+len(name)+1,payload,0,0,0]),(payload,[0x7ff2f000])]:
    for i,v in enumerate(words):self.w(p+4*i,v)
   u.mem_write(payload+4,name+b'\0');return
  if pc==0x4dddb0:return
  return super().hook(u,pc,size,_)

class NativeRefresh(Machine):
 """Run actual004bba50 ->004c09b0 ->GuUpdate; private layer0 list/sort substitute."""
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  for item in [0xaa,0x640,0x641,0x642,0x643]:self.object(item)
  header=0x21e0000;self.w(0x59bf40,header)
  nodes=[0x21e1000+i*32 for i in range(len(self.objects))]
  for i,(node,obj) in enumerate(zip(nodes,self.objects.values())):
   for off,v in enumerate([0,obj,0,nodes[i-1] if i else 0,nodes[i+1] if i+1<len(nodes) else 0]):self.w(node+4*off,v)
  for i,v in enumerate([nodes[0],len(nodes),0,nodes[0],0,0,0]):self.w(header+4*i,v)
 def hook(self,u,pc,size,_):
  if pc==0x4bba50:return
  if pc in [0x4cd2d0,0x4cd170] and u.reg_read(UC_X86_REG_ECX)==0x21e0000:return
  if pc==0x4cdfc0:self.ret(0,8);return
  return super().hook(u,pc,size,_)

class NativeSelect(Machine):
 """Actual native mode10 mouse selection + original confirmation/button blocks.
 UI scroll helpers and graphics remain substitutes; no live input is sampled.
 """
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);self.cached_confirm=True
  for address,value in [(0x581518,0),(0x58151c,0),(0x58149c,0),(0x581540,6),(0x580c88,2),
   (0x581494,0),(0x581c84,580),(0x581c88,240),(0x581c58,24),(0x581c74,0),(0x53b8c0,250),(0x53b8c4,200)]:self.w(address,value)
  obj=self.object(0x640);self.flags[obj+0x28]=1
 def hook(self,u,pc,size,_):
  if pc==0x4b4b90:return
  if pc==0x4aa660:self.ret(0,8);return
  if pc in (0x4fda30,0x4fd800,0x4fdc10):self.ret(0,4);return
  return super().hook(u,pc,size,_)
 def advance_and_button(self,item=101):
  # These are original instruction spans. Run only the state/visibility parts;
  # the enclosing item-list render, string creation and destruction are not run.
  self.u.reg_write(UC_X86_REG_ESP,0x230e000);self.u.reg_write(UC_X86_REG_EBP,0x230d000)
  self.w(0x230d000-0x10,item)
  self.u.emu_start(0x4c3b82,0x4c3c7b,count=10000)
  assert self.u.reg_read(UC_X86_REG_EIP)==0x4c3c7b
  assert self.u.reg_read(UC_X86_REG_ESP)==0x230e000
  self.u.emu_start(0x4c3cc5,0x4c3d79,count=10000)
  assert self.u.reg_read(UC_X86_REG_EIP)==0x4c3d79
  assert self.u.reg_read(UC_X86_REG_ESP)==0x230e000
 def click(self):
  self.w(0x59a3ac,0);self.u.mem_write(0x580dc0,b'\x02')
  self.call('GuInput',[10]);self.advance_and_button()
 def button_visible(self):return (self.flags[self.objects[0x640]+0x28]&1)==0

