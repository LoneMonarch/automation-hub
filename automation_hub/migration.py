"""Explicit, read-only import of legacy configuration and report evidence."""
import json
from pathlib import Path
from automation_hub.storage import QueueLock, now


def migrate(store, folder, save_credentials):
    root = Path(folder)
    config = json.loads((root/'config.json').read_text(encoding='utf-8'))
    login = config.get('login',{})
    settings = config.get('settings',{})
    account = login.get('username','')
    if account and login.get('password'):
        save_credentials(account,login['password'])
    with QueueLock(store.root):
        store.put('account',account)
        store.put('settings:help2rent',dict(login_url=login.get('url','https://www.help2rent.co.uk/login'),upload_url=config.get('upload_url','https://www.help2rent.co.uk/email/marketing/contact'),tag=settings.get('tag_to_select',''),officer=settings.get('officer_to_select',''),timeout=settings.get('timeout_seconds',30)))
        count = 0
        with store.db:
            for report in sorted((root/'contacts-to-upload'/'reports').glob('*.csv')):
                if report.name.startswith('._'):
                    continue
                store.db.execute('INSERT OR REPLACE INTO historical VALUES (?,?,?)',(str(report),report.read_text(encoding='utf-8-sig'),now()))
                count += 1
    return count
