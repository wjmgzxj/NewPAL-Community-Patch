"""十里坡单图：第三套独立地图 payload（运行时揭雾/独立探索/存档绑定）。

复用 luocha_return_runtime_v1.payload() 的 profile 链式接入（荷花池就是第二套）。
只追加新节数据并改写 5 个地图钩子；梦境/再入罗刹/荷花三套既有 payload 逐字节不变。
不安装、不写正常存档、不启动或控制游戏。
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import flash_v4 as pe
import luocha_return_runtime_v1 as shared

W = pe.ROOT / "补丁工作仓库"
CASE = W / "地图开发/逐图开发/04_十里坡"
FIXED = CASE / "固定UI层"
UI = CASE / "UI与连线"
OUT = W / "候选版本/shilipo-map-v1"
RES = OUT / "Resource"
N = 640 * 480
COUNT = 3
TOTAL = N * COUNT
MAGIC = int.from_bytes(b"NSP1", "little")
ALPHA_OFFSET = (0x10000 + TOTAL + 28 + 0xFFF) & ~0xFFF
SIZE = (ALPHA_OFFSET + TOTAL + 0xFFF) & ~0xFFF
NAMESPACE = "np_shilipo_%d.dat"
BASE = "2558a78380b079caf4d26ad0899eb04e8fcc4f7e"  # 当前状态.json installed_development.sha1
SCENES = [17, 18, 817]
GRID = (120, 90)
PREVIOUS_NAME = "map-nameplates-v1"  # 当前 EXE 的地图链末端（荷花池）符号来源

load = shared.saved
dump = lambda p, r: p.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
sha = lambda b: hashlib.sha256(b).hexdigest()


def compositor():
    """Reuse the approved preview's fit_content() so runtime art matches it exactly."""
    path = CASE / "合成完整预览.py"
    spec = importlib.util.spec_from_file_location("shilipo_compositor", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def font(size):
    for c in ["C:/Windows/Fonts/simkai.ttf", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"]:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def assets():
    OUT.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    comp = compositor()
    terrain = Image.open(CASE / "地形层_用户抠图.png").convert("RGBA")
    s, nw, nh, ox, oy, bbox = comp.fit_content(terrain, comp.DRAW_BOX,
                                               scale_boost=comp.SCALE_BOOST,
                                               shift=(comp.SHIFT_X, comp.SHIFT_Y))
    placed = terrain.resize((nw, nh), Image.Resampling.LANCZOS)
    arr = np.array(placed)
    overlay_arr = np.zeros((480, 640, 4), np.uint8)
    sx, sy = max(0, ox), max(0, oy)
    ex, ey = min(640, ox + nw), min(480, oy + nh)
    overlay_arr[sy:ey, sx:ex] = arr[sy - oy:ey - oy, sx - ox:ex - ox]

    # Base UI is exactly the user-reviewed paper: no terrain, no player, no port
    # numbers. Port destinations are still unknown and numbering would be an
    # unconfirmed art change (and would be covered by the terrain overlay anyway).
    paper = Image.open(FIXED / "00_纸面_原样复用.png").convert("RGBA")
    base = paper.copy()
    base.alpha_composite(Image.open(FIXED / "02_标题区覆盖_纸纹补丁.png").convert("RGBA"))
    base.alpha_composite(Image.open(FIXED / "01_标题_十里坡_透明层.png").convert("RGBA"))
    base.alpha_composite(Image.open(FIXED / "04_共用底部提示_透明层.png").convert("RGBA"))
    transform = json.loads((UI / "页面变换.json").read_text(encoding="utf-8"))
    assert transform["draw_port_numbers"] is False
    t = transform["transform"]
    rows = []
    for i, scene in enumerate(SCENES):
        b = f"np_sp_base_{scene}_v1.png"
        o = f"np_sp_road_{scene}_v1.png"
        base.save(RES / b)
        Image.fromarray(overlay_arr, "RGBA").save(RES / o)
        rows.append(dict(index=i, scene=scene, width=GRID[0], height=GRID[1],
                         tx=t["tx"], ty=t["ty"], numerator=t["numerator"], denominator=1000,
                         page=0, family=0, base=b, overlay=o, ports={}))
    # payload() hardcodes the shared 25px player widget name.
    player = pe.ROOT / "Resource/np_lr_player_v1.png"
    assert player.exists()
    shutil.copy2(player, RES / player.name)

    alpha = overlay_arr[:, :, 3].tobytes()
    (OUT / "alpha.bin").write_bytes(alpha * COUNT)
    assert len((OUT / "alpha.bin").read_bytes()) == TOTAL
    dump(OUT / "atlas.json", dict(rows=rows, links=[], pages=1,
                                  note="single shared display layer; three independent fog masks"))
    manifest = [dict(path="Resource/" + p.name, sha256=sha(p.read_bytes()), size=p.stat().st_size)
                for p in sorted(RES.glob("*.png"))]
    dump(OUT / "assets.json", manifest)
    dump(OUT / "placement.json", dict(terrain=str(CASE / "地形层_用户抠图.png"),
                                      terrain_sha256=sha((CASE / "地形层_用户抠图.png").read_bytes()),
                                      scale=s, placed_size=[nw, nh], origin=[ox, oy],
                                      alpha_bbox=bbox, scale_boost=comp.SCALE_BOOST,
                                      shift=[comp.SHIFT_X, comp.SHIFT_Y],
                                      overlay_alpha_sha256=sha(alpha)))
    return rows


def hook_sites():
    old = load("dungeon-map-v2")
    paint = load("painted-map-v1")
    return [(old["symbols"]["context"], "context_dispatch", 0xE9, 10),
            (paint["symbols"]["frame"], "frame", 0xE9, 7),
            (paint["symbols"]["write_sidecar"], "write_wrapper", 0xE9, 5),
            (0x4B589A, "load_wrapper", 0xE8, 5),
            (0x4691A0, "reset_wrapper", 0xE9, 6)]


def candidate(source):
    assert hashlib.sha1(source).hexdigest() == BASE, "current installed EXE identity differs"
    rows = json.loads((OUT / "atlas.json").read_text(encoding="utf-8"))["rows"]
    links = []
    prev = load(PREVIOUS_NAME)
    lotus = prev["lotus"]["symbols"]
    previous = dict(symbols={k: lotus[k] for k in
                             ("context_dispatch", "frame", "write_wrapper", "load_wrapper", "reset_wrapper")})
    profile = dict(count=COUNT, size=SIZE, magic=MAGIC, namespace=NAMESPACE,
                   alpha_offset=ALPHA_OFFSET, out=OUT, previous=previous,
                   exclusive_scene=True, sample_during_events=False)
    h, o, secs = pe.pe_info(source)
    last = secs[-1]
    assert last[4] + last[3] == len(source), "last section does not end at EOF"
    origin = pe.IMAGE_BASE + last[2] + last[3]
    p = shared.payload(origin, source, rows, links, profile)

    out = bytearray(source)
    out.extend(p["blob"])
    patches = []
    for site, key, kind, length in hook_sites():
        offset = pe.rva_offset(source, site - pe.IMAGE_BASE)
        before = bytes(source[offset:offset + length])
        expected = pe.branch(kind, site, lotus[key]) + b"\x90" * (length - 5)
        assert before == expected, ("hook differs", hex(site), before.hex(), expected.hex())
        after = pe.branch(kind, site, p["symbols"][key]) + b"\x90" * (length - 5)
        out[offset:offset + length] = after
        patches.append(dict(site=site, offset=offset, kind=hex(kind), key=key,
                            before=before.hex(), after=after.hex()))
    # The sixth (dream nameplate draw) hook belongs to the cave chain and stays put.
    walk = load("walk-fog-v2")
    draw_hook = pe.rva_offset(source, walk["symbols"]["draw"] - pe.IMAGE_BASE)
    assert bytes(source[draw_hook:draw_hook + 5]) == bytes(out[draw_hook:draw_hook + 5])

    sh = o + struct.unpack_from("<H", source, h + 20)[0] + (len(secs) - 1) * 40
    size = last[3] + SIZE
    for at in (sh + 8, sh + 16):
        struct.pack_into("<I", out, at, size)
    for at, value in ((o + 56, last[2] + size),
                      (o + 4, struct.unpack_from("<I", source, o + 4)[0] + SIZE),
                      (o + 64, 0)):
        struct.pack_into("<I", out, at, value)
    assert len(out) == len(source) + SIZE
    plan = dict(origin=origin, payload_span=[len(source), len(source) + SIZE], size=SIZE,
                alpha_offset=ALPHA_OFFSET, magic=MAGIC, namespace=NAMESPACE,
                header_offsets=[sh + 8, sh + 16, o + 56, o + 4, o + 64],
                rows=rows, hooks=patches, state=p["state"], symbols=p["symbols"],
                code_size=p["code_size"], previous_symbols=previous["symbols"],
                previous_name=PREVIOUS_NAME, brush=p["brush"], mask_data=p["mask_data"],
                record=p["record"], alpha=p["alpha"], ids=p["ids"], ptrs=p["ptrs"],
                dirty=p["dirty"])
    return bytes(out), plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path)
    args = ap.parse_args()
    rows = assets()
    source = (pe.ROOT / "NewPAL_Release.exe").read_bytes() if args.source is None else args.source.read_bytes()
    target, plan = candidate(source)
    (OUT / "NewPAL_Release.exe").write_bytes(target)
    # 本脚本在验证之前运行；若已有与本次候选同哈希的离线验证结果，状态就如实写成
    # 「离线已通过」，不再停在 pending。哈希不匹配时仍保持 pending，避免拿旧结论顶替。
    evidence = OUT / "verification.json"
    verified = False
    if evidence.exists():
        v = json.loads(evidence.read_text(encoding="utf-8"))
        verified = (v.get("candidate_sha1") == hashlib.sha1(target).hexdigest()
                    and v.get("status") == "passed; user gameplay verification pending")
    report = dict(status=("candidate; offline verification passed; installation and gameplay pending"
                          if verified else "candidate; offline verification pending"),
                  baseline_sha1=BASE, candidate_sha1=hashlib.sha1(target).hexdigest(),
                  candidate_sha256=sha(target), candidate_size=len(target),
                  pages=1, independent_fog_records=COUNT,
                  save_namespace=f"{NAMESPACE} / NSP1", scenes=SCENES,
                  offline_verified=verified,
                  native_saves_modified=False, installed=False, gameplay_tested=False,
                  **{k: v for k, v in plan.items()})
    dump(OUT / "candidate.json", report)
    print(json.dumps(dict(candidate_sha1=report["candidate_sha1"], code_size=plan["code_size"],
                          append_bytes=SIZE, resources=len(rows) * 2 + 1, scenes=SCENES), ensure_ascii=False))


if __name__ == "__main__":
    main()
