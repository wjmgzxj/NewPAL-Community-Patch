"""Rebuild from public sources and the verified release's embedded data.

Only extracts data from the given tool; never executes that file or opens a game.
Requires PyInstaller and pefile. Existing previews are reused without resampling.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-from-tool', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--extract-only', action='store_true')
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root / 'tool-baseline.json').read_text(encoding='utf-8'))
    if hashlib.sha256(args.data_from_tool.read_bytes()).hexdigest() != baseline['sha256']:
        raise ValueError('Use the verified tool named in tool-baseline.json')
    out = args.output.resolve()
    if out == root or root in out.parents or out == args.data_from_tool.resolve().parent:
        raise ValueError('Use a separate empty output directory outside the source and downloaded tool folder')
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty')
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(args.data_from_tool.resolve()))
    count = 0
    for name in archive.toc:
        normalized = name.replace('\\', '/')
        if not normalized.startswith('work/'):
            continue
        rel = PurePosixPath(normalized)
        if rel.is_absolute() or '..' in rel.parts or any(':' in part for part in rel.parts):
            raise ValueError('Invalid embedded data path')
        dest = out / 'bundle' / Path(*rel.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(archive.extract(name))
        count += 1
    rules = out / 'bundle/work/地图开发/地图测试工具/传送接口兼容规则.json'
    expected = (root / 'tool-data/传送接口兼容规则.json').read_bytes()
    if not rules.exists() or rules.read_bytes() != expected:
        raise ValueError('Embedded interface rules differ from the public source snapshot')
    if args.extract_only:
        print(json.dumps({'data_files': count, 'executed_tool': False}))
        return
    scripts = root / '补丁工作仓库/脚本'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--onefile', '--windowed', '--noupx', '--name', '新仙剑地图传送器',
                    '--paths', str(scripts), '--add-data', str(out / 'bundle/work') + ';work',
                    '--distpath', str(out / 'dist'), '--workpath', str(out / 'build'),
                    '--specpath', str(out), str(scripts / 'map_test_exe_entry_v1.py')], check=True)
    print('Rebuilt tool in output/dist. Hash may differ with environment; use hidden self-check before connecting.')


if __name__ == '__main__':
    main()
