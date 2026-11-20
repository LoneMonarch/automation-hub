"""Build modules from an explicitly selected source directory, never the project root."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from automation_hub.modules import validate_manifest


def build(source, output):
    source=Path(source).resolve(); output=Path(output).resolve()
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    files={}
    for path in source.rglob('*'):
        relative=path.relative_to(source)
        if any(part.startswith('.') or part in ('__pycache__','venv','node_modules') for part in relative.parts): continue
        if path.is_symlink(): raise ValueError('Symlinks are not allowed in module packages')
        if path.is_file() and path.name!='manifest.json' and path != output:
            if path.suffix.lower() in ('.xlsx','.xls','.sqlite','.log','.pyc') or path.name=='config.json':
                raise ValueError('Do not package private data or configuration: '+str(relative))
            files[relative.as_posix()]=path.read_bytes()
    manifest['files']={name:hashlib.sha256(content).hexdigest() for name,content in files.items()}
    validate_manifest(manifest,compatible=False)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest,indent=2))
        for name,content in sorted(files.items()): z.writestr(name,content)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('source'); parser.add_argument('output')
    args=parser.parse_args(); print(build(args.source,args.output))
