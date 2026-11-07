"""Package the exact current patch and optional verified tester; never install or upload.

First reconstruct your own current EXE with build_current.py. This packages the
frozen release, not a full source compilation. Art source ZIP is maintained separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game-exe', type=Path, required=True)
    ap.add_argument('--map-tester', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / 'baseline.json').read_text(encoding='utf-8'))
    assert sha(args.game_exe) == data['target_sha256'], 'Not the exact current release EXE'
    for row in data['resources']:
        assert sha(root / row['path']) == row['sha256'], 'Resource mismatch: ' + row['path']
    if args.map_tester:
        expected = json.loads((root / 'tool-baseline.json').read_text(encoding='utf-8'))
        assert sha(args.map_tester) == expected['sha256'], 'Unknown tester binary'
    args.output.mkdir(parents=True, exist_ok=True)

    def notices(z, prefix):
        z.write(root / 'THIRD_PARTY.md', prefix + '/THIRD_PARTY.md')
        for path in sorted((root / 'third_party').rglob('*')):
            if path.is_file():
                z.write(path, prefix + '/third_party/' + path.relative_to(root / 'third_party').as_posix())

    with zipfile.ZipFile(args.output / ('NewPAL_Patch_'+data['version']+'.zip'), 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        prefix = 'NewPAL_Patch'
        z.write(args.game_exe, prefix + '/NewPAL_Release.exe')
        for row in data['resources']:
            z.write(root / row['path'], prefix + '/' + row['path'])
        for src, dest in [('docs/安装与还原.md', '安装与还原.md'), ('docs/功能与状态.md', '功能与状态.md'),
                          ('LICENSE.md', 'LICENSE.md'), ('baseline.json', '资源与版本清单.json')]:
            z.write(root / src, prefix + '/' + dest)
        notices(z, prefix)
    if args.map_tester:
        with zipfile.ZipFile(args.output / ('NewPAL_MapTester_'+data['version']+'.zip'), 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            prefix = 'NewPAL_MapTester'
            z.write(args.map_tester, prefix + '/新仙剑地图传送器.exe')
            z.write(root / 'docs/工具说明.md', prefix + '/工具说明.md')
            z.write(root / 'LICENSE.md', prefix + '/项目自有内容许可.md')
            notices(z, prefix)
    for path in args.output.glob('*.zip'):
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None, 'Corrupt ZIP: ' + path.name
    print('Exact release packaged. Freeze checksums and perform the privacy review before upload.')


if __name__ == '__main__':
    main()
