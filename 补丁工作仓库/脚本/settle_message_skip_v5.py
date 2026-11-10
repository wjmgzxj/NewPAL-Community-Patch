"""Current settlement payload library. The legacy late helper is retained only
for byte-exact v5 identity and has no installed caller. No installer or live input.
"""
import hashlib,struct
import flash_v4 as pe
SIZE=0x1000
CURSOR_OFF=0x800
CURSOR_LATE_OFF=0x880
STATE_AREA=0xE00
HOOK_VA=0x49FC60
NATIVE_PROLOGUE=bytes.fromhex("55 8b ec 81 ec b8 01 00 00")
RETURN_VA=HOOK_VA+len(NATIVE_PROLOGUE)
FRAME_HOOK_VA=0x45C273
FRAME_BACK=FRAME_HOOK_VA+5
DRAW_LAST=0x4CFC70
DRAW_CURSOR=0x474850
SAMPLE=0x124E083
STATE_SLOT=0x599814
CHAIN_HEAD=0x53E690
TICKS=0x53A584
IDLE=0x53B8D4
SHOWCURSOR_IAT=0x50D2F8
MAX_NODES=256
BASE="3421c9a01d05544042b01c3dbeeb04266884d286e3c2153f82591ed2714c23a0"

def payload(origin):
    a = pe.Asm(origin)
    sy = {}
    state = origin + STATE_AREA
    prev, fired, first_done = state, state + 4, state + 8

    def start(name):
        sy[name] = a.pc
        a.label(name)

    def absop(op, address, tail=b""):
        a.raw(bytes.fromhex(op) + pe.u32(address) + tail)

    def store(address, value):
        absop("c7 05", address, pe.u32(value))

    def expire_fields():
        a.raw("81 4e 08 08 00 00 40")        # or [esi+8],0x40000008
        a.raw("c7 46 0c 00 00 00 00")        # mov [esi+0xc],0
        absop("a1", TICKS)
        a.raw("2d e8 03 00 00")              # sub eax,0x3e8
        a.raw("89 46 10")
        a.raw("66 c7 46 18 01 00")

    def chain_loop(tag, relax_flags):
        absop("8b 35", CHAIN_HEAD)
        a.raw(b"\xbf" + pe.u32(MAX_NODES))
        a.label("loop_" + tag)
        a.raw("85 f6")
        a.jump("0f 84", "done")
        a.raw("4f")
        a.jump("0f 84", "done")
        if not relax_flags:
            a.raw("8b 46 08")
            a.raw("a9 08 00 00 00")
            a.jump("0f 84", "next_" + tag)
        a.raw("81 7e 0c ff ff 00 00")        # wait != 0xffff
        a.jump("0f 84", "next_" + tag)
        expire_fields()
        a.label("next_" + tag)
        a.raw("8b 76 48")
        a.jump("e9", "loop_" + tag)

    # ---- 0x49FC60 入口跳板（与 v1/v2/v3 完全相同，地址不变）----
    start("settle_hook")
    a.raw("9c 60")
    a.jump("e8", "settle_skip")
    a.raw("61 9d")
    a.raw(NATIVE_PROLOGUE)
    a.jump("e9", RETURN_VA)

    # ---- settle_skip：守卫从 state 1 起 ----
    start("settle_skip")
    absop("a1", STATE_SLOT)
    a.raw("85 c0")
    a.jump("0f 84", "leave")                 # state 0 -> 零动作
    a.raw("3d 06 00 00 00")
    a.jump("0f 82", "battle_active")         # 1..5 -> 战斗期
    a.raw("3d 0c 00 00 00")
    a.jump("0f 87", "leave")                 # >12 -> 零动作
    a.jump("e9", "settle_active")            # 6..12

    a.label("leave")
    store(prev, 0xFFFFFFFF)
    store(fired, 0)
    a.raw("c3")

    # ---- 战斗期 1..5：一次性到期，不锁存 ----
    a.label("battle_active")
    store(fired, 0)                          # 清结算锁存
    a.jump("e8", SAMPLE)
    a.raw("89 c3")
    absop("8b 0d", prev)
    a.raw("f7 d1 21 d9")                     # ~prev & now
    absop("89 1d", prev)
    a.raw("85 c9")
    a.jump("0f 84", "done")                  # 无新边沿 -> 完全不动
    chain_loop("battle", relax_flags=True)   # 放宽 flags&8，保留 wait!=0xffff

    # ---- 结算期 6..12：fired 锁存后每帧续写 ----
    a.label("settle_active")
    a.jump("e8", SAMPLE)
    a.raw("89 c3")
    absop("8b 0d", prev)
    a.raw("f7 d1 21 d9")
    absop("89 1d", prev)
    absop("83 3d", fired, b"\x00")
    a.jump("0f 85", "expire_settle")
    a.raw("85 c9")
    a.jump("0f 84", "done")
    store(fired, 1)
    a.label("expire_settle")
    chain_loop("settle", relax_flags=False)  # (flags&8) && wait!=0xffff
    a.label("done")
    a.raw("c3")

    # ---- 光标首帧桩：地址必须仍在 origin+0x800，内容与 v2/v3 一致 ----
    assert len(a.buf) < CURSOR_OFF
    a.raw(b"\x00" * (CURSOR_OFF - len(a.buf)))
    start("cursor_firstframe")
    a.raw("9c 60")
    absop("80 3d", first_done, b"\x00")
    a.jump("0f 85", "cursor_done")
    absop("c6 05", first_done, b"\x01")
    store(IDLE, 91)
    a.raw("6a 00")
    absop("ff 15", SHOWCURSOR_IAT)
    a.label("cursor_done")
    a.raw("61 9d")
    absop("a1", TICKS)
    a.jump("e9", FRAME_BACK)

    # ---- 帧末画光标桩：补执行 0x4CFC70，再在所有 UI 之后画光标 ----
    assert len(a.buf) < CURSOR_LATE_OFF
    a.raw(b"\x00" * (CURSOR_LATE_OFF - len(a.buf)))
    start("cursor_late")
    a.jump("e8", DRAW_LAST)                  # 被覆盖的原 call
    a.raw("9c 60")                           # pushfd; pushal
    a.jump("e8", DRAW_CURSOR)               # call 0x474850（无参）
    a.raw("61 9d")
    a.raw("c3")                              # ret 回 LATE_BACK

    code = a.finish()
    assert len(code) < STATE_AREA, len(code)
    return code + bytes(SIZE - len(code)), dict(
        symbols=sy,
        state=dict(prev=prev, fired=fired, first_done=first_done),
        code_size=len(code),
        cursor_stub_size=CURSOR_LATE_OFF - CURSOR_OFF,
        guard="1 <= state <= 12 (1..5 one-shot, 6..12 latched); state 0 = zero action",
        sample_va=SAMPLE, chain_head=CHAIN_HEAD, state_slot=STATE_SLOT,
    )


def candidate(source):
    assert hashlib.sha256(source).hexdigest()==BASE, 'Expected manual-reentry-v1 baseline'
    header,opt,sections=pe.pe_info(source)
    last=sections[-1];origin=0x400000+last[2]+last[3]
    assert origin==0x1426000 and last[4]+last[3]==len(source)
    blob,plan=payload(origin);out=bytearray(source+blob)
    for va,before,label in [(HOOK_VA,NATIVE_PROLOGUE,'settle_hook'),(FRAME_HOOK_VA,bytes.fromhex('a1 84 a5 53 00'),'cursor_firstframe')]:
        at=pe.rva_offset(source,va-0x400000);assert source[at:at+len(before)]==before
        out[at:at+len(before)]=pe.branch(0xe9,va,plan['symbols'][label])+b'\x90'*(len(before)-5)
    sh=opt+struct.unpack_from('<H',source,header+20)[0]+(len(sections)-1)*40
    for at,value in [(sh+8,last[1]+SIZE),(sh+16,last[3]+SIZE),(opt+4,struct.unpack_from('<I',source,opt+4)[0]+SIZE),(opt+56,last[2]+last[3]+SIZE),(opt+64,0)]:
        struct.pack_into('<I',out,at,value)
    # No hooks are installed for cursor_late: preserve the tested native timing.
    return bytes(out),plan
