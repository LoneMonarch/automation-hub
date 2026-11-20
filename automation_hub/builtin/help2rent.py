"""Help2Rent adapter. All uncertain submissions are reconciled, never retried blindly."""
import json
from pathlib import Path
import re
import sys
import time
import zipfile
from automation_hub.api import Result


# Prevent Chromium's own first-run/sign-in screens from appearing over the
# upload window. These switches do not alter the Help2Rent login or profile.
CHROMIUM_ARGS = [
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-search-engine-choice-screen',
]


class SiteChanged(RuntimeError):
    pass


class Help2Rent:
    def describe_settings(self):
        return [
            dict(
                key='tag',
                label='Upload tag (selected automatically)',
                type='choice',
                default='31',
            ),
            dict(key='officer',label='Officer',type='choice'),
        ]

    def validate(self, path):
        p = Path(path)
        if p.suffix.lower() != '.xlsx' or p.name.startswith(('~$','._','.')):
            return 'Select an Excel .xlsx workbook (not a temporary file).'
        try:
            with zipfile.ZipFile(p) as z:
                if z.testzip() or not {'[Content_Types].xml','xl/workbook.xml'} <= set(z.namelist()):
                    return 'This Excel workbook is incomplete or corrupt.'
        except (OSError,zipfile.BadZipFile):
            return 'This file is not a readable Excel workbook.'
        return ''

    def preview(self, path, settings):
        return re.sub(r'[_\s]+',' ',Path(path).stem).strip()+' upload'

    def open(self, settings, credentials):
        from playwright.sync_api import sync_playwright
        if credentials.get('username','').count('@') != 1:
            raise SiteChanged('The saved Help2Rent email is duplicated or invalid. Correct it in Settings before logging in.')
        self.settings = settings
        self.timeout = max(5,min(int(settings.get('timeout',30)),120))*1000
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(
            headless=settings.get('headless',False),
            args=CHROMIUM_ARGS,
        )
        self.page = self.browser.new_page()
        self.page.set_default_timeout(self.timeout)
        self.page.set_default_navigation_timeout(self.timeout)
        self.url = settings.get('upload_url','https://www.help2rent.co.uk/email/marketing/contact')
        self.page.goto(settings.get('login_url','https://www.help2rent.co.uk/login'),wait_until='domcontentloaded')
        # Help2Rent can populate the email field shortly after the page appears.
        # Wait for that work to finish, then replace and verify both login values.
        self.page.wait_for_timeout(1000)
        self.replace_login_value(
            self.page.get_by_role('textbox',name='Email Address',exact=True),
            credentials['username'],
            'email',
        )
        self.replace_login_value(
            self.page.get_by_role('textbox',name='Password',exact=True),
            credentials['password'],
            'password',
        )
        self.page.get_by_role('button',name='Login',exact=True).click()
        self.page.goto(self.url,wait_until='domcontentloaded')
        self.check_form()

    def replace_login_value(self, field, value, label):
        """Replace a possibly prefilled login value and confirm it occurs once."""
        field.wait_for(state='visible',timeout=self.timeout)
        field.click()
        field.press('Meta+A' if sys.platform == 'darwin' else 'Control+A')
        field.press('Backspace')
        field.clear()
        if field.input_value():
            raise SiteChanged(f'The {label} field could not be cleared before login.')
        field.fill(value)
        if field.input_value() != value:
            raise SiteChanged(f'The {label} field did not contain exactly the saved value.')

    def check_form(self):
        for selector in ('select[name="tag_id"]','select[name="subadmin_id[]"]','input[name="userfile"]'):
            try:
                self.page.locator(selector).wait_for(state='attached',timeout=self.timeout)
            except Exception as e:
                raise SiteChanged('Login expired or the upload form changed. Check your account and try again.') from e

    def options(self):
        return {key:self.page.locator(selector+' option').evaluate_all('(els)=>els.filter(e=>e.value).map(e=>({value:e.value,label:e.textContent.trim()}))') for key,selector in [('tag','select[name="tag_id"]'),('officer','select[name="subadmin_id[]"]')]}

    def select(self, selector, value):
        options = self.page.locator(selector+' option').evaluate_all('(els)=>els.map(e=>({value:e.value,label:e.textContent.trim()}))')
        exact = [o for o in options if o['value'] == str(value)]
        if len(exact) != 1:
            raise SiteChanged('The selected tag or officer is no longer available. Refresh account choices.')
        self.page.locator(selector).select_option(value=str(value))

    def inventory(self):
        """Follow next-page links, including DataTables, with loop detection."""
        self.page.goto(self.url,wait_until='domcontentloaded')
        self.check_form()
        found = {}
        visited = set()
        for _ in range(1000):
            self.page.locator('body').wait_for()
            entries = self.page.locator('a[href*="/marketing/contactlist/"]').evaluate_all('(els)=>els.map(e=>[e.href,e.textContent.trim()])')
            signature = tuple(sorted(tuple(x) for x in entries))
            if signature in visited:
                raise SiteChanged('Contact-list pagination repeated a page. Uploading was stopped to avoid duplicates.')
            visited.add(signature)
            found.update({url:name for url,name in entries})
            next_links = self.page.locator('a[rel="next"], .pagination .next a, .paginate_button.next, .pagination a').all()
            next_button = None
            for candidate in next_links:
                text = candidate.inner_text().strip().casefold()
                rel = candidate.get_attribute('rel')
                classes = (candidate.get_attribute('class') or '')+' '+(candidate.locator('..').get_attribute('class') or '')
                if (rel == 'next' or 'next' in classes or text in ('next','next ›','›','»')) and candidate.is_visible() and candidate.get_attribute('aria-disabled') != 'true' and 'disabled' not in classes and candidate.is_enabled():
                    next_button = candidate
                    break
            if next_button is None:
                return found
            next_button.click()
            self.page.wait_for_function("old => JSON.stringify(Array.from(document.querySelectorAll('a[href*=\"/marketing/contactlist/\"]')).map(e=>[e.href,e.textContent.trim()]).sort()) !== old",arg=json.dumps(sorted(entries),separators=(',',':')))
        raise SiteChanged('Too many listing pages. Uploading stopped.')

    def prepare(self, job):
        baseline = self.inventory()
        base = self.preview(job['path'],self.settings)
        names = {name.casefold() for name in baseline.values()}
        name = base
        number = 1
        while name.casefold() in names:
            name = f'{base} {number}'
            number += 1
        self.page.goto(self.url,wait_until='domcontentloaded')
        self.check_form()
        self.select('select[name="tag_id"]',self.settings['tag'])
        self.select('select[name="subadmin_id[]"]',self.settings['officer'])
        # Scope the text field to the actual upload form, excluding site search fields.
        form = self.page.locator('form').filter(has=self.page.locator('input[name="userfile"]'))
        name_input = form.locator('input[name="name"], input[name="list_name"], input[type="text"]')
        if name_input.count() != 1:
            raise SiteChanged('Cannot identify the contact-list name field unambiguously.')
        name_input.fill(name)
        self.page.locator('input[name="userfile"]').set_input_files(job['path'])
        self.submit_button = form.get_by_role('button',name='Submit',exact=True)
        if self.submit_button.count() != 1:
            raise SiteChanged('Cannot identify the upload button.')
        return name, baseline

    def submit(self, job):
        # The host commits 'submitting' before this method can click anything.
        self.submit_button.click()
        self.page.wait_for_load_state('domcontentloaded')
        errors = self.page.locator('.alert-danger, .invalid-feedback, .validation-summary-errors').all_text_contents()
        if any(t.strip() for t in errors):
            # Still reconcile: the server may have committed despite an error page.
            result = self.reconcile(job)
            if result.state != 'completed':
                result.error = 'Website reported: '+'; '.join(errors)[:1000]+'. Check the list before retrying.'
            return result
        return self.reconcile(job)

    def reconcile(self, job):
        baseline = json.loads(job['baseline'] or '{}')
        deadline = time.monotonic()+self.timeout/1000
        last_error = ''
        while True:
            try:
                current = self.inventory()
                matches = [ident for ident,name in current.items() if ident not in baseline and name.casefold() == job['name'].casefold()]
                if len(matches) == 1:
                    return Result('completed',matches[0],'list_creation_confirmed')
                if len(matches)>1:
                    return Result('needs_review',error='Multiple new lists match this upload. Review them on the website.')
            except Exception as e:
                last_error = str(e)
            if time.monotonic() >= deadline:
                return Result('needs_review',error=last_error or 'Could not confirm a new list. Check the website before retrying. No automatic resubmission was made.')
            self.page.wait_for_timeout(min(1000,max(1,int((deadline-time.monotonic())*1000))))

    def close(self):
        if hasattr(self,'browser'):
            self.browser.close()
        if hasattr(self,'pw'):
            self.pw.stop()


def create_module():
    return Help2Rent()
