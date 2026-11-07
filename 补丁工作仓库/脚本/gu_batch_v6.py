"""Compile a freestanding helper, relocate its internal references and append it.

No live attachment and no installation. Requires the existing local MSVC x86 tools.
"""
import hashlib,json,struct,subprocess,os
from pathlib import Path
import flash_v4 as pe

ROOT=pe.ROOT;OUT=ROOT/'补丁工作仓库/候选版本/gu-batch-v6'
SOURCE=ROOT/'修改exe备份/NewPAL_Release.exe.orig-before-gu-batch-v1-20261107'
BASE='6926c69a0cfc75af775ab7ed2bab9e3b0c910c88e4ed8ddbbb1b36f6ce7b9121'
TOOLS=Path(os.environ.get('NEWPAL_MSVC_TOOLS', '.local/msvc-x86'))
HOOKS={0x4e40ce:(0x474850,'GuCursor'),0x4ba72e:(0x4b4b90,'GuInput'),0x4c0a51:(0x4c3180,'GuUpdate'),0x4ca321:(0x4e3370,'GuDraw'),0x4c3521:(0x4ddf40,'GuFinishGate'),0x4c359d:(0x4fb390,'GuFormat')}
def u16(b,p):return struct.unpack_from('<H',b,p)[0]
def u32(b,p):return struct.unpack_from('<I',b,p)[0]

def helper(origin):
 d=OUT/'build';d.mkdir(parents=True,exist_ok=True)
 obj=d/'gu.obj';dll=d/'gu-helper.dll'
 cmds=[[str(TOOLS/'cl.exe'),'/nologo','/c','/TC','/O1','/Ob1','/Oi','/GS-','/Zl','/Brepro',f'/Fo{obj}',str(Path(__file__).with_suffix('.c'))],
 [str(TOOLS/'link.exe'),'/nologo','/dll','/noentry','/nodefaultlib','/machine:x86','/base:0x10000000','/fixed:no','/dynamicbase:no','/safeseh:no','/merge:.rdata=.text','/merge:.data=.text','/section:.text,ERW','/opt:noref','/opt:noicf','/incremental:no','/Brepro',f'/out:{dll}',str(obj)]]
 for cmd in cmds:
  r=subprocess.run(cmd,capture_output=True);(d/('compile.log' if 'cl.exe' in cmd[0] else 'link.log')).write_bytes(r.stdout+r.stderr)
  if r.returncode:raise RuntimeError((r.stdout+r.stderr).decode('utf-8','replace'))
 b=dll.read_bytes();_,opt,sections=pe.pe_info(b);imagebase=u32(b,opt+28)
 # .reloc is metadata; all helper code, globals and strings are merged in .text.
 used=[s for s in sections if s[0]!=b'.reloc'];lo=min(s[2] for s in used);hi=max(s[2]+max(s[1],s[3]) for s in used)
 blob=bytearray((hi-lo+4095)&~4095)
 for _,vs,rva,rs,rp in used:blob[rva-lo:rva-lo+rs]=b[rp:rp+rs]
 assert not u32(b,opt+104),'Helper must not import external DLLs'
 er=pe.rva_offset(b,u32(b,opt+96));count=u32(b,er+24)
 names=pe.rva_offset(b,u32(b,er+32));ords=pe.rva_offset(b,u32(b,er+36));funcs=pe.rva_offset(b,u32(b,er+28));symbols={}
 for i in range(count):
  p=pe.rva_offset(b,u32(b,names+4*i));name=b[p:b.index(0,p)].decode('ascii');rva=u32(b,funcs+4*u16(b,ords+2*i));symbols[name]=origin+rva-lo
 delta=origin-(imagebase+lo);rr=u32(b,opt+136);size=u32(b,opt+140);relocs=[]
 if rr:
  p=pe.rva_offset(b,rr);end=p+size
  while p<end:
   page,n=struct.unpack_from('<II',b,p)
   if n<8:raise ValueError('bad relocation block')
   for i in range((n-8)//2):
    e=u16(b,p+8+2*i);typ=e>>12;rva=page+(e&4095)
    if not typ:continue
    if typ!=3:raise ValueError('non HIGHLOW helper relocation')
    off=rva-lo
    if 0<=off<=len(blob)-4:
     old=u32(blob,off);assert imagebase+lo<=old<imagebase+hi
     blob[off:off+4]=pe.u32(old+delta);relocs.append(off)
   p+=n
 return bytes(blob),dict(symbols=symbols,relocations=relocs,linked_image_base=imagebase,linked_low_rva=lo,code_size=hi-lo)

def candidate(source):
 if hashlib.sha256(source).hexdigest()!=BASE:raise ValueError('Unexpected pre-gu backup baseline')
 header,opt,sections=pe.pe_info(source);name,vs,rva,rs,rp=sections[-1]
 assert name==b'.palhov' and vs==rs and rp+rs==len(source)
 origin=0x400000+rva+rs;blob,plan=helper(origin);data=bytearray(source+blob)
 for va,(old,label) in HOOKS.items():
  off=pe.rva_offset(source,va-0x400000);expected=pe.branch(0xe8,va,old);assert source[off:off+5]==expected,(hex(va),source[off:off+5].hex())
  data[off:off+5]=pe.branch(0xe8,va,plan['symbols'][label]);plan.setdefault('changed_regions',[]).append(dict(va=va,offset=off,before=expected.hex(),after=data[off:off+5].hex()))
 sh=opt+u16(source,header+20)+(len(sections)-1)*40
 for off,value in ((sh+8,vs+len(blob)),(sh+16,rs+len(blob)),(opt+4,u32(source,opt+4)+len(blob)),(opt+56,rva+rs+len(blob)),(opt+64,0)):
  data[off:off+4]=pe.u32(value);plan.setdefault('header_offsets',[]).append(off)
 plan.update(baseline_sha256=BASE,candidate_sha256=hashlib.sha256(data).hexdigest(),origin=origin,size=len(data),appended_size=len(blob),status='v8 approved design integration candidate; offline verification required before local install; gameplay pending')
 return bytes(data),plan

if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True);data,plan=candidate(SOURCE.read_bytes())
 (OUT/'NewPAL_Release.gu-batch-v6.exe').write_bytes(data)
 (OUT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(candidate_sha256=plan['candidate_sha256'],appended_size=plan['appended_size'],symbols=plan['symbols']),ensure_ascii=False))
