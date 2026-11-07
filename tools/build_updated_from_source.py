"""Rebuild the three v0.3.1 additions on the frozen v0.3.0 base, never install.

Earlier features still use a frozen delta; this is not an all-feature source build.
Requires the exact supported Steam original and MSVC x86 build tools.
"""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--original', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--msvc-tools', type=Path, required=True,
                    help='MSVC bin/Hostx64/x86 directory containing cl.exe and link.exe')
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'baseline.json').read_text(encoding='utf-8'))
    original = args.original.read_bytes()
    assert digest(original) == manifest['original_sha256'], 'Unsupported original'
    assert args.output.resolve() != args.original.parent.resolve(), 'Separate output required'
    assert not args.output.exists() or not any(args.output.iterdir()), 'Output must be empty'
    for name in ('cl.exe', 'link.exe'):
        assert (args.msvc_tools / name).is_file(), 'Missing MSVC x86 tool: ' + name
    packed = (root / 'patch/v0.3.0-baseline.json.gz').read_bytes()
    assert digest(packed) == '1c32914f48cb049e60a3e016946ae3b5c76d36eb26d6d7e342474d7a48535920'
    base = json.loads(gzip.decompress(packed))
    data = bytearray(original)
    end = 0
    for row in base['spans']:
        at = row['offset']
        old = base64.b64decode(row['old'], validate=True)
        new = base64.b64decode(row['new'], validate=True)
        assert at >= end and old and len(old) == len(new) and original[at:at+len(old)] == old
        data[at:at+len(old)] = new
        end = at + len(old)
    data.extend(base64.b64decode(base['tail'], validate=True))
    data = bytes(data)
    assert digest(data) == base['target_sha256']
    sys.path.insert(0, str(root / '补丁工作仓库/脚本'))
    import postbattle_native_recovery_v2 as recovery
    import postbattle_popup_skip_v1 as popup
    import gu_batch_v6 as gu
    data, recovery_plan = recovery.candidate(data)
    data, popup_plan = popup.candidate(data)
    # Build artifacts remain outside tracked sources and the user's game.
    build_parent = root / '.local'
    build_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gu-source-', dir=build_parent) as temp:
        gu.OUT = Path(temp)
        gu.TOOLS = args.msvc_tools.resolve()
        data, gu_plan = gu.candidate(data)
    assert digest(data) == manifest['target_sha256'], 'Source build differs from frozen release'
    for row in manifest['resources']:
        assert digest((root / row['path']).read_bytes()) == row['sha256']
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'NewPAL_Release.exe').write_bytes(data)
    (args.output / 'gu-build-plan.json').write_text(json.dumps(gu_plan, indent=2) + '\n', encoding='utf-8')
    for row in manifest['resources']:
        dest = args.output / row['path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / row['path'], dest)
    print(json.dumps({'sha256': digest(data), 'runtime_pngs': len(manifest['resources']),
                      'source_stages': ['native-recovery-v2', 'postbattle-popup-skip-v1', 'gu-batch-v6'],
                      'earlier_features': 'frozen v0.3.0 delta', 'installed': False}))


if __name__ == '__main__':
    main()
