import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import unittest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication
from automation_hub.ui import Window, apply_light_theme


class UITests(unittest.TestCase):
    def test_first_run_and_worker_description(self):
        app=QApplication.instance() or QApplication([])
        apply_light_theme(app)
        self.assertLess(app.palette().color(QPalette.ColorRole.WindowText).lightness(),100)
        self.assertGreater(app.palette().color(QPalette.ColorRole.Window).lightness(),220)
        with tempfile.TemporaryDirectory() as root:
            window=Window(root)
            deadline=time.monotonic()+15
            while window.busy() and time.monotonic()<deadline:
                app.processEvents(); time.sleep(.02)
            app.processEvents()
            self.assertFalse(window.busy())
            self.assertEqual(set(window.fields),{'tag','officer'})
            self.assertEqual(window.field_descriptions['tag']['default'],'31')
            self.assertEqual(window.tabs.currentIndex(),3)
            self.assertEqual(window.modules.count(),1)
            self.assertEqual(window.tabs.tabText(window.tutorial_index),'Tutorial')
            self.assertEqual(window.tutorial_steps.count(),10)
            window.open_tutorial()
            self.assertEqual(window.tabs.currentIndex(),window.tutorial_index)
            window.account.setText('test@example.comtest@example.com')
            with self.assertRaises(ValueError):
                window.save_settings()
            window.close(); window.store.db.close()
