"""Context-limited result-popup dismissal. Candidate builder, no live attachment.

The event observer records A/B/left-button edges without changing native input.
Only the two result-window call sites consume input. Skill notifications expire
through their existing renderer; no dialog list is manually freed.
"""
import hashlib,json,struct
import flash_v4 as pe
from settings_toggle_v1 import imports

BASE='f8ced732c5d79da82492db6b55f2aab7a362b4616b8316ea884f9550d6dca90f'
OUT=pe.ROOT/'补丁工作仓库/候选版本/postbattle-popup-skip-v1'
SIZE=0x1000
EXPECTED={0x4a9330:bytes.fromhex('55 8b ec 83 ec 30'),
 0x4d2b4b:pe.branch(0xe8,0x4d2b4b,0x4e0a90),
 0x4e9369:pe.branch(0xe8,0x4e9369,0x4c7a10)}

def payload(origin,iat):
 a=pe.Asm(origin);sy={};state=origin+0xe00
 held,pending,mode,token,previous,fired=[state+4*i for i in range(6)]
 def op(code,address,tail=b''):a.raw(bytes.fromhex(code)+pe.u32(address)+tail)
 def store(address,value):op('c7 05',address,pe.u32(value))
 def cmp(address,value):op('81 3d',address,pe.u32(value))
 def start(name):sy[name]=a.pc;a.label(name)
 def call(name):a.jump('e8',name)

 start('observe_event')
 a.raw('9c 60 81 f9');a.raw(pe.u32(0x580b38));a.jump('0f 85','observer_done')
 a.raw('8b 44 24 28 83 f8 15');a.jump('0f 84','event_a')
 a.raw('83 f8 16');a.jump('0f 84','event_b')
 a.raw('83 f8 0f');a.jump('0f 85','observer_done');a.raw('ba 04 00 00 00');a.jump('e9','event_bit')
 a.label('event_a');a.raw('ba 01 00 00 00');a.jump('e9','event_bit')
 a.label('event_b');a.raw('ba 02 00 00 00')
 a.label('event_bit');a.raw('80 7c 24 2c 00');a.jump('0f 84','event_up')
 op('85 15',held);a.jump('0f 85','observer_done')
 op('09 15',held);op('09 15',pending);a.jump('e9','observer_done')
 a.label('event_up');a.raw('f7 d2');op('21 15',held)
 a.label('observer_done');a.raw('61 9d');a.raw(EXPECTED[0x4a9330]);a.jump('e9',0x4a9336)

 start('sample')
 # SDL is already pumping these events. No OS polling or device reopen.
 a.raw('6a 00');op('ff 15',iat['SDL_GetKeyboardState']);a.raw('83 c4 04 8b d0')
 op('a1',held);a.raw('85 d2');a.jump('0f 84','sample_done')
 for scan,bit in ((44,8),(40,16),(88,32)):
  a.raw(bytes([0x80,0x7a,scan,0]));a.jump('0f 84',f'key_{scan}_done')
  a.raw(bytes([0x83,0xc8,bit]));a.label(f'key_{scan}_done')
 a.label('sample_done');a.raw('c3')

 start('consume')
 # Clear only the accepted action slots and their aliases; directions survive.
 for slot in (0,1,12,15,21,22):
  address=0x580c94+20*slot
  op('c6 05',address,b'\x00');store(address+8,0)
 op('83 25',0x59a328,b'\xfa') # cancel bits 1/4
 for address in (0x59a334,0x59a3ac,0x59a3c8):store(address,0)
 a.raw('c3')

 start('poll') # cdecl (mode, token, initialize)
 a.raw('55 8b ec 53 56 57');call('sample');a.raw('8b f0 8b 55 08')
 op('3b 15',mode);a.jump('0f 85','poll_init')
 a.raw('8b 55 0c');op('3b 15',token);a.jump('0f 85','poll_init')
 a.raw('83 7d 10 00');a.jump('0f 85','poll_init')
 op('a1',previous);a.raw('f7 d0 23 c6');op('0b 05',pending);a.raw('8b f8')
 op('89 35',previous);store(pending,0)
 cmp(fired,0);a.jump('0f 85','poll_none')
 a.raw('85 ff');a.jump('0f 84','poll_none')
 store(fired,1);call('consume');a.raw('b8 01 00 00 00');a.jump('e9','poll_return')
 a.label('poll_init');a.raw('8b 45 08');op('a3',mode);a.raw('8b 45 0c');op('a3',token)
 op('89 35',previous);store(pending,0);store(fired,0)
 a.label('poll_none');a.raw('31 c0')
 a.label('poll_return');a.raw('5f 5e 5b 8b e5 5d c3')

 start('level_confirm')
 cmp(0x599814,9);a.jump('0f 85',0x4e0a90)
 a.raw('31 c0');cmp(0x5998d0,0);a.raw('0f 94 c0 50')
 op('a1',0x5998cc);a.raw('40 50 6a 01');call('poll');a.raw('83 c4 0c c3')

 start('skill_wait')
 a.raw('55 8b ec 53 56 57 ff 75 0c ff 75 08');call(0x4c7a10);a.raw('83 c4 08 8b f0')
 cmp(0x599814,10);a.jump('0f 85','skill_return')
 a.raw('83 7d 08 02');a.jump('0f 85','skill_return')
 a.raw('66 81 7d 0c 10 27');a.jump('0f 85','skill_return')
 a.raw('85 f6');a.jump('0f 84','skill_pending')
 cmp(mode,2);a.jump('0f 85','skill_return');store(mode,0);store(pending,0);a.jump('e9','skill_return')
 a.label('skill_pending');op('8b 3d',0x58915c);a.raw('85 ff');a.jump('0f 84','skill_return')
 a.raw('f6 47 08 40');a.jump('0f 84','skill_return')
 a.raw('6a 00 57 6a 02');call('poll');a.raw('83 c4 0c')
 # A still-typing notification initializes its native timer/fade at the end
 # of text. Reapply the expiry request next tick until that object is gone.
 cmp(fired,0);a.jump('0f 84','skill_return')
 # Request immediate native expiry/full text. Renderer owns cleanup and the
 # script advances only after the native wait actually observes completion.
 a.raw('81 4f 08 08 00 00 40 c7 47 0c 00 00 00 00')
 op('a1',0x53a584);a.raw('2d e8 03 00 00 89 47 10 66 c7 47 18 01 00')
 a.label('skill_return');a.raw('8b c6 5f 5e 5b 8b e5 5d c3')
 code=a.finish();assert len(code)<0xe00
 return code+bytes(SIZE-len(code)),dict(symbols=sy,state=dict(held=held,pending=pending,mode=mode,token=token,previous=previous,fired=fired),code_size=len(code))

def candidate(source):
 if hashlib.sha256(source).hexdigest()!=BASE:raise ValueError('Unexpected installed baseline')
 header,opt,sections=pe.pe_info(source);last=sections[-1]
 assert last[0]==b'.palhov' and last[1]==last[3]
 _,vs,rva,rs,rp=last;assert rp+rs==len(source)
 origin=0x400000+rva+rs;blob,plan=payload(origin,imports(source));data=bytearray(source+blob)
 for va,label in ((0x4a9330,'observe_event'),(0x4d2b4b,'level_confirm'),(0x4e9369,'skill_wait')):
  off=pe.rva_offset(source,va-0x400000);old=EXPECTED[va]
  assert source[off:off+len(old)]==old
  data[off:off+len(old)]=pe.branch(0xe9 if va==0x4a9330 else 0xe8,va,plan['symbols'][label])+b'\x90'*(len(old)-5)
  plan.setdefault('changed_regions',[]).append(dict(va=hex(va),offset=off,size=len(old),before=old.hex(),after=data[off:off+len(old)].hex()))
 sh=opt+struct.unpack_from('<H',source,header+20)[0]+(len(sections)-1)*40
 for off,value in ((sh+8,vs+SIZE),(sh+16,rs+SIZE),(opt+4,struct.unpack_from('<I',source,opt+4)[0]+SIZE),(opt+56,rva+rs+SIZE),(opt+64,0)):
  data[off:off+4]=pe.u32(value);plan.setdefault('header_offsets',[]).append(off)
 plan.update(baseline_sha256=BASE,candidate_sha256=hashlib.sha256(data).hexdigest(),candidate_sha1=hashlib.sha1(data).hexdigest(),origin=origin,size=len(data),appended_size=SIZE)
 return bytes(data),plan

if __name__=='__main__':
 data,plan=candidate((pe.ROOT/'NewPAL_Release.exe').read_bytes());OUT.mkdir(parents=True,exist_ok=True)
 (OUT/'NewPAL_Release.popup-skip-v1.exe').write_bytes(data)
 (OUT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:plan[k] for k in ('candidate_sha256','candidate_sha1','size','code_size')},ensure_ascii=False))
