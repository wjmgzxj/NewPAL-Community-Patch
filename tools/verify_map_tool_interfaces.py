"""Read-only file/interface regression. No process connection or game launch."""
import argparse
import json
from pathlib import Path
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--exe', type=Path, required=True, action='append')
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / '补丁工作仓库/脚本'))
    from map_test_compat_v2 import select_contract, validate_runtime
    import flash_v4 as pe
    rules = json.loads((root / 'tool-data/传送接口兼容规则.json').read_text(encoding='utf-8'))
    cases = []
    for file in args.exe:
        raw = file.read_bytes()
        contract = select_contract(raw, rules)
        assert select_contract(raw + b'UNRELATED-OVERLAY', rules)['label'] == contract['label']
        rejected = 0
        for region in contract['regions']:
            modified = bytearray(raw)
            at = pe.rva_offset(raw, region['rva'])
            modified[at] ^= 128
            try:
                select_contract(modified, rules)
            except ValueError:
                rejected += 1
            else:
                raise AssertionError('Changed protected region was accepted')
        regions = {(r['rva'], len(bytes.fromhex(r['bytes']))): bytes.fromhex(r['bytes'])
                   for r in contract['regions'] if not r.get('attach_owned')}
        validate_runtime(lambda rva, n: regions[(rva, n)], 0x400000, contract)
        cases.append({'interface': contract['label'], 'rejected_regions': rejected})
    print(json.dumps({'status': 'passed; file and simulated runtime only', 'cases': cases}, ensure_ascii=False))


if __name__ == '__main__':
    main()
