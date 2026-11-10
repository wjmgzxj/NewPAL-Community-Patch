# -*- coding: utf-8 -*-
"""Protection window: let an intentional action re-enter combat with a monster.

Baseline : root NewPAL_Release.exe = 4118f872... (c889cd86 + object-split v1,
           installed 2026-11-09 22:20, user confirmed chest/NPC/switch works
           with both mouse and keyboard).
Output   : 补丁工作仓库/候选版本/NewPAL_Release.encounter-manual-reentry-v1.exe

User finding after v1: "无敌期间鼠标键盘都开不了怪" — both the keyboard and
the mouse route still cannot start a fight during the 10s window.

Why both routes:
  gate1 (0x45D3DD) is the scene-encounter flow gate.  encounter-confirmkey-v4
  proved in-game that restoring gate1 to factory behaviour gives
  "confirm key opens chest / confirm key starts fight with monster" while
  "walk into monster / monster chases you" still does NOT start a fight.
  gate3 (0x493736) is the FUN_00493170 scan/click route, shared by chest,
  NPC, switch and monster.  v1 already lets non-0x2000 objects through here.

Design:
  gate1, gate3 -> force CF=0, i.e. hand control back to the untouched factory
                  flow.  Both routes carry their own native input-edge test:
                  gate1 uses the [ebp-1] action-edge built at 0x45D390,
                  gate3 uses the short-press gate at 0x493562..0x4935A2
                  (slot state 1/2 plus a 100ms press window) and the distance
                  filter at 0x4932D3..0x4932F0.
  gate2, gate4 -> keep v1 logic (non-0x2000 passes, 0x2000 stays protected).
                  Walking into a monster and physical collision stay blocked.

No new global state, no input hook, no new press/release stub.  The hold-still
and hold-drag exclusion is delegated to the native edge tests above; those are
the same tests the factory uses, so no guessed click threshold is introduced.
Disable branch (switch off / ten-mile incense) is untouched, so outside the
protection window and with incense the game keeps factory behaviour.

RISK (to be checked in-game): gate1 and gate3 no longer protect on their own
during the window.  v4 only proved gate1-open + gate2/3/4-closed; gate3-open
has no prior in-game evidence.  If walking into a monster turns out to leak
through gate3, roll back to the v1 backup and add a real release-edge check
to gate3 instead.

This script never writes the root EXE.  It only emits a candidate + report.
"""
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "NewPAL_Release.exe"
OUT = ROOT / "补丁工作仓库" / "候选版本" / "NewPAL_Release.encounter-manual-reentry-v1.exe"
REPORT = OUT.with_suffix(".json")

BASE_SHA1 = "4118f872c02fd572798b8a03303b622a8be2accc"
IMAGE_BASE = 0x400000
ORIGIN = 0x5E3120
FREE_END = 0x5E3600
OBJ_BASE = 0x53E8C8
OBJ_STRIDE = 0x48
FLAG_ENCOUNTERABLE = 0x2000

# (site VA of the E9, load-object instruction, kind, label, behaviour)
GATES = (
    (0x5E3057, "8b 45 f4", "index",   "gate1", "allow"),   # 0x45D3DD scene flow
    (0x5E3086, "8b 45 ec", "index",   "gate2", "split"),   # 0x45DE5F front cell
    (0x5E30B5, "8b 45 fc", "pointer", "gate3", "allow"),   # 0x493736 scan/click
    (0x5E30E4, "8b 45 ec", "pointer", "gate4", "split"),   # 0x473863 collision
)


def u32(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


class Asm:
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
    return out


def rva_off(data, rva):
    for _, vs, va, rs, rp in sections(data):
        if va <= rva < va + rs:
            return rp + rva - va
    raise ValueError("RVA not file-backed: " + hex(rva))


def build_payload():
    a = Asm(ORIGIN)

    # helper(eax = object pointer) -> eax = 1 when NOT encounterable
    a.label("helper")
    a.raw("85 c0")
    a.jmp("0f 84", "h_keep")
    a.raw("8b 48 0c")
    a.raw("f7 c1 " + u32(FLAG_ENCOUNTERABLE).hex(" "))
    a.jmp("0f 85", "h_keep")
    a.raw("b8 01 00 00 00")
    a.raw("c3")
    a.label("h_keep")
    a.raw("31 c0")
    a.raw("c3")

    for idx, (site, load, kind, name, behaviour) in enumerate(GATES):
        keep = "keep%d" % (idx + 1)
        allow = "allow%d" % (idx + 1)
        a.label(name)

        if behaviour == "allow":
            # Hand back to the untouched factory flow.  No register/flag state
            # is touched beyond what the original cmp eax,0x2710 would set.
            a.raw("39 c0")                       # cmp eax,eax -> CF=0
            a.jmp("e9", site + 5)
            continue

        a.raw("9c 60")                          # pushfd ; pushal
        a.raw(load)                             # mov eax,[ebp-X]
        if kind == "index":
            a.raw("85 c0")
            a.jmp("0f 88", keep)               # js
            a.raw("3d 00 08 00 00")
            a.jmp("0f 83", keep)               # jae
            a.raw("6b c0 %02x" % OBJ_STRIDE)
            a.raw("05 " + u32(OBJ_BASE).hex(" "))
        a.jmp("e8", "helper")
        a.raw("85 c0")
        a.jmp("0f 85", allow)                  # non-encounterable -> pass
        a.jmp("e9", keep)
        a.label(allow)
        a.raw("61 9d")
        a.raw("39 c0")                          # CF=0
        a.jmp("e9", site + 5)
        a.label(keep)
        a.raw("61 9d")
        a.raw("3d 10 27 00 00")                # original CF
        a.jmp("e9", site + 5)

    blob = a.finish()
    if a.pc > FREE_END:
        raise ValueError("payload exceeds .palrule free run")
    return blob, a.labels


def candidate(source):
    if hashlib.sha1(source).hexdigest() != BASE_SHA1:
        raise ValueError("root EXE is not the installed object-split v1")
    payload, symbols = build_payload()
    data = bytearray(source)

    patches = {}
    for site, _, _, name, _ in GATES:
        o = rva_off(source, site - IMAGE_BASE)
        if source[o] != 0xE9:
            raise ValueError("expected v1 E9 at " + hex(site))
        if source[o + 5] != 0xE9:
            raise ValueError("missing return jump at " + hex(site + 5))
        patch = bytes([0xE9]) + u32(symbols[name] - site - 5)
        data[o:o + 5] = patch
        patches[hex(site)] = patch.hex(" ")

    # Clear the whole free run before writing, so no stale v1 payload remains.
    o = rva_off(source, ORIGIN - IMAGE_BASE)
    end = o + (FREE_END - ORIGIN)
    data[o:end] = bytes(FREE_END - ORIGIN)
    data[o:o + len(payload)] = payload
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
        "format": "encounter-manual-reentry-v1",
        "status": "candidate only; NOT installed; gameplay pending",
        "baseline_sha1": BASE_SHA1,
        "baseline_note": "c889cd86 clean baseline + object-split v1 (chest/NPC/switch user-verified)",
        "candidate_sha1": hashlib.sha1(out).hexdigest(),
        "candidate_sha256": hashlib.sha256(out).hexdigest(),
        "size": len(out),
        "changed_byte_count_vs_installed": len(diff),
        "changed_ranges_file_offset": [(hex(a), hex(b)) for a, b in groups[:20]],
        "patches": patches,
        "payload": {
            "origin": hex(ORIGIN),
            "size": len(payload),
            "free_run_end": hex(FREE_END),
            "symbols": {k: hex(v) for k, v in symbols.items()},
        },
        "gate_behaviour": {
            "gate1_0x45D3DD": "force CF=0 -> factory scene flow (keyboard confirm)",
            "gate2_0x45DE5F": "v1 split: non-0x2000 pass, 0x2000 protected",
            "gate3_0x493736": "force CF=0 -> factory scan/click flow (mouse)",
            "gate4_0x473863": "v1 split: non-0x2000 pass, 0x2000 protected",
        },
        "native_edge_tests_relied_on": [
            "gate1 [ebp-1] action edge at 0x45D390..0x45D3D9",
            "gate3 short-press gate 0x493562..0x4935A2 (slot state 1/2, 100ms)",
            "gate3 distance filter 0x4932D3..0x4932F0",
        ],
        "untouched": [
            "root EXE", "front/middle stubs (incl. NMT1 lease)",
            "disable branch (switch off / ten-mile incense)",
            "glow / cursor / white flash", "native input chain",
            "timestamp 0x52C144", "switch 0x5E8700", "save data", "resources",
        ],
        "risk": "gate1+gate3 no longer protect during the window. v4 only "
                "proved gate1-open with gate2/3/4 closed; gate3-open has no "
                "prior in-game evidence. If walking into a monster leaks "
                "through gate3, roll back to the v1 backup and add a real "
                "release-edge check instead.",
        "verification_limit": "Byte-level and disassembly checks only. Not gameplay evidence.",
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nROOT EXE UNCHANGED sha1", hashlib.sha1(EXE.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
