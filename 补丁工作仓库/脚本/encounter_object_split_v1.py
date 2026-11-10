# -*- coding: utf-8 -*-
"""Post-battle protection: let non-encounterable objects through all four gates.

Baseline : <game-directory>\\NewPAL_Release.exe
           sha1 c889cd86ede9c3904490fab147e8e5d6187fa08c (十里坡地图完成版)
Output   : 补丁工作仓库/候选版本/NewPAL_Release.encounter-object-split-v1.exe

Design (read-only, no new global state, no input hooks):

  The four shared compare blocks each end their "protection active" branch with
      pop eax ; cmp eax,0x2710 ; jmp <stub>
  and the whole 10s interception is decided by the CF that cmp produces.
  incense_link_v1.py already shipped the exact same "conditional bypass" shape
  (E9 over the 5-byte cmp, gate ends with jmp site+5).  Reuse it.

  Each gate reads the current object's [obj+0xC] flags.  0x2000 is the native
  "encounterable" bit (REVERSE_NOTES_EN.md:196, 新仙剑逆向情报.md:198);
  0x8000 is the scan bit shared by chests/NPC/monsters.  When the object does
  NOT carry 0x2000, force CF=0 so the original flow proceeds (chest / talk /
  switch works during the protection window).  When it does, fall back to the
  untouched "cmp eax,0x2710" so monsters stay blocked.

  Anything uncertain (null pointer, out-of-range index, unreadable flags) also
  falls back to the original protection.  Failure direction is "still
  protected", never "encounter leaks through".

Object provenance at gate time (disassembled from this exact baseline):
  gate1 [ebp-0xC]   index   -> 0x53E8C8 + i*0x48 + 0xC
  gate2 [ebp-0x14]  index   -> 0x53E8C8 + i*0x48 + 0xC
  gate3 [ebp-4]     pointer -> [ptr+0xC]
  gate4 [ebp-0x14]  pointer -> [ptr+0xC]

This script never writes the root EXE.  It only emits a candidate + report.
"""
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "NewPAL_Release.exe"
OUT = ROOT / "补丁工作仓库" / "候选版本" / "NewPAL_Release.encounter-object-split-v1.exe"
REPORT = OUT.with_suffix(".json")

BASE_SHA1 = "c889cd86ede9c3904490fab147e8e5d6187fa08c"
IMAGE_BASE = 0x400000
ORIGIN = 0x5E3120                 # free run 0x5E3117..0x5E3600 in .palrule
FREE_END = 0x5E3600
OBJ_BASE = 0x53E8C8
OBJ_STRIDE = 0x48
FLAG_ENCOUNTERABLE = 0x2000

# (cmp site VA, load-object instruction, kind, label)
GATES = (
    (0x5E3057, "8b 45 f4", "index",   "gate1"),   # [ebp-0xC]
    (0x5E3086, "8b 45 ec", "index",   "gate2"),   # [ebp-0x14]
    (0x5E30B5, "8b 45 fc", "pointer", "gate3"),   # [ebp-4]
    (0x5E30E4, "8b 45 ec", "pointer", "gate4"),   # [ebp-0x14]
)
CMP_BYTES = bytes.fromhex("3d 10 27 00 00")       # cmp eax,0x2710


def u32(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


class Asm:
    """Minimal two-pass builder; near jumps are always 32-bit relative."""
    def __init__(self, origin):
        self.origin = origin
        self.buf = bytearray()
        self.labels = {}
        self.fixups = []

    @property
    def pc(self):
        return self.origin + len(self.buf)

    def raw(self, value):
        self.buf.extend(bytes.fromhex(value) if isinstance(value, str) else value)

    def label(self, name):
        if name in self.labels:
            raise ValueError("duplicate label " + name)
        self.labels[name] = self.pc

    def jmp(self, opcode, target):
        self.raw(opcode)
        self.fixups.append((len(self.buf), target))
        self.raw(b"\x00" * 4)

    def finish(self):
        for pos, target in self.fixups:
            addr = self.labels[target] if isinstance(target, str) else target
            self.buf[pos:pos + 4] = u32(addr - (self.origin + pos + 4))
        return bytes(self.buf)


def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    n = struct.unpack_from("<H", data, pe + 6)[0]
    opt = pe + 24
    size_opt = struct.unpack_from("<H", data, pe + 20)[0]
    out = []
    for i in range(n):
        p = opt + size_opt + i * 40
        name, vs, va, rs, rp = struct.unpack_from("<8sIIII", data, p)
        out.append((name.rstrip(b"\0").decode("latin1"), vs, va, rs, rp))
    return pe, opt, out


def rva_off(data, rva):
    for _, vs, va, rs, rp in sections(data)[2]:
        if va <= rva < va + rs:
            return rp + rva - va
    raise ValueError("RVA not file-backed: " + hex(rva))


def build_payload():
    a = Asm(ORIGIN)

    # helper(eax = object pointer) -> eax = 1 when the object is NOT encounterable.
    a.label("helper")
    a.raw("85 c0")                          # test eax,eax
    a.jmp("0f 84", "h_keep")               # jz  -> keep protection
    a.raw("8b 48 0c")                      # mov ecx,[eax+0xC]
    a.raw("f7 c1 " + u32(FLAG_ENCOUNTERABLE).hex(" "))   # test ecx,0x2000
    a.jmp("0f 85", "h_keep")               # jnz -> keep protection
    a.raw("b8 01 00 00 00")                # mov eax,1
    a.raw("c3")
    a.label("h_keep")
    a.raw("31 c0")                          # xor eax,eax
    a.raw("c3")

    for idx, (site, load, kind, name) in enumerate(GATES):
        keep = "keep%d" % (idx + 1)
        a.label(name)
        a.raw("9c 60")                      # pushfd ; pushal
        a.raw(load)                         # mov eax,[ebp-X]
        if kind == "index":
            a.raw("85 c0")                  # test eax,eax
            a.jmp("0f 88", keep)           # js  -> keep
            a.raw("3d 00 08 00 00")        # cmp eax,0x800
            a.jmp("0f 83", keep)           # jae -> keep
            a.raw("6b c0 %02x" % OBJ_STRIDE)                 # imul eax,eax,0x48
            a.raw("05 " + u32(OBJ_BASE).hex(" "))            # add eax,0x53E8C8
        a.jmp("e8", "helper")
        a.raw("85 c0")                      # test eax,eax
        a.jmp("0f 84", keep)               # jz  -> keep
        a.raw("61 9d")                      # popal ; popfd
        a.raw("39 c0")                      # cmp eax,eax  -> CF=0 (bypass)
        a.jmp("e9", site + 5)
        a.label(keep)
        a.raw("61 9d")                      # popal ; popfd
        a.raw(CMP_BYTES.hex(" "))           # cmp eax,0x2710 -> original CF
        a.jmp("e9", site + 5)

    blob = a.finish()
    if a.pc > FREE_END:
        raise ValueError("payload exceeds .palrule free run")
    return blob, a.labels


def candidate(source):
    if hashlib.sha1(source).hexdigest() != BASE_SHA1:
        raise ValueError("root EXE is not the c889cd86 baseline")
    payload, symbols = build_payload()

    data = bytearray(source)
    patches = {}
    for site, _, _, name in GATES:
        o = rva_off(source, site - IMAGE_BASE)
        if source[o:o + 5] != CMP_BYTES:
            raise ValueError("compare bytes differ at " + hex(site))
        # the five bytes after the cmp must stay the original E9 back to the stub
        if source[o + 5] != 0xE9:
            raise ValueError("missing return jump at " + hex(site + 5))
        patch = bytes([0xE9]) + u32(symbols[name] - site - 5)
        data[o:o + 5] = patch
        patches[hex(site)] = patch.hex(" ")

    o = rva_off(source, ORIGIN - IMAGE_BASE)
    end = o + len(payload)
    if any(data[o:end]):
        raise ValueError(".palrule target region is not zero-filled")
    data[o:end] = payload
    return bytes(data), payload, patches, symbols


def main():
    source = EXE.read_bytes()
    out, payload, patches, symbols = candidate(source)

    diff = [i for i, (x, y) in enumerate(zip(source, out)) if x != y]
    groups = []
    for i in diff:
        if groups and i == groups[-1][1]:
            groups[-1][1] = i + 1
        else:
            groups.append([i, i + 1])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(out)
    report = {
        "format": "encounter-object-split-v1",
        "status": "candidate only; NOT installed; gameplay pending",
        "baseline_sha1": BASE_SHA1,
        "baseline_sha256": hashlib.sha256(source).hexdigest(),
        "candidate_sha1": hashlib.sha1(out).hexdigest(),
        "candidate_sha256": hashlib.sha256(out).hexdigest(),
        "size": len(out),
        "changed_byte_count": len(diff),
        "changed_ranges_file_offset": [(hex(a), hex(b)) for a, b in groups],
        "patches": patches,
        "payload": {
            "origin": hex(ORIGIN),
            "size": len(payload),
            "free_run_end": hex(FREE_END),
            "symbols": {k: hex(v) for k, v in symbols.items()},
        },
        "rule": "0x2000 absent -> force CF=0 (native flow proceeds); "
                "0x2000 present / unknown -> original cmp eax,0x2710",
        "untouched": [
            "root EXE", "four front stubs", "four middle stubs (NMT1 lease)",
            "disable-branch compares", "glow / cursor / white flash",
            "native input chain", "factory bytes at 0x45D3DD / 0x45DE5F / 0x473863 / 0x493736",
            "timestamp 0x52C144", "switch 0x5E8700", "save data", "resources",
        ],
        "scope_note": "This candidate addresses chest/NPC/switch availability during "
                      "the 10s window. Active single-click re-encounter is deliberately "
                      "NOT included; it belongs to a separate step after gameplay check.",
        "verification_limit": "Byte-level and disassembly checks only. No Unicorn "
                              "result is claimed as gameplay evidence.",
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nROOT EXE UNCHANGED sha1", hashlib.sha1(EXE.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
