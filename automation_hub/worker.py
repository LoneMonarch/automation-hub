"""Isolated worker protocol: one JSON request on stdin, JSON events on stdout."""
import json
import sys
import threading
import time
from dataclasses import asdict
from automation_hub.storage import Store, QueueLock
from automation_hub.modules import ModuleManager


def emit(event, **values):
    print(json.dumps(dict(event=event,**values)),flush=True)


class Controls:
    def __init__(self):
        self.paused = False
        self.stopped = False

    def listen(self):
        for line in sys.stdin:
            try:
                command = json.loads(line).get('command')
                if command == 'pause': self.paused = True
                if command == 'resume': self.paused = False
                if command == 'stop': self.stopped = True
            except ValueError:
                pass

    def checkpoint(self):
        while self.paused and not self.stopped:
            time.sleep(.15)
        return not self.stopped


def run_queue(store, module, ident, credentials, controls, emit_event=emit):
    opened = False
    current_settings = None
    try:
        for row in store.rows(ident):
            if row['state'] not in ('queued','validating','submitting','verifying','needs_review'):
                continue
            if not controls.checkpoint():
                break
            job = store.job(row['id'])
            settings = json.loads(job['settings'])
            uncertain = job['state'] in ('submitting','verifying','needs_review')
            try:
                if settings.get('account') and settings['account'] != credentials.get('username'):
                    raise ValueError('This queue belongs to a different account. Sign in with the account used when it was created.')
                if not opened or settings != current_settings:
                    if opened:
                        module.close()
                    module.open(settings,credentials)
                    opened = True
                    current_settings = settings
                if uncertain:
                    result = module.reconcile(job)
                else:
                    store.transition(job['id'],'validating',error='')
                    error = module.validate(job['path'])
                    if error:
                        store.transition(job['id'],'failed',error=error)
                        emit_event('progress',job=store.job(job['id']))
                        continue
                    name,baseline = module.prepare(job)
                    # Persist before submitting, including every identifier seen before the click.
                    store.transition(job['id'],'submitting',name=name,baseline=json.dumps(baseline),attempts=job['attempts']+1)
                    job = store.job(job['id'])
                    emit_event('progress',job=job)
                    try:
                        result = module.submit(job)
                    except Exception:
                        store.transition(job['id'],'verifying')
                        result = module.reconcile(job)
                if result.state not in ('completed','failed','needs_review'):
                    raise ValueError('Module returned an invalid outcome')
                store.transition(job['id'],result.state,remote_id=result.remote_id,verification=result.verification,error=result.error)
                emit_event('progress',job=store.job(job['id']))
                if result.state == 'needs_review':
                    emit_event('notice',message='A submission needs review. The queue has stopped without retrying it.')
                    break
            except Exception as e:
                state = store.job(job['id'])['state']
                if state != 'completed':
                    store.transition(job['id'],'needs_review' if state in ('submitting','verifying','needs_review') else 'queued',error=str(e))
                emit_event('error',message=str(e))
                break
    finally:
        try:
            module.close()
        except Exception:
            pass


def main():
    request = json.loads(sys.stdin.readline())
    store = Store(request.get('root'))
    controls = Controls()
    threading.Thread(target=controls.listen,daemon=True).start()
    try:
        with QueueLock(store.root):
            module = ModuleManager(store).load(request['module'])
            action = request.get('action','run')
            if action == 'describe':
                emit('description',settings=module.describe_settings())
            elif action == 'preview':
                rows = []
                for path in request['files']:
                    rows.append(dict(file=path,name=module.preview(path,request['settings']),error=module.validate(path)))
                emit('preview',rows=rows)
            elif action == 'options':
                try:
                    module.open(request['settings'],request['credentials'])
                    emit('options',choices=module.options())
                finally:
                    module.close()
            else:
                run_queue(store,module,request['module'],request.get('credentials',{}),controls)
        emit('finished')
        return 0
    except Exception as e:
        emit('error',message=str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
