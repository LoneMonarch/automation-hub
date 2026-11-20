"""Generate a GitHub-release-compatible catalogue from module packages."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from urllib.parse import quote

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--base-url',required=True); p.add_argument('--output',required=True); p.add_argument('packages',nargs='+'); args=p.parse_args()
    if not args.base_url.startswith('https://'): p.error('Use an HTTPS release asset base URL')
    modules=[]
    for filename in args.packages:
        path=Path(filename)
        with zipfile.ZipFile(path) as z: item=json.loads(z.read('manifest.json'))
        item.update(download_url=args.base_url.rstrip('/')+'/'+quote(path.name),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        modules.append(item)
    Path(args.output).write_text(json.dumps(dict(schema_version=1,modules=modules),indent=2),encoding='utf-8')
