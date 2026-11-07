"""Portable subset of bounded x86 regression checks, not live gameplay QA.

Needs Unicorn and the EXE/gu-build-plan.json from build_updated_from_source.py.
No test saves, personal original backups or old candidate EXEs are required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--built', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / '补丁工作仓库/脚本'))
    from gu_test_fixtures_v6 import Machine, NativeNames, NativeSelect, NativeRefresh
    manifest = json.loads((root / 'baseline.json').read_text(encoding='utf-8'))
    data = (args.built / 'NewPAL_Release.exe').read_bytes()
    assert hashlib.sha256(data).hexdigest() == manifest['target_sha256']
    plan = json.loads((args.built / 'gu-build-plan.json').read_text(encoding='utf-8'))
    assert plan['candidate_sha256'] == manifest['target_sha256']
    checks = []
    m = NativeNames(data, plan, {100: 9, 101: 9})
    assert m.call(0x4f8450, [0x7f100000]) == 0
    assert m.call('GuBuild', [2]) == 2
    checks.append('valid zero group index and native cached name lookup')
    m = Machine(data, plan, {100: 8, 101: 3})
    assert m.call('GuBuild', [99]) == 4
    m = Machine(data, plan, {100: 7}, {(100, 100): 200})
    m.w(0x58151c, 100)
    assert m.call('GuBuild', [99]) == 4
    checks.append('unequal and identical ingredient limits include reserved slots')
    m = Machine(data, plan, {100: 9, 101: 9, 200: 99})
    assert m.call('GuBuild', [99]) == 0
    checks.append('output capacity rejection before consumption')
    for fail in range(1, 7):
        m = Machine(data, plan, {100: 9, 101: 9})
        m.prep(3)
        before = m.bag.copy()
        m.fail_at = fail
        assert m.call('GuCommit') == 0 and +m.bag == +before
    checks.append('six transaction abort and rollback positions')
    m = NativeSelect(data, plan, {101: 5})
    m.click()
    assert not m.button_visible()
    m.click()
    assert m.button_visible() and m.bag[101] == 5
    m.w(0x59a3ac, 1)
    m.advance_and_button()
    assert m.r(0x581518) == 101 and m.bag[101] == 4
    checks.append('native first-entry mouse sequence and one reserved ingredient')
    m = NativeRefresh(data, plan, {100: 9, 101: 9})
    m.call('GuInput', [10])
    m.slot(2, 2)
    m.slot(4, 2)
    m.confirm = 1
    m.call('GuInput', [10])
    m.confirm = 0
    m.call(0x4bba50)
    for step in range(10):
        m.call(0x4b7b70)
        assert all((m.flags[m.objects[key]+0x28] & 1) == 0 for key in (0x642, 0x643))
        assert (m.r(m.objects[0x642]+8), m.r(m.objects[0x643]+8)) == (40+16*step, 360-16*step)
        m.paint_order.clear()
        m.call('GuDraw')
        assert m.paint_order == ['cursor']
    m.call(0x4b7b70)
    assert m.r(0x581518) == 200 and m.bag[200] == 1
    checks.append('native refresh, visible ten-step merge, hidden overlay, delayed batch completion')
    m = Machine(data, plan, {100: 9, 101: 9})
    m.call('GuDraw')
    assert m.paint_order[-1] == 'cursor' and m.paint_order.count('cursor') == 1
    checks.append('new image/text layers precede a single original cursor call')
    print(json.dumps({'status': 'passed', 'checks': checks,
                      'limits': 'Private list/UI/input/inventory substitutes; native instruction blocks execute; no live game or GPU.'}))


if __name__ == '__main__':
    main()
