"""Desktop UI. Browser work and plugin code always execute outside the UI process."""
import json
from pathlib import Path
import sys
from PySide6.QtCore import QProcess, QTimer, Qt, QThread, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QPushButton,QLabel,QListWidget,QTabWidget,QLineEdit,QFormLayout,QComboBox,
    QCheckBox,QTableWidget,QTableWidgetItem,QFileDialog,QMessageBox,QTextBrowser,
    QProgressBar,QSplitter,QAbstractItemView)
from automation_hub.storage import Store, QueueLock
from automation_hub.modules import ModuleManager, Catalogue, BUILTIN
from automation_hub import credentials


TUTORIAL_STEPS = [
    (
        '1. What Automation Hub does',
        '''<h2>What Automation Hub does</h2>
        <p>Automation Hub runs small tools called modules. The Help2Rent Contact
        Uploader is included and uploads Excel contact lists for you.</p>
        <p>Your original spreadsheets stay where they are. The app makes managed
        copies, records every job, and can continue after the app is restarted.</p>
        <p>Start with one spreadsheet until you have checked the resulting list and
        its contacts on Help2Rent.</p>''',
    ),
    (
        '2. Save your Help2Rent account',
        '''<h2>Save your Help2Rent account</h2>
        <ol><li>Open <b>Settings</b>.</li><li>Enter your Help2Rent email and
        password.</li><li>Click <b>Save Settings</b>.</li></ol>
        <p>The password is stored in macOS Keychain or Windows Credential Manager.
        The uploader clears any email already present on the login page, enters the
        saved address once, and checks it before logging in.</p>''',
    ),
    (
        '3. Refresh the tag and officer choices',
        '''<h2>Refresh account choices</h2>
        <ol><li>Open <b>My Modules</b>.</li><li>Select <b>Help2Rent Contact
        Uploader</b>.</li><li>Click <b>Refresh account choices</b>.</li></ol>
        <p>This logs in and reads the choices currently available to your account.
        The old uploader always used tag ID 31, whose current name is
        <b>sample</b>. Automation Hub selects that tag automatically when it is
        available. Check the displayed tag and choose the officer for this run.</p>
        <p>Refresh again whenever Help2Rent changes its tags or officers.</p>''',
    ),
    (
        '4. Add spreadsheets',
        '''<h2>Add spreadsheets</h2>
        <p>Use <b>Add Files</b> for individual workbooks or <b>Add Folder</b> for a
        complete folder. You can also drag files onto the table.</p>
        <p>The Help2Rent module accepts <code>.xlsx</code> files. Temporary Excel
        files and hidden Mac files are ignored. Selecting a file does not upload
        it, move it, or change it.</p>''',
    ),
    (
        '5. Preview and understand list names',
        '''<h2>Preview before uploading</h2>
        <ol><li>Click <b>Preview</b>.</li><li>Check every validation result and
        proposed list name.</li></ol>
        <p>The spreadsheet filename becomes the list name. For example,
        <code>Enfields.xlsx</code> becomes <code>Enfields upload</code>. If that
        name already exists, the uploader adds the next available number.</p>
        <p>Preview checks whether the workbook is readable. It does not submit it
        and cannot confirm that every contact column has the meaning Help2Rent
        expects.</p>''',
    ),
    (
        '6. Start and follow an upload',
        '''<h2>Start an upload</h2>
        <p>Click <b>Start</b> only after reviewing the preview. The uploader works
        through files one at a time and shows progress in <b>Activity</b>.</p>
        <p>A completed result means the app found a newly created Help2Rent list
        after submission. Open the list on Help2Rent during your first test and
        confirm the contacts inside it are correct.</p>
        <p>The <b>Upload Again</b> checkbox is for a deliberate repeat upload. Leave
        it off during normal use so identical completed files are skipped.</p>''',
    ),
    (
        '7. Pause, stop, resume, and review',
        '''<h2>Control and recover a queue</h2>
        <p><b>Pause</b> waits at a safe boundary. <b>Stop</b> finishes checking any
        submission already in progress, then stops. <b>Resume Queue</b> continues
        saved work after a pause, restart, or connection problem.</p>
        <p>If a job says <b>Needs review</b>, check Help2Rent before permitting
        another submission. Use <b>Resolve Uncertain Upload</b> to record what you
        found. This prevents a lost browser response from creating duplicates.</p>''',
    ),
    (
        '8. Activity and reports',
        '''<h2>Activity and reports</h2>
        <p>The <b>Activity</b> tab shows the file, saved state, final list name,
        verification level, update time, and any error.</p>
        <p><b>Open Selected List</b> opens the corresponding Help2Rent page when a
        remote address is available. <b>Export Report</b> saves the current history
        as a CSV that can be opened in Excel.</p>
        <p>Imported reports from the old uploader are retained as historical
        records. They do not cause new jobs to be marked as freshly verified.</p>''',
    ),
    (
        '9. Install and update modules',
        '''<h2>Install and update modules</h2>
        <p>Use <b>Install Module from File</b> for a module package sent to you. The
        Module Catalogue can show modules from a configured online catalogue.</p>
        <p>Read the description and install modules only from someone you trust.
        Installed modules stay available offline, although a module that works
        with a website still needs an internet connection.</p>
        <p><b>Roll Back</b> returns an installed module to its previous version.
        Uninstalling a module keeps its settings and activity history.</p>''',
    ),
    (
        '10. If something goes wrong',
        '''<h2>If something goes wrong</h2>
        <ul><li>If login fails, save the account again and refresh account choices.</li>
        <li>If <b>sample</b> is not selected, tag ID 31 is unavailable. Choose the
        correct existing tag before uploading.</li><li>If validation fails, open the
        workbook in Excel and save it as a normal <code>.xlsx</code> file.</li>
        <li>If Help2Rent changes its page, the queue stops with an explanation.
        Keep the job saved and update the module before retrying.</li></ul>''',
    ),
]


def apply_light_theme(app):
    """Use one complete palette so macOS dark mode cannot create white-on-white text."""
    app.setStyle('Fusion')
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,QColor('#f5f7fb'))
    palette.setColor(QPalette.ColorRole.WindowText,QColor('#172033'))
    palette.setColor(QPalette.ColorRole.Base,QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.AlternateBase,QColor('#f1f4f8'))
    palette.setColor(QPalette.ColorRole.ToolTipBase,QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.ToolTipText,QColor('#172033'))
    palette.setColor(QPalette.ColorRole.Text,QColor('#172033'))
    palette.setColor(QPalette.ColorRole.Button,QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.ButtonText,QColor('#172033'))
    palette.setColor(QPalette.ColorRole.BrightText,QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.Link,QColor('#245dcc'))
    palette.setColor(QPalette.ColorRole.Highlight,QColor('#245dcc'))
    palette.setColor(QPalette.ColorRole.HighlightedText,QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.PlaceholderText,QColor('#6b7280'))
    app.setPalette(palette)
    app.setStyleSheet('''
        QWidget {
            color: #172033;
            font-size: 13px;
        }
        QMainWindow, QDialog, QTabWidget::pane {
            background: #f5f7fb;
        }
        QLabel#title {
            color: #101828;
            font-size: 23px;
            font-weight: 600;
            padding: 8px 0;
        }
        QPushButton {
            color: #172033;
            background: #ffffff;
            border: 1px solid #cbd3df;
            border-radius: 6px;
            padding: 8px 13px;
        }
        QPushButton:hover {
            background: #eef4ff;
            border-color: #8aa8df;
        }
        QPushButton:pressed {
            background: #dce8fb;
        }
        QPushButton:disabled {
            color: #8a94a6;
            background: #edf0f4;
        }
        QLineEdit, QComboBox, QTextBrowser, QListWidget, QTableWidget {
            color: #172033;
            background: #ffffff;
            border: 1px solid #cbd3df;
            border-radius: 5px;
            selection-color: #ffffff;
            selection-background-color: #245dcc;
        }
        QLineEdit, QComboBox {
            padding: 7px;
        }
        QComboBox QAbstractItemView {
            color: #172033;
            background: #ffffff;
            border: 1px solid #aeb8c7;
            selection-color: #ffffff;
            selection-background-color: #245dcc;
        }
        QTableWidget {
            gridline-color: #dce1e9;
            alternate-background-color: #f7f9fc;
        }
        QHeaderView::section {
            color: #273142;
            background: #e9edf3;
            border: 0;
            border-right: 1px solid #cbd3df;
            border-bottom: 1px solid #cbd3df;
            padding: 6px;
            font-weight: 600;
        }
        QTabWidget::pane {
            border: 1px solid #d7dde7;
            top: -1px;
        }
        QTabBar::tab {
            color: #344054;
            background: #e7ebf1;
            border: 1px solid #cbd3df;
            padding: 11px 20px;
        }
        QTabBar::tab:selected {
            color: #173665;
            background: #ffffff;
            border-top: 3px solid #245dcc;
        }
        QCheckBox {
            color: #273142;
            spacing: 7px;
        }
        QProgressBar {
            color: #172033;
            background: #e7ebf1;
            border: 1px solid #cbd3df;
            border-radius: 5px;
            text-align: center;
            min-height: 22px;
        }
        QProgressBar::chunk {
            background: #4d7fd3;
            border-radius: 4px;
        }
        QStatusBar {
            color: #344054;
            background: #eef1f5;
        }
        QToolTip {
            color: #172033;
            background: #ffffff;
            border: 1px solid #9da8b8;
        }
    ''')


class Task(QThread):
    result = Signal(object)
    failed = Signal(str)
    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
    def run(self):
        try: self.result.emit(self.fn())
        except Exception as e: self.failed.emit(str(e))


class DropTable(QTableWidget):
    dropped = Signal(list)
    def __init__(self):
        super().__init__(0,3)
        self.setHorizontalHeaderLabels(['Spreadsheet','Proposed list name','Validation'])
        self.setAcceptDrops(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.horizontalHeader().setStretchLastSection(True)
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dragMoveEvent(self,event):
        event.acceptProposedAction()
    def dropEvent(self,event):
        self.dropped.emit([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()


def button(text, fn, layout):
    b = QPushButton(text)
    b.clicked.connect(fn)
    layout.addWidget(b)
    return b


class Window(QMainWindow):
    def __init__(self, root=None):
        super().__init__()
        self.store = Store(root)
        self.manager = ModuleManager(self.store)
        self.files = []
        self.preview_rows = []
        self.preview_signature = None
        self.fields = {}
        self.process = None
        self.buffer = ''
        self.tasks = []
        self.module_id = 'help2rent'
        self.setWindowTitle('Automation Hub')
        self.resize(1100,760)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.build_modules()
        self.build_catalogue()
        self.build_activity()
        self.build_settings()
        self.build_tutorial()
        self.statusBar().showMessage('Ready • Your original files stay untouched')
        self.reload_modules()
        self.refresh_activity()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_activity)
        self.timer.start(1500)
        if not self.store.get('account'):
            self.tabs.setCurrentIndex(3)
            self.statusBar().showMessage('Welcome — save your Help2Rent account in Settings, then open My Modules.')

    def error(self, message):
        QMessageBox.warning(self,'Action needed',str(message))

    def guarded(self, fn):
        try: return fn()
        except Exception as e: self.error(e)

    def background(self, fn, done):
        task = Task(fn,self)
        self.tasks.append(task)
        task.result.connect(done)
        task.failed.connect(self.error)
        task.finished.connect(lambda:self.tasks.remove(task))
        task.start()

    def build_modules(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel('My Modules'); title.setObjectName('title'); layout.addWidget(title)
        row = QHBoxLayout(); layout.addLayout(row)
        self.modules = QComboBox(); row.addWidget(self.modules,1)
        button('Install Module from File',self.install_file,row)
        button('Roll Back',lambda:self.guarded(self.rollback),row)
        button('Uninstall',lambda:self.guarded(self.uninstall),row)
        self.module_description = QLabel(); self.module_description.setWordWrap(True); layout.addWidget(self.module_description)
        self.form = QFormLayout(); layout.addLayout(self.form)
        row = QHBoxLayout(); layout.addLayout(row)
        button('Refresh account choices',lambda:self.guarded(self.refresh_options),row)
        button('Add Files',self.add_files,row)
        button('Add Folder',self.add_folder,row)
        button('Clear Selection',self.clear_files,row)
        self.table = DropTable(); self.table.dropped.connect(self.add_paths); layout.addWidget(self.table,1)
        self.again = QCheckBox('Upload Again — intentionally include files already completed'); layout.addWidget(self.again)
        row = QHBoxLayout(); layout.addLayout(row)
        button('Preview',lambda:self.guarded(self.preview),row)
        button('Start',lambda:self.guarded(self.start),row)
        button('Pause',lambda:self.control('pause'),row)
        button('Resume Queue',lambda:self.guarded(self.resume),row)
        button('Stop',lambda:self.control('stop'),row)
        self.progress = QProgressBar(); layout.addWidget(self.progress)
        self.tabs.addTab(page,'My Modules')
        self.modules.currentIndexChanged.connect(self.module_changed)

    def build_catalogue(self):
        page = QWidget(); layout = QVBoxLayout(page)
        row = QHBoxLayout(); layout.addLayout(row)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search modules'); row.addWidget(self.search)
        button('Refresh Catalogue',self.refresh_catalogue,row)
        self.catalogue_status = QLabel('Cached catalogue • Internet is only needed to refresh or download.'); layout.addWidget(self.catalogue_status)
        split = QSplitter(); layout.addWidget(split)
        self.catalogue_list = QListWidget(); split.addWidget(self.catalogue_list)
        self.detail = QTextBrowser(); split.addWidget(self.detail)
        self.catalogue_list.currentRowChanged.connect(self.catalogue_detail)
        self.search.textChanged.connect(self.show_catalogue)
        button('Install / Update Selected Module',self.install_catalogue,layout)
        self.tabs.addTab(page,'Module Catalogue')
        self.show_catalogue()

    def build_activity(self):
        page = QWidget(); layout = QVBoxLayout(page)
        self.activity = QTableWidget(0,6)
        self.activity.setHorizontalHeaderLabels(['File','Status','List name','Verification','Updated','Details'])
        self.activity.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.activity.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.activity.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.activity)
        row = QHBoxLayout(); layout.addLayout(row)
        button('Export Report',self.export,row)
        button('Open Selected List',self.open_remote,row)
        button('Retry Selected Failed File',lambda:self.guarded(self.retry),row)
        button('Resolve Uncertain Upload',lambda:self.guarded(self.resolve),row)
        self.history_label = QLabel(); layout.addWidget(self.history_label)
        self.tabs.addTab(page,'Activity')

    def build_settings(self):
        page = QWidget(); layout = QVBoxLayout(page)
        title = QLabel('Account & Application Settings'); title.setObjectName('title'); layout.addWidget(title)
        form = QFormLayout(); layout.addLayout(form)
        self.account = QLineEdit(self.store.get('account',''))
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText('Leave blank to keep your saved password')
        self.catalogue_url = QLineEdit(self.store.get('catalogue_url','')); self.catalogue_url.setPlaceholderText('Optional HTTPS catalogue URL')
        form.addRow('Help2Rent email',self.account); form.addRow('Password',self.password); form.addRow('Module catalogue',self.catalogue_url)
        button('Save Settings',lambda:self.guarded(self.save_settings),layout)
        button('Import Previous Configuration & Reports',lambda:self.guarded(self.import_legacy),layout)
        button('Open Step-by-Step Tutorial',self.open_tutorial,layout)
        label = QLabel('Passwords are saved in your operating system’s credential store.\nInstalled modules work locally. Website uploads require internet.\nOnly install modules supplied by someone you trust.'); label.setWordWrap(True); layout.addWidget(label)
        layout.addStretch()
        self.tabs.addTab(page,'Settings')

    def build_tutorial(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel('Step-by-Step Tutorial')
        title.setObjectName('title')
        layout.addWidget(title)

        splitter = QSplitter()
        layout.addWidget(splitter,1)
        self.tutorial_steps = QListWidget()
        self.tutorial_content = QTextBrowser()
        splitter.addWidget(self.tutorial_steps)
        splitter.addWidget(self.tutorial_content)
        splitter.setStretchFactor(1,1)

        for step_title, _ in TUTORIAL_STEPS:
            self.tutorial_steps.addItem(step_title)
        self.tutorial_steps.currentRowChanged.connect(self.show_tutorial_step)

        navigation = QHBoxLayout()
        layout.addLayout(navigation)
        button('Previous',lambda:self.move_tutorial(-1),navigation)
        button('Next',lambda:self.move_tutorial(1),navigation)

        self.tutorial_index = self.tabs.addTab(page,'Tutorial')
        self.tutorial_steps.setCurrentRow(0)

    def open_tutorial(self):
        self.tabs.setCurrentIndex(self.tutorial_index)
        if self.tutorial_steps.currentRow() < 0:
            self.tutorial_steps.setCurrentRow(0)

    def show_tutorial_step(self, index):
        if 0 <= index < len(TUTORIAL_STEPS):
            self.tutorial_content.setHtml(TUTORIAL_STEPS[index][1])

    def move_tutorial(self, offset):
        current = max(0,self.tutorial_steps.currentRow())
        target = min(len(TUTORIAL_STEPS)-1,max(0,current+offset))
        self.tutorial_steps.setCurrentRow(target)

    def save_settings(self):
        from urllib.parse import urlparse
        url = self.catalogue_url.text().strip()
        if url and urlparse(url).scheme != 'https': raise ValueError('Use an HTTPS catalogue URL.')
        account = self.account.text().strip()
        if account and (account.count('@') != 1 or any(character.isspace() for character in account)):
            raise ValueError('Enter one Help2Rent email address. The current value is duplicated or invalid.')
        if self.password.text():
            if not account: raise ValueError('Enter your account email first.')
            credentials.save(account,self.password.text())
            self.password.clear()
        self.store.put('account',account)
        self.store.put('catalogue_url',url)
        self.statusBar().showMessage('Settings saved')

    def reload_modules(self):
        self.modules.blockSignals(True)
        self.modules.clear()
        for m in self.manager.manifests():
            self.modules.addItem(f"{m['name']}  ·  {m['version']}",m)
        self.modules.blockSignals(False)
        self.module_changed()

    def module_changed(self):
        m = self.modules.currentData()
        if not m: return
        if self.busy():
            self.error('Wait for the current operation to finish before switching modules.')
            index = next((i for i in range(self.modules.count()) if self.modules.itemData(i)['id']==self.module_id),0)
            self.modules.blockSignals(True); self.modules.setCurrentIndex(index); self.modules.blockSignals(False)
            return
        self.module_id = m['id']
        self.module_description.setText(m['description']+f"\nUpdated {m['released']}")
        self.clear_files()
        while self.form.rowCount(): self.form.removeRow(0)
        self.fields = {}
        self.launch(dict(action='describe'))

    def apply_fields(self, descriptions):
        saved = self.store.get('settings:'+self.module_id,{})
        choices = self.store.get('choices:'+self.module_id,{})
        self.field_descriptions = {field['key']: field for field in descriptions}
        for field in descriptions:
            key = field['key']; kind = field.get('type','text')
            if kind == 'choice':
                widget = QComboBox()
                for option in choices.get(key,field.get('options',[])):
                    widget.addItem(option['label'],option['value'])
                index = widget.findData(saved.get(key) or field.get('default',''))
                widget.setCurrentIndex(index)
            elif kind == 'boolean':
                widget = QCheckBox(); widget.setChecked(bool(saved.get(key,field.get('default',False))))
            else:
                widget = QLineEdit(str(saved.get(key,field.get('default',''))))
            self.fields[key] = widget
            self.form.addRow(field['label'],widget)

    def settings(self):
        value = self.store.get('settings:'+self.module_id,{})
        for key,widget in self.fields.items():
            value[key] = widget.currentData() if isinstance(widget,QComboBox) else widget.isChecked() if isinstance(widget,QCheckBox) else widget.text()
        if self.module_id == 'help2rent':
            value.setdefault('upload_url','https://www.help2rent.co.uk/email/marketing/contact')
            value.setdefault('login_url','https://www.help2rent.co.uk/login')
            value.setdefault('timeout',30)
            value['account'] = self.store.get('account','')
        return value

    def account_credentials(self):
        account = self.store.get('account','')
        if account and (account.count('@') != 1 or any(character.isspace() for character in account)):
            raise ValueError('The saved Help2Rent email is duplicated or invalid. Correct it in Settings.')
        password = credentials.read(account) if account else ''
        if not account or not password: raise ValueError('Save your email and password in Settings first.')
        return dict(username=account,password=password)

    def busy(self):
        return self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning

    def launch(self, request):
        if self.busy(): raise ValueError('An operation is already running. Pause or stop it first.')
        request.update(root=str(self.store.root),module=self.module_id)
        process = QProcess(self)
        self.process = process; self.buffer = ''; self.stderr = ''
        process.readyReadStandardOutput.connect(self.read_events)
        process.readyReadStandardError.connect(lambda:self.capture_stderr(process))
        process.finished.connect(self.worker_finished)
        process.errorOccurred.connect(lambda error:self.error('Could not start the module worker.') if error == QProcess.ProcessError.FailedToStart else None)
        if getattr(sys,'frozen',False):
            worker = Path(sys.executable).with_name('AutomationHubWorker.exe' if sys.platform=='win32' else 'AutomationHubWorker')
            process.setProgram(str(worker)); process.setArguments(['--worker'])
        else:
            process.setProgram(sys.executable); process.setArguments([str(Path(__file__).resolve().parents[1]/'desktop.py'),'--worker'])
        process.start()
        if not process.waitForStarted(5000): raise RuntimeError('The module worker could not start.')
        process.write((json.dumps(request)+'\n').encode())
        self.statusBar().showMessage('Working…')

    def capture_stderr(self,process):
        self.stderr = (self.stderr+bytes(process.readAllStandardError()).decode(errors='replace'))[-4000:]

    def read_events(self):
        self.buffer += bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')
        while '\n' in self.buffer:
            line,self.buffer = self.buffer.split('\n',1)
            try: event = json.loads(line)
            except ValueError: continue
            kind = event.get('event')
            if kind == 'description': self.apply_fields(event['settings'])
            elif kind == 'preview':
                self.preview_rows = event['rows']; self.preview_signature = self.pending_preview_signature
                self.render_preview()
            elif kind == 'options':
                self.store.put('choices:'+self.module_id,event['choices'])
                saved = self.store.get('settings:'+self.module_id,{})
                for key,options in event['choices'].items():
                    widget = self.fields.get(key)
                    if isinstance(widget,QComboBox):
                        field = self.field_descriptions.get(key,{})
                        preferred = widget.currentData()
                        if preferred is None:
                            preferred = saved.get(key) or field.get('default')
                        widget.clear()
                        for option in options: widget.addItem(option['label'],option['value'])
                        index = widget.findData(preferred)
                        widget.setCurrentIndex(index)
                selected_tag = self.fields.get('tag').currentText() if isinstance(self.fields.get('tag'),QComboBox) else ''
                if selected_tag:
                    self.statusBar().showMessage(f'Account choices loaded. Upload tag selected automatically: {selected_tag}')
                else:
                    self.statusBar().showMessage('Account choices loaded. The usual upload tag was not found; choose an existing tag.')
            elif kind in ('error','notice'): self.error(event['message'])
            elif kind == 'progress': self.refresh_activity()

    def worker_finished(self,code,status):
        self.read_events()
        self.refresh_activity()
        self.statusBar().showMessage('Operation finished. Review Activity for results.' if code==0 else 'Operation stopped. Your saved queue is preserved.')
        if code and self.stderr: self.error('The worker stopped unexpectedly. Your queue is saved.\n'+self.stderr)

    def refresh_options(self):
        self.launch(dict(action='options',settings=self.settings(),credentials=self.account_credentials()))

    def add_files(self):
        files,_ = QFileDialog.getOpenFileNames(self,'Choose files','','Excel files (*.xlsx *.XLSX);;All files (*)')
        self.add_paths(files)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self,'Choose a folder')
        if folder: self.add_paths([folder])

    def add_paths(self,paths):
        if self.busy(): return self.error('Wait for the current operation before changing files.')
        for raw in paths:
            path = Path(raw)
            candidates = path.rglob('*') if path.is_dir() else [path]
            for candidate in candidates:
                if candidate.is_file() and not any(p.startswith(('.', '~$')) for p in candidate.parts) and candidate.suffix.lower()=='.xlsx':
                    name = str(candidate.resolve())
                    if name not in self.files: self.files.append(name)
        self.preview_signature = None
        self.preview_rows = [dict(file=f,name='Preview to calculate',error='Not checked') for f in self.files]
        self.render_preview()

    def clear_files(self):
        if self.busy(): return
        self.files=[]; self.preview_rows=[]; self.preview_signature=None
        self.render_preview()

    def render_preview(self):
        self.table.setRowCount(len(self.preview_rows))
        for i,row in enumerate(self.preview_rows):
            for j,value in enumerate((row['file'],row['name'],row['error'] or 'Ready')):
                self.table.setItem(i,j,QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def preview(self):
        if not self.files: raise ValueError('Add some spreadsheets first.')
        self.pending_preview_signature = json.dumps([self.files,self.settings()],sort_keys=True)
        self.launch(dict(action='preview',files=self.files,settings=self.settings()))

    def start(self):
        if self.busy(): raise ValueError('An operation is already running.')
        if self.preview_signature != json.dumps([self.files,self.settings()],sort_keys=True):
            raise ValueError('Preview your current files and settings before starting.')
        if not self.files or any(r['error'] for r in self.preview_rows):
            raise ValueError('Resolve the file validation errors before starting.')
        settings = self.settings()
        if self.module_id=='help2rent' and (not settings.get('tag') or not settings.get('officer')):
            raise ValueError('Refresh account choices and select a tag and officer.')
        auth = self.account_credentials() if self.module_id=='help2rent' else {}
        with QueueLock(self.store.root):
            added,skipped = self.store.enqueue(self.module_id,self.files,settings,self.again.isChecked())
            self.store.put('settings:'+self.module_id,settings)
        self.statusBar().showMessage(f'{added} added; {skipped} already queued or completed')
        self.launch(dict(action='run',credentials=auth))

    def control(self,command):
        if self.busy():
            self.process.write((json.dumps(dict(command=command))+'\n').encode())
            self.statusBar().showMessage(command.capitalize()+' requested — the current submission will be reconciled first.')

    def resume(self):
        if self.busy(): self.control('resume')
        else: self.launch(dict(action='run',credentials=self.account_credentials() if self.module_id=='help2rent' else {}))

    def refresh_activity(self):
        rows = self.store.rows(); self.activity_rows = rows
        self.activity.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,key in enumerate(('original','state','name','verification','updated','error')):
                self.activity.setItem(i,j,QTableWidgetItem(str(row[key] or '').replace('_',' ') if key in ('state','verification') else str(row[key] or '')))
        done = sum(r['state']=='completed' for r in rows)
        self.progress.setMaximum(max(1,len(rows))); self.progress.setValue(done)
        self.progress.setFormat(f'{done} of {len(rows)} completed')
        count = self.store.db.execute('SELECT COUNT(*) FROM historical').fetchone()[0]
        self.history_label.setText(f'{count} imported historical reports. These are historical evidence, not fresh upload verification.')

    def selected_job(self):
        index = self.activity.currentRow()
        if index<0: raise ValueError('Select a file in Activity first.')
        return self.activity_rows[index]

    def retry(self):
        row = self.selected_job()
        if row['state'] != 'failed': raise ValueError('Only confirmed failures can be retried here. Resolve uncertain uploads separately.')
        with QueueLock(self.store.root): self.store.transition(row['id'],'queued',error='')
        self.refresh_activity()

    def resolve(self):
        row = self.selected_job()
        if row['state'] not in ('needs_review','submitting','verifying'): raise ValueError('This file does not need reconciliation.')
        box = QMessageBox(self); box.setWindowTitle('Review the website first')
        box.setText('Use Resume Queue to check again automatically. Only mark this as not uploaded after checking the website yourself. This permits another submission.')
        retry = box.addButton('I checked — not uploaded',QMessageBox.ButtonRole.AcceptRole)
        complete = box.addButton('I checked — uploaded',QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel); box.exec()
        with QueueLock(self.store.root):
            if box.clickedButton()==retry: self.store.transition(row['id'],'queued',error='User confirmed no upload exists.')
            elif box.clickedButton()==complete: self.store.transition(row['id'],'completed',verification='user_confirmed',error='')
        self.refresh_activity()

    def open_remote(self):
        def action():
            row = self.selected_job()
            if row['remote_id'] and row['remote_id'].startswith(('https://','http://')):
                QDesktopServices.openUrl(QUrl(row['remote_id']))
            else: QDesktopServices.openUrl(QUrl(json.loads(row['settings']).get('upload_url','https://www.help2rent.co.uk/email/marketing/contact')))
        self.guarded(action)

    def export(self):
        path,_ = QFileDialog.getSaveFileName(self,'Export Activity','upload-report.csv','CSV (*.csv)')
        if path: self.guarded(lambda:self.store.export(path))

    def install_file(self):
        path,_ = QFileDialog.getOpenFileName(self,'Install a trusted module','','Module packages (*.zip *.hubmodule)')
        if not path: return
        def action():
            m = self.manager.inspect(path)
            if QMessageBox.question(self,'Install Module',f"Install {m['name']} {m['version']}?\n\n{m['description']}\n\nModules execute code on this computer. Install only from someone you trust.") == QMessageBox.StandardButton.Yes:
                self.manager.install(path); self.reload_modules()
        self.guarded(action)

    def rollback(self):
        self.manager.rollback(self.module_id); self.reload_modules()

    def uninstall(self):
        if QMessageBox.question(self,'Uninstall module','Remove this module? Its settings and history will be kept.')==QMessageBox.StandardButton.Yes:
            self.manager.uninstall(self.module_id); self.reload_modules()

    def show_catalogue(self):
        try: items = Catalogue(self.store).cached()['modules']
        except Exception: items=[]
        query = self.search.text().casefold()
        self.catalogue_items = [m for m in items if query in (m['name']+' '+m['summary']).casefold()]
        self.catalogue_list.clear()
        for m in self.catalogue_items: self.catalogue_list.addItem(f"{m['name']} · {m['version']} · {m['released']}")
        if not items: self.detail.setPlainText('No catalogue loaded. Configure a catalogue URL in Settings, or use Install Module from File.')
        elif self.catalogue_items: self.catalogue_list.setCurrentRow(0)

    def catalogue_detail(self,index):
        if index<0 or index>=len(self.catalogue_items): return
        m = self.catalogue_items[index]
        installed = next((x['version'] for x in self.manager.manifests() if x['id']==m['id']),'Not installed')
        self.detail.setPlainText(f"{m['name']}\nAvailable: {m['version']} • Installed: {installed}\nUpdated: {m['released']}\n\n{m['summary']}\n\n{m['description']}\n\n{m.get('release_notes','')}")

    def refresh_catalogue(self):
        root = self.store.root
        def done(result):
            self.catalogue_status.setText('Catalogue refreshed • Available offline'); self.show_catalogue()
        self.background(lambda:Catalogue(Store(root)).refresh(),done)

    def install_catalogue(self):
        index = self.catalogue_list.currentRow()
        if index<0: return
        item = self.catalogue_items[index]; root = self.store.root
        if QMessageBox.question(self,'Install Module',f"Install trusted module {item['name']} {item['version']}?")==QMessageBox.StandardButton.Yes:
            self.background(lambda:Catalogue(Store(root)).install(item),lambda result:self.reload_modules())

    def import_legacy(self):
        folder = QFileDialog.getExistingDirectory(self,'Choose the old uploader folder')
        if not folder: return
        if QMessageBox.question(self,'Import existing configuration','Copy account settings and historical reports? Original files will not be changed and no uploads will start.') != QMessageBox.StandardButton.Yes: return
        from automation_hub.migration import migrate
        count = migrate(self.store,folder,credentials.save)
        self.account.setText(self.store.get('account','')); self.refresh_activity()
        self.statusBar().showMessage(f'Imported {count} historical reports. Refresh account choices before uploading.')

    def closeEvent(self,event):
        if self.busy() or self.tasks:
            self.error('An operation is still running. Click Stop and wait for the current submission or download to finish before closing.')
            event.ignore()
        else: event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Automation Hub')
    apply_light_theme(app)
    window = Window(); window.show()
    return app.exec()
