"""Build a self-contained distribution. Never packages local project data."""
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

if __name__ != '__main__':
    raise SystemExit('Run this script directly.')

root=Path(__file__).resolve().parents[1]
browser_dir = root / 'build' / 'browsers'
env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(browser_dir),
           PYINSTALLER_CONFIG_DIR=str(root / 'build' / 'pyinstaller-cache'))
subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], cwd=root, env=env, check=True)
# A previous developer install may have put a browser inside Playwright's
# package directory. The release keeps its tested browser in browser_dir and
# copies it beside the executable, so remove this redundant generated cache
# before PyInstaller scans package data.
playwright_local_browsers = Path(sys.prefix) / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages' / 'playwright' / 'driver' / 'package' / '.local-browsers'
if playwright_local_browsers.exists():
    shutil.rmtree(playwright_local_browsers)
# External macOS volumes can create AppleDouble ``._*`` metadata beside files
# in Chromium's framework bundle. PyInstaller mistakes those metadata entries
# for malformed framework contents, so remove them from this generated cache.
if sys.platform == 'darwin':
    subprocess.run(['dot_clean','-m',str(browser_dir)],check=True)
    # Some removable/exFAT volumes retain the AppleDouble sidecars even after
    # dot_clean. They are metadata, not application files, and can make
    # PyInstaller parse a fake ``._*.framework`` entry as a real framework.
    for generated_root in (browser_dir,Path(sys.prefix)):
        subprocess.run(
            ['find',str(generated_root),'-depth','-name','._*','-delete'],
            check=True,
        )
subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', str(root / 'packaging' / 'AutomationHub.spec')], cwd=root, env=env, check=True)
if sys.platform=='darwin':
    app = root / 'dist' / 'Automation Hub.app'
    # Sign and image on the native temporary filesystem. Removable/exFAT
    # project drives create AppleDouble sidecars while signing, which can make
    # an otherwise valid app fail verification.
    with tempfile.TemporaryDirectory(prefix='automationhub-release-') as stage:
        staged_app = Path(stage) / 'Automation Hub.app'
        shutil.copytree(app,staged_app,symlinks=True,ignore=shutil.ignore_patterns('._*'))
        shutil.copytree(browser_dir,staged_app / 'Contents' / 'Resources' / 'browsers',symlinks=True,ignore=shutil.ignore_patterns('.links','._*'))
        subprocess.run(['find',str(staged_app),'-depth','-name','._*','-delete'],check=True)
        subprocess.run(['codesign','--force','--deep','--sign','-',str(staged_app)],check=True)
        subprocess.run(['codesign','--verify','--deep','--strict','--verbose=2',str(staged_app)],check=True)
        subprocess.run(['hdiutil','create','-volname','Automation Hub','-srcfolder',str(staged_app),'-ov','-format','UDZO',str(root/'dist'/'AutomationHub-macOS.dmg')],check=True)
elif sys.platform=='win32':
    shutil.copytree(browser_dir, root / 'dist' / 'AutomationHub' / 'browsers', ignore=shutil.ignore_patterns('.links'))
    compiler=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Inno Setup 6'/'ISCC.exe'
    subprocess.run([str(compiler),str(root/'packaging'/'windows.iss')],check=True)
