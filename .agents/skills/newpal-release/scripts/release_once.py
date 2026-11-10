"""Content-bound evidence receipts and reusable ZIPs. Never tests or uploads."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import shutil
import tempfile
import zipfile
import zlib


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source(root, name):
    p = root / name
    if p.is_symlink() or root not in p.resolve().parents or not p.is_file():
        raise ValueError('Input must be a regular file inside the selected root')
    for parent in p.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('Linked input directory is not allowed')
    return p


def checks(a):
    plan = load(a.plan)
    ledger = load(a.ledger, {'schema': 1, 'checks': {}})
    signatures, hashes = {}, {}
    for row in plan['checks']:
        if row['id'] in signatures or not row['method'] or not row['files']:
            raise ValueError('Checks need unique IDs, a method and explicit inputs')
        for name in set(row['files'] + row.get('method_files', [])):
            if name not in hashes:
                hashes[name] = sha(source(a.root.resolve(), name))
        signatures[row['id']] = key([row['method'], sorted(
            (n, hashes[n]) for n in set(row['files'] + row.get('method_files', [])))])
    if a.command == 'record':
        if a.check not in signatures or not a.evidence.is_file() or not a.evidence.stat().st_size:
            raise ValueError('Provide a defined check and actual nonempty evidence file')
        ledger['checks'][a.check] = dict(input=signatures[a.check], result=a.result,
                                        evidence=str(a.evidence.resolve()), evidence_sha256=sha(a.evidence))
        save(a.ledger, ledger)
    result = {}
    for name, signature in signatures.items():
        old = ledger['checks'].get(name, {})
        proof = Path(old.get('evidence', ''))
        valid = (old.get('result') == 'pass' and old.get('input') == signature and
                 proof.is_file() and sha(proof) == old.get('evidence_sha256'))
        result[name] = 'reusable' if valid else 'needs-check'
    return dict(checks=result, executed_tests=False)


def pack(a):
    plan = load(a.manifest)
    rows, sources = [], {}
    for item in plan['entries']:
        name = item['name']
        rel = PurePosixPath(name)
        if (not name or '\\' in name or rel.is_absolute() or '..' in rel.parts or ':' in name or
                str(rel) != name or name.casefold() in sources):
            raise ValueError('Invalid or duplicate ZIP member')
        p = source(a.root.resolve(), item['source'])
        sources[name.casefold()] = p
        rows.append(dict(name=name, bytes=p.stat().st_size, sha256=sha(p)))
    if not rows:
        raise ValueError('Empty package')
    rows.sort(key=lambda row: row['name'])
    method = [sha(Path(__file__)), platform.python_version(), zlib.ZLIB_VERSION, 'fixed-zip-v1']
    signature = key([plan['version'], rows, method])
    old = load(a.receipt, {})
    if a.output.exists():
        if old.get('input') == signature and sha(a.output) == old.get('sha256'):
            return dict(status='reused', sha256=old['sha256'], members=len(rows))
        raise ValueError('Existing package differs or lacks matching receipt; use a new candidate output')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release-', dir=a.output.parent) as tmp:
        archive_path = Path(tmp) / 'package.zip'
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for row in rows:
                info = zipfile.ZipInfo(row['name'], date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                with z.open(info, 'w') as dst, sources[row['name'].casefold()].open('rb') as src:
                    shutil.copyfileobj(src, dst)
        with zipfile.ZipFile(archive_path) as z:
            if z.namelist() != [row['name'] for row in rows]:
                raise ValueError('ZIP member mismatch')
            for row in rows:
                h = hashlib.sha256()
                with z.open(row['name']) as member:
                    for chunk in iter(lambda: member.read(1024 * 1024), b''):
                        h.update(chunk)  # Reading to EOF also checks ZIP CRC.
                if h.hexdigest() != row['sha256'] or z.getinfo(row['name']).file_size != row['bytes']:
                    raise ValueError('ZIP content mismatch or source changed while packaging')
        digest = sha(archive_path)
        with a.output.open('xb') as dst, archive_path.open('rb') as src:
            shutil.copyfileobj(src, dst)
    save(a.receipt, dict(schema=1, version=plan['version'], input=signature, sha256=digest,
                         bytes=a.output.stat().st_size, members=rows, method=method, privacy_checked=False))
    return dict(status='packed', sha256=digest, members=len(rows))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ['status', 'record', 'pack']:
        cmd = sub.add_parser(name)
        cmd.add_argument('--root', type=Path, required=True)
        for option in (['manifest', 'output', 'receipt'] if name == 'pack' else ['plan', 'ledger']):
            cmd.add_argument('--' + option, type=Path, required=True)
        if name == 'record':
            cmd.add_argument('--check', required=True)
            cmd.add_argument('--result', choices=['pass', 'fail'], required=True)
            cmd.add_argument('--evidence', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(pack(a) if a.command == 'pack' else checks(a), ensure_ascii=False))


if __name__ == '__main__':
    main()
