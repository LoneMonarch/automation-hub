"""Exercise the packaged worker without an account or website connection."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
worker = (root / 'dist' / 'Automation Hub.app' / 'Contents' / 'MacOS' / 'AutomationHubWorker'
          if sys.platform == 'darwin' else root / 'dist' / 'AutomationHub' / 'AutomationHubWorker.exe')
with tempfile.TemporaryDirectory() as data:
    request = dict(root=data, module='help2rent', action='describe')
    result = subprocess.run([str(worker), '--worker'], input=json.dumps(request) + '\n',
                            text=True, capture_output=True, timeout=30, check=True)
    events = [json.loads(line) for line in result.stdout.splitlines()]
    if not any(event['event'] == 'description' for event in events):
        raise RuntimeError('Packaged worker did not return the Help2Rent settings')
    print('Packaged worker started and returned Help2Rent settings.')
