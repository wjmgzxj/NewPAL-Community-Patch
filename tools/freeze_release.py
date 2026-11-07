"""Freeze or verify an explicit public snapshot. Does not upload anything."""
import argparse
import hashlib
import json
from pathlib import Path

SKIP = {'.git', '__pycache__', '.local', '.venv', 'node_modules', 'private-audit'}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--assets', type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = root / 'public-files.json'
    rows = []
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root)
        if any(x in SKIP for x in rel.parts) or p == manifest or not p.is_file():
            continue
        if p.is_symlink():
            raise ValueError('Public snapshot must not include symlinks: ' + rel.as_posix())
        if p.suffix.lower() in {'.exe', '.dll', '.pyd', '.sav', '.dmp', '.pfx', '.p12', '.key', '.log'} or p.name.startswith('.env'):
            raise ValueError('Unexpected public source file: ' + rel.as_posix())
        rows.append({'path': rel.as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)})
    current = {'version': json.loads((root/'baseline.json').read_text(encoding='utf-8'))['version'], 'files': rows}
    if args.check:
        assert json.loads(manifest.read_text(encoding='utf-8')) == current, 'Public snapshot changed'
    else:
        manifest.write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    if args.assets:
        lines = [sha(p) + '  ' + p.name for p in sorted(args.assets.glob('*.zip'))]
        target = args.assets / 'SHA256SUMS.txt'
        expected = '\n'.join(lines) + '\n'
        if args.check:
            assert target.read_text(encoding='utf-8') == expected, 'Attachment checksums changed'
        else:
            target.write_text(expected, encoding='utf-8', newline='\n')
    print(json.dumps({'snapshot_files': len(rows), 'status': 'verified' if args.check else 'frozen'}))


if __name__ == '__main__':
    main()
