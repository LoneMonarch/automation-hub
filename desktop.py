"""Packaged desktop entry point; workers use the same executable."""
import sys
import os
from pathlib import Path

if __name__ == '__main__':
    if getattr(sys, 'frozen', False):
        binary_dir = Path(sys.executable).parent
        browser_dir = binary_dir.parent / 'Resources' / 'browsers' if sys.platform == 'darwin' else binary_dir / 'browsers'
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(browser_dir)
    if '--worker' in sys.argv:
        from automation_hub.worker import main
    else:
        from automation_hub.ui import main
    sys.exit(main())
