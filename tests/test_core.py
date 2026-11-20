import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from automation_hub.storage import Store, QueueLock
from automation_hub.modules import ModuleManager, Catalogue, BUILTIN, PLATFORM
from automation_hub.worker import run_queue, Controls
from automation_hub.api import Result
from automation_hub.builtin.help2rent import Help2Rent


def workbook(path):
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>'); z.writestr('xl/workbook.xml','<workbook/>')
    return path


def package(path, version='1.0.0', **extra):
    code = b'def create_module():\n    return object()\n'
    manifest = dict(BUILTIN,id='example',version=version,files={'entry.py':hashlib.sha256(code).hexdigest()},**extra)
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('manifest.json',json.dumps(manifest)); z.writestr('entry.py',code)
    return path


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root/'data')
        self.file = workbook(self.root/'Résumé contacts.xlsx')
        self.manager = ModuleManager(self.store)
    def tearDown(self):
        self.store.db.close(); self.temp.cleanup()
    def enqueue(self):
        self.store.enqueue('help2rent',[self.file],{'tag':'31','officer':'7'})
        return self.store.rows()[0]
    def test_copy_and_duplicate_scope(self):
        self.enqueue()
        self.assertTrue(self.file.exists())
        self.assertEqual(self.store.enqueue('help2rent',[self.file],{'tag':'31','officer':'7'}),(0,1))
        self.assertEqual(self.store.enqueue('help2rent',[self.file],{'tag':'32','officer':'7'}),(1,0))
        self.assertEqual(self.store.enqueue('help2rent',[self.file],{'tag':'31','officer':'7'},again=True),(1,0))
    def test_readonly_original_and_same_filename(self):
        self.file.chmod(0o444)
        row=self.enqueue(); self.assertTrue(Path(row['path']).exists())
        second=self.root/'sub'; second.mkdir(); other=workbook(second/self.file.name)
        self.store.enqueue('help2rent',[other],{},again=True)
        self.assertNotEqual(self.store.rows()[0]['path'],self.store.rows()[1]['path'])
    def test_persistence_and_report(self):
        row=self.enqueue(); self.store.transition(row['id'],'completed',remote_id='123',verification='list_creation_confirmed')
        other=Store(self.store.root); self.assertEqual(other.job(row['id'])['remote_id'],'123'); other.db.close()
        self.store.export(self.root/'report.csv')
        with open(self.root/'report.csv',encoding='utf-8-sig') as f: self.assertEqual(list(csv.DictReader(f))[0]['state'],'completed')
    def test_queue_lock(self):
        with QueueLock(self.store.root):
            with self.assertRaises(RuntimeError):
                with QueueLock(self.store.root): pass
        with QueueLock(self.store.root): pass
    def test_install_update_rollback_uninstall_preserves_jobs(self):
        self.enqueue()
        self.manager.install(package(self.root/'one.zip'))
        self.manager.install(package(self.root/'two.zip','1.1.0'))
        self.assertEqual(self.manager.installed()['example']['active'],'1.1.0')
        self.manager.rollback('example')
        self.assertEqual(self.manager.installed()['example']['active'],'1.0.0')
        self.manager.uninstall('example'); self.assertEqual(len(self.store.rows()),1)
    def test_install_blocked_during_job(self):
        p=package(self.root/'one.zip')
        with QueueLock(self.store.root):
            with self.assertRaises(RuntimeError): self.manager.install(p)
    def test_bad_hash(self):
        p=package(self.root/'one.zip')
        with zipfile.ZipFile(p,'a') as z: z.writestr('extra.py','bad')
        with self.assertRaises(ValueError): self.manager.install(p)
        self.assertEqual(self.manager.installed(),{})
    def test_traversal(self):
        p=package(self.root/'one.zip')
        with zipfile.ZipFile(p,'a') as z: z.writestr('../escape','no')
        with self.assertRaises(ValueError): self.manager.install(p)
        self.assertFalse((self.root/'escape').exists())
    def test_incompatible(self):
        p=package(self.root/'one.zip',host_version='>=99')
        with self.assertRaises(ValueError): self.manager.install(p)
    def test_interrupted_update_preserves_active(self):
        self.manager.install(package(self.root/'one.zip'))
        with patch('automation_hub.modules.os.replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.manager.install(package(self.root/'two.zip','1.1.0'))
        self.assertEqual(self.manager.installed()['example']['active'],'1.0.0')
    def test_cached_catalogue_offline(self):
        catalogue=Catalogue(self.store)
        catalogue.cache.write_text(json.dumps({'schema_version':1,'modules':[]}))
        self.assertEqual(catalogue.cached()['modules'],[])
        with self.assertRaises(ValueError): catalogue.refresh()
    def test_workbook_validation(self):
        mod=Help2Rent(); self.assertEqual(mod.validate(self.file),'')
        self.assertTrue(mod.validate(self.root/'~$temp.xlsx'))
        corrupt=self.root/'bad.xlsx'; corrupt.write_text('bad'); self.assertTrue(mod.validate(corrupt))


class FakeModule:
    def __init__(self, mode='ok'):
        self.mode=mode; self.submissions=0; self.reconciliations=0
    def open(self,*args): pass
    def close(self): pass
    def validate(self,path): return ''
    def prepare(self,job): return 'Test upload',{'old':'Existing'}
    def submit(self,job):
        self.submissions+=1
        if self.mode=='crash': raise ConnectionError('lost response')
        return Result('completed','new','list_creation_confirmed')
    def reconcile(self,job):
        self.reconciliations+=1
        return Result('completed','new','list_creation_confirmed') if self.mode!='uncertain' else Result('needs_review',error='unknown')


class RecoveryTests(unittest.TestCase):
    setUp = CoreTests.setUp
    tearDown = CoreTests.tearDown
    enqueue = CoreTests.enqueue
    def test_response_lost_reconciles_once(self):
        self.enqueue(); mod=FakeModule('crash')
        run_queue(self.store,mod,'help2rent',{},Controls(),lambda *a,**k:None)
        self.assertEqual(mod.submissions,1); self.assertEqual(mod.reconciliations,1)
        self.assertEqual(self.store.rows()[0]['state'],'completed')
    def test_restart_never_resubmits_uncertain(self):
        row=self.enqueue(); self.store.transition(row['id'],'submitting',name='Test upload',baseline='{}')
        mod=FakeModule('uncertain')
        run_queue(self.store,mod,'help2rent',{},Controls(),lambda *a,**k:None)
        self.assertEqual(mod.submissions,0); self.assertEqual(self.store.rows()[0]['state'],'needs_review')
    def test_stop_preserves_pending(self):
        self.enqueue(); controls=Controls(); controls.stopped=True; mod=FakeModule()
        run_queue(self.store,mod,'help2rent',{},controls,lambda *a,**k:None)
        self.assertEqual(mod.submissions,0); self.assertEqual(self.store.rows()[0]['state'],'queued')
    def test_completed_not_repeated(self):
        row=self.enqueue(); self.store.transition(row['id'],'completed'); mod=FakeModule()
        run_queue(self.store,mod,'help2rent',{},Controls(),lambda *a,**k:None)
        self.assertEqual(mod.submissions,0)
    def test_local_failure_does_not_resubmit(self):
        self.enqueue(); mod=FakeModule()
        def broken(*a,**k):
            if k.get('job',{}).get('state')=='completed': raise OSError('report unavailable')
        run_queue(self.store,mod,'help2rent',{},Controls(),broken)
        self.assertEqual(mod.submissions,1)
        # A completed remote outcome must survive a subsequent reporting exception.
        self.assertEqual(self.store.rows()[0]['state'],'completed')


if __name__=='__main__': unittest.main()
