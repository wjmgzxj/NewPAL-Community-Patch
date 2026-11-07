"""Increase native KO recovery by one sixth; remove the separate 6% pass.

Guarded against the exact installed v0.3 preview. Build candidates only.
Native eligibility, death clearing, MP addition and caps remain in place.
"""
from pathlib import Path
import hashlib,json
import flash_v4 as pe
import postbattle_recovery_v1 as previous

BASE_SHA256='6a2d11f58a9d4d2e794b46d2952eb13d6867ff519756c200cc24437f8efac9cd'
ORIGIN=0x5e5a00
DIVISION_SITES=(0x4d26ce,0x4d271d)
OLD_DIVISION=bytes.fromhex('99 b9 03 00 00 00 f7 f9')
OUTDIR=pe.ROOT/'补丁工作仓库/候选版本/native-recovery-v2'

def helper():
    # eax = trunc(max/3) + trunc(trunc(max/3)/6).
    # Preserve ebx and the original divide-by-three remainder in edx;
    # leave ecx=3 as in the overwritten native instructions.
    return bytes.fromhex('53 99 b9 03 00 00 00 f7 f9 52 8b d8 99 b9 06 00 00 00 f7 f9 03 c3 5a b9 03 00 00 00 5b c3')

def candidate(source):
    if hashlib.sha256(source).hexdigest()!=BASE_SHA256:
        raise ValueError('Installed baseline differs; refuse automatic conversion')
    plan=previous.payload(pe.IMAGE_BASE,ORIGIN)
    changes={}
    def put(va,expected,replacement):
        assert len(expected)==len(replacement)
        off=pe.rva_offset(source,va-pe.IMAGE_BASE)
        if source[off:off+len(expected)]!=expected:
            raise ValueError('Unexpected bytes at '+hex(va))
        changes[va]=(off,expected,replacement)
    put(pe.IMAGE_BASE+previous.SITE,plan['patches'][previous.SITE],previous.EXPECTED)
    put(ORIGIN,plan['blob'],helper()+bytes(previous.SIZE-len(helper())))
    for va in DIVISION_SITES:
        put(va,OLD_DIVISION,pe.branch(0xe8,va,ORIGIN)+b'\x90'*3)
    result=bytearray(source)
    for off,expected,new in changes.values():result[off:off+len(new)]=new
    return bytes(result),{'previous_sha256':BASE_SHA256,'sha256':hashlib.sha256(result).hexdigest(),
        'sha1':hashlib.sha1(result).hexdigest(),'size':len(result),
        'formula':'native_amount=trunc(maximum/3); new_amount=native_amount+trunc(native_amount/6)',
        'separate_6_percent_exit_call_removed':True,
        'native_eligibility_and_caps_preserved':True,
        'changed_regions':[{'va':hex(va),'size':len(old),'before':old.hex(),'after':new.hex()} for va,(_,old,new) in changes.items()]}

if __name__=='__main__':
    source=(pe.ROOT/'NewPAL_Release.exe').read_bytes()
    data,plan=candidate(source);OUTDIR.mkdir(parents=True,exist_ok=True)
    (OUTDIR/'NewPAL_Release.native-recovery-v2.exe').write_bytes(data)
    (OUTDIR/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in plan.items() if k!='changed_regions'},ensure_ascii=False))
