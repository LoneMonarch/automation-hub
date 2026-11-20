"""Versioned, offline module packages and cached HTTPS catalogue."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen
import zipfile
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from automation_hub import __version__
from automation_hub.storage import QueueLock, digest

PLATFORM = {'darwin':'macos','win32':'windows'}.get(sys.platform, sys.platform)
BUILTIN = dict(id='help2rent',name='Help2Rent Contact Uploader',version='1.0.4',
    released='2026-11-18',summary='Upload Excel contact lists with resumable progress.',
    description='Select spreadsheets, preview list names, then upload to Help2Rent. Originals are preserved. Requires an internet connection and a Help2Rent account. Verification confirms list creation, not every imported contact.',
    platforms=['windows','macos'],api_version=1,host_version='>=1.0,<2',dependencies=[],entrypoint='entry.py',release_notes='Passed a live upload of Erith.xlsx as Erith upload 2. Prevents Chromium first-run and sign-in prompts from appearing during uploads. Retains the high-contrast light theme, verified login-field replacement, and step-by-step tutorial.')


def safe_path(value):
    p = PurePosixPath(value)
    if not value or '\\' in value or ':' in value or p.is_absolute() or any(part in ('..','.') for part in value.split('/')):
        raise ValueError('Unsafe package path: '+value)
    if any(part.endswith((' ','.')) or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} for part in p.parts):
        raise ValueError('Unsupported Windows package path: '+value)
    return p


def validate_manifest(m, compatible=True):
    for key in ('id','name','version','released','summary','description','platforms','api_version','host_version','dependencies','entrypoint','files'):
        if key not in m:
            raise ValueError('Module manifest is missing '+key)
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',m['id']):
        raise ValueError('Invalid module ID')
    Version(m['version'])
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',m['version']):
        raise ValueError('Use a three-part module version, for example 1.0.0')
    safe_path(m['entrypoint'])
    if m['entrypoint'] not in m['files']:
        raise ValueError('Entry point is missing from file hashes')
    if compatible and (m['api_version'] != 1 or PLATFORM not in m['platforms'] or Version(__version__) not in SpecifierSet(m['host_version'])):
        raise ValueError('This module needs a different app version or operating system.')
    if not isinstance(m['dependencies'],list):
        raise ValueError('Dependencies must be a list of bundled dependency descriptions.')
    for name, value in m['files'].items():
        safe_path(name)
        if not re.fullmatch(r'[a-f0-9]{64}',value):
            raise ValueError('Invalid SHA-256 file hash')
    return m


def atomic_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2),encoding='utf-8')
    os.replace(tmp,path)


class ModuleManager:
    def __init__(self, store):
        self.store = store
        self.root = store.root / 'modules'
        self.root.mkdir(exist_ok=True)
        self.index = self.root / 'installed.json'

    def installed(self):
        return json.loads(self.index.read_text(encoding='utf-8')) if self.index.exists() else {}

    def manifests(self):
        result = {BUILTIN['id']:BUILTIN}
        for ident,item in self.installed().items():
            result[ident] = json.loads((self.root / ident / item['active'] / 'manifest.json').read_text(encoding='utf-8'))
        return list(result.values())

    def inspect(self, archive):
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            if sum(i.file_size for i in infos) > 512*1024*1024 or len(infos)>10000:
                raise ValueError('Module package is too large')
            names = set()
            for i in infos:
                safe_path(i.filename.rstrip('/'))
                if stat.S_ISLNK(i.external_attr >> 16):
                    raise ValueError('Module packages cannot contain symbolic links')
                key = i.filename.casefold()
                if key in names:
                    raise ValueError('Duplicate package path')
                names.add(key)
            m = validate_manifest(json.loads(z.read('manifest.json')))
            actual = {i.filename for i in infos if not i.is_dir()} - {'manifest.json'}
            if actual != set(m['files']):
                raise ValueError('Package contents do not match the manifest')
            for name, expected in m['files'].items():
                if hashlib.sha256(z.read(name)).hexdigest() != expected:
                    raise ValueError('Module file checksum mismatch: '+name)
            return m

    def install(self, archive):
        with QueueLock(self.store.root):
            m = self.inspect(archive)
            index = self.installed()
            old = index.get(m['id'],{}).get('active')
            target = self.root / m['id'] / m['version']
            if old == m['version']:
                raise ValueError('This module version is already installed.')
            target.parent.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.root) as temp:
                stage = Path(temp) / 'package'
                stage.mkdir()
                with zipfile.ZipFile(archive) as z:
                    z.extractall(stage)
                if target.exists():
                    retained = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
                    if retained != m or any(digest(target / name) != expected for name, expected in m['files'].items()):
                        raise ValueError('A different package already uses this version. Publish a new version.')
                else:
                    os.replace(stage,target)
            index[m['id']] = {'active':m['version'],'previous':old}
            atomic_json(self.index,index)
            return m

    def rollback(self, ident):
        with QueueLock(self.store.root):
            index = self.installed()
            item = index.get(ident,{})
            if not item.get('previous'):
                raise ValueError('No previous version is available.')
            item['active'],item['previous'] = item['previous'],item['active']
            atomic_json(self.index,index)

    def uninstall(self, ident):
        with QueueLock(self.store.root):
            index = self.installed()
            if ident not in index:
                raise ValueError('The bundled uploader cannot be removed.')
            del index[ident]
            atomic_json(self.index,index)
            # Retain package files and all job data; only deactivate executable code.

    def load(self, ident):
        item = self.installed().get(ident)
        if not item and ident == 'help2rent':
            from automation_hub.builtin.help2rent import Help2Rent
            return Help2Rent()
        if not item:
            raise ValueError('Module is not installed')
        folder = self.root / ident / item['active']
        m = validate_manifest(json.loads((folder/'manifest.json').read_text(encoding='utf-8')))
        for name,expected in m['files'].items():
            if digest(folder/name) != expected:
                raise ValueError('Installed module was changed. Install a new verified package.')
        sys.path.insert(0,str(folder/'vendor'))
        sys.path.insert(0,str(folder))
        spec = importlib.util.spec_from_file_location('hub_plugin_'+ident.replace('-','_'),folder/m['entrypoint'])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.create_module()


def fetch_https(url, limit=20*1024*1024):
    if urlparse(url).scheme != 'https':
        raise ValueError('Catalogue and download addresses must use HTTPS.')
    with urlopen(url,timeout=30) as response:
        if urlparse(response.url).scheme != 'https':
            raise ValueError('Insecure download redirect')
        result = response.read(limit+1)
    if len(result)>limit:
        raise ValueError('Download exceeds size limit')
    return result


class Catalogue:
    def __init__(self, store):
        self.store = store
        self.cache = store.root/'catalogue.json'

    def cached(self):
        return json.loads(self.cache.read_text(encoding='utf-8')) if self.cache.exists() else {'schema_version':1,'modules':[]}

    def refresh(self):
        url = self.store.get('catalogue_url','')
        if not url:
            raise ValueError('No catalogue configured. You can still install a module from a file.')
        data = json.loads(fetch_https(url))
        if data.get('schema_version') != 1 or not isinstance(data.get('modules'),list):
            raise ValueError('Unsupported catalogue format')
        for item in data['modules']:
            validate_manifest(item)
            if urlparse(item.get('download_url','')).scheme != 'https' or not re.fullmatch(r'[a-f0-9]{64}',item.get('sha256','')):
                raise ValueError('Invalid catalogue download metadata')
        atomic_json(self.cache,data)
        return data

    def install(self, item):
        content = fetch_https(item['download_url'],512*1024*1024)
        if hashlib.sha256(content).hexdigest() != item['sha256']:
            raise ValueError('Download checksum mismatch. Nothing was installed.')
        with tempfile.TemporaryDirectory(dir=self.store.root) as temp:
            path = Path(temp)/'module.zip'
            path.write_bytes(content)
            manager = ModuleManager(self.store)
            m = manager.inspect(path)
            if (m['id'],m['version']) != (item['id'],item['version']):
                raise ValueError('Downloaded module does not match the catalogue.')
            return manager.install(path)
