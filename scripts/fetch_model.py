"""Download the approved upstream model without running upstream code."""
from pathlib import Path
from urllib.request import urlopen, Request
from concurrent.futures import ThreadPoolExecutor
import re, json, hashlib
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'source-model'
OUT.mkdir(exist_ok=True)
BASE='https://neuromechfly.org/wasm/viewer/assets/'
def fetch(url, path):
    data=urlopen(Request(url,headers={'User-Agent':'FlyCoRobinhood local research prototype'}),timeout=60).read()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    return {'url':url,'file':str(path.relative_to(ROOT)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
manifest=[fetch(BASE+'model/fly.xml',OUT/'fly.xml'),fetch(BASE+'model_meta.json',OUT/'model_meta.json'),fetch('https://neuromechfly.org/wasm/game/assets/model_meta.json',OUT/'game_meta.json')]
files=sorted(set(re.findall(r'<mesh[^>]*file="([^"]+)"',(OUT/'fly.xml').read_text())))
with ThreadPoolExecutor(8) as pool:
    manifest.extend(pool.map(lambda name:fetch(BASE+'model/'+name,OUT/name),files))
license_path=ROOT/'public'/'licenses'/'NeuroMechFly-Apache-2.0.txt'
manifest.append(fetch('https://raw.githubusercontent.com/NeLy-EPFL/flygym/main/LICENSE',license_path))
(ROOT/'source-model'/'manifest.json').write_text(json.dumps(manifest,indent=2))
print('DOWNLOADED',len(files),'original STL meshes;',sum(x['bytes'] for x in manifest),'bytes; SHA256 manifest written')
