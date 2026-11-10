"""Build the v0.3.2 additions from an exact v0.3.1 checkpoint; never install.

Uses final approved PNG alpha/atlas data without regenerating art or fonts.
Older features remain the documented frozen/partial-source baseline.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

BASE='e0b4be9d7958ab7b9620326b834498d0e24be9a80203c25212e07075c1812a12'
TARGET='4067f280219357317ae2806163930f922303314cbf8e1543aa7e757f179c5d2e'


def digest(data):return hashlib.sha256(data).hexdigest()


def apply(source,root):
    assert digest(source)==BASE,'Expected exact v0.3.1 checkpoint'
    sys.path.insert(0,str(root/'补丁工作仓库/脚本'))
    from PIL import Image
    import shilipo_runtime_v1 as shilipo
    import encounter_object_split_v1 as split
    import encounter_manual_reentry_v1 as reentry
    import settle_message_skip_v5 as settle
    stages=[]
    with tempfile.TemporaryDirectory(prefix='newpal-map-') as folder:
        folder=Path(folder)
        shutil.copy2(root/'补丁工作仓库/候选版本/shilipo-map-v1/atlas.json',folder/'atlas.json')
        masks=[]
        for scene in shilipo.SCENES:
            with Image.open(root/f'Resource/np_sp_road_{scene}_v1.png') as image:
                assert image.size==(640,480)
                masks.append(image.convert('RGBA').getchannel('A').tobytes())
        (folder/'alpha.bin').write_bytes(b''.join(masks))
        saved=shilipo.OUT
        try:
            shilipo.OUT=folder
            source,_=shilipo.candidate(source)
        finally:shilipo.OUT=saved
    expected='5694641891f75dfdd0e04f24f0e181c6cf6229a33b412ba605b41a9050d7ef15'
    assert digest(source)==expected,'Final Shilipo atlas/alpha stage differs: '+digest(source)
    stages.append({'stage':'shilipo-map-v1','sha256':digest(source)})
    source,*_=split.candidate(source)
    assert digest(source)=='c8bc09e57e15a6cfb5cc2fba897feee10ba1d87ef14cda61313a65f33b43908a'
    stages.append({'stage':'encounter-object-split-v1','sha256':digest(source)})
    source,*_=reentry.candidate(source)
    assert digest(source)=='3421c9a01d05544042b01c3dbeeb04266884d286e3c2153f82591ed2714c23a0'
    stages.append({'stage':'encounter-manual-reentry-v1','sha256':digest(source)})
    source,_=settle.candidate(source)
    assert digest(source)==TARGET,'Stable settlement stage differs: '+digest(source)
    stages.append({'stage':'settle-message-skip-v5','sha256':digest(source)})
    return source,stages


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-v031',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    assert a.output.resolve()!=a.base_v031.parent.resolve(),'Separate output required'
    assert not a.output.exists() or not any(a.output.iterdir()),'Output must be empty'
    data,stages=apply(a.base_v031.read_bytes(),root)
    manifest=json.loads((root/'baseline.json').read_text(encoding='utf-8'))
    for row in manifest['resources']:
        assert digest((root/row['path']).read_bytes())==row['sha256']
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'NewPAL_Release.exe').write_bytes(data)
    for row in manifest['resources']:
        target=a.output/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/row['path'],target)
    report={'status':'source additions rebuilt exactly; not installed','target_sha256':digest(data),'stages':stages,'runtime_pngs':len(manifest['resources'])}
    (a.output/'source-stages.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
