# Build on the target OS. Browsers are copied beside the frozen app by
# tools/build_app.py, so do not let Playwright's hook bundle a second copy.
from importlib.metadata import distributions
import sys
from pathlib import Path
from automation_hub import __version__ as app_version
root = Path(SPECPATH).parent
hidden = ['automation_hub.worker','automation_hub.builtin.help2rent',
          'keyring.backends.macOS' if sys.platform == 'darwin' else 'keyring.backends.Windows']
notices = [(str(root/'THIRD_PARTY_NOTICES.md'),'.')]
for distribution in distributions():
    for file in distribution.files or ():
        path = Path(str(file))
        if '.dist-info' in str(path.parent) and path.name.lower().startswith(('license','licence','notice','copying')):
            notices.append((str(distribution.locate_file(file)), 'licenses/' + distribution.metadata['Name']))
a = Analysis([str(root/'desktop.py')], pathex=[str(root)],
    binaries=[], datas=notices, hiddenimports=hidden,
    hookspath=[], excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtPdf'], noarchive=False)
def is_runtime_file(entry):
    return not any('.local-browsers' in str(value).replace('\\','/').split('/') for value in entry[:2])
a.binaries = [entry for entry in a.binaries if is_runtime_file(entry)]
a.datas = [entry for entry in a.datas if is_runtime_file(entry)]
pyz = PYZ(a.pure)
worker = EXE(pyz,a.scripts,[],exclude_binaries=True,name='AutomationHubWorker',console=True)
app = EXE(pyz,a.scripts,[],exclude_binaries=True,name='AutomationHub',console=False)
collection = COLLECT(app,worker,a.binaries,a.datas,strip=False,upx=False,name='AutomationHub')
if sys.platform == 'darwin':
    bundle = BUNDLE(collection,name='Automation Hub.app',bundle_identifier='local.automationhub.desktop',
        info_plist={'NSHighResolutionCapable':True,'LSMinimumSystemVersion':'14.0',
                    'CFBundleShortVersionString':app_version,'CFBundleVersion':app_version})
