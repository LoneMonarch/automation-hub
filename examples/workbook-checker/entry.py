"""Offline example module demonstrating the complete v1 contract."""
from pathlib import Path
from automation_hub.api import Result
from automation_hub.builtin.help2rent import Help2Rent

class WorkbookChecker:
    def describe_settings(self): return []
    def validate(self,path): return Help2Rent().validate(path)
    def preview(self,path,settings): return Path(path).name
    def open(self,settings,credentials): pass
    def prepare(self,job): return Path(job['path']).name,{}
    def submit(self,job): return Result('completed',verification='workbook_integrity_checked')
    def reconcile(self,job):
        error=self.validate(job['path'])
        return Result('failed',error=error) if error else Result('completed',verification='workbook_integrity_checked')
    def close(self): pass

def create_module(): return WorkbookChecker()
