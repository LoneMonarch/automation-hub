"""Browser integration tests use only a loopback test server, never Help2Rent."""
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlparse
from automation_hub.builtin.help2rent import CHROMIUM_ARGS, Help2Rent, SiteChanged
from test_core import workbook


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,content):
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers(); self.wfile.write(content.encode())
    def do_GET(self):
        if self.path.startswith('/login'):
            return self.send('<form action="/authenticate" method="post"><label>Email Address<input id="email" name="email" value="old@example.comold@example.com"></label><label>Password<input type="password" name="password" value="old-password"></label><button>Login</button></form><script>setTimeout(() => document.querySelector("#email").value = "late@example.comlate@example.com", 100)</script>')
        page=int(parse_qs(urlparse(self.path).query).get('page',['1'])[0])
        form='<form action="/submit" method="post"><input name="name" type="text"><select name="tag_id"><option value="131">Wrong tag</option><option value="31">Correct tag</option></select><select name="subadmin_id[]"><option value="7">Test Officer</option></select><input type="file" name="userfile"><button>Submit</button></form>'
        lists=self.server.lists
        chunk=lists[:1] if page==1 else lists[1:]
        links=''.join(f'<a href="/marketing/contactlist/{ident}">{html.escape(name)}</a>' for ident,name in chunk)
        pagination='<a rel="next" href="/upload?page=2">Next</a>' if page==1 and len(lists)>1 else ''
        self.send(form+links+pagination)
    def do_POST(self):
        data=self.rfile.read(int(self.headers.get('Content-Length',0))).decode()
        if self.path=='/authenticate':
            self.server.last_login=parse_qs(data)
        if self.path=='/submit':
            self.server.posts+=1
            if self.server.mode=='reject': return self.send('<div class="alert-danger">Invalid workbook</div>')
            name=parse_qs(data)['name'][0]
            self.server.lists.append((str(len(self.server.lists)+1),name))
        self.send_response(303); self.send_header('Location','/upload'); self.end_headers()


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()
    def setUp(self):
        self.server.lists=[('1','Old list'),('2','Résumé contacts upload')]; self.server.posts=0; self.server.mode='ok'; self.server.last_login={}
        self.temp=tempfile.TemporaryDirectory(); self.file=workbook(Path(self.temp.name)/'Résumé contacts.xlsx')
        self.mod=Help2Rent()
        self.mod.open(dict(login_url=self.url+'/login',upload_url=self.url+'/upload',tag='31',officer='7',headless=True,timeout=5),dict(username='test@example.com',password='test'))
    def tearDown(self): self.mod.close(); self.temp.cleanup()
    def prepare(self):
        job=dict(path=str(self.file)); name,baseline=self.mod.prepare(job)
        job.update(name=name,baseline=json.dumps(baseline)); return job
    def test_login_replaces_prefilled_email_and_password(self):
        self.assertEqual(self.server.last_login.get('email'),['test@example.com'])
        self.assertEqual(self.server.last_login.get('password'),['test'])

    def test_browser_first_run_prompts_are_disabled(self):
        self.assertIn('--no-first-run',CHROMIUM_ARGS)
        self.assertIn('--no-default-browser-check',CHROMIUM_ARGS)
    def test_paginated_inventory_and_exact_dropdown(self):
        job=self.prepare()
        self.assertEqual(job['name'],'Résumé contacts upload 1')
        self.assertEqual(len(json.loads(job['baseline'])),2)
        self.assertEqual(self.mod.page.locator('select[name="tag_id"]').input_value(),'31')
    def test_success_identifies_new_remote_id(self):
        result=self.mod.submit(self.prepare())
        self.assertEqual(result.state,'completed'); self.assertTrue(result.remote_id.endswith('/3')); self.assertEqual(self.server.posts,1)
    def test_rejected_form_not_success(self):
        self.server.mode='reject'; self.mod.timeout=200
        result=self.mod.submit(self.prepare())
        self.assertEqual(result.state,'needs_review'); self.assertEqual(self.server.posts,1)
    def test_preexisting_name_not_success(self):
        inventory=self.mod.inventory(); self.mod.timeout=200
        result=self.mod.reconcile(dict(name='Old list',baseline=json.dumps(inventory)))
        self.assertEqual(result.state,'needs_review'); self.assertEqual(self.server.posts,0)
    def test_recovery_after_server_commit(self):
        job=self.prepare(); self.server.lists.append(('3',job['name']))
        result=self.mod.reconcile(job)
        self.assertEqual(result.state,'completed'); self.assertEqual(self.server.posts,0)
    def test_ambiguous_name_field_stops_before_submit(self):
        self.mod.select('select[name="tag_id"]','31')
        with self.assertRaises(SiteChanged): self.mod.select('select[name="tag_id"]','3')
        self.assertEqual(self.server.posts,0)
    def test_expired_session(self):
        self.mod.page.goto(self.url+'/login'); self.mod.timeout=100
        with self.assertRaises(SiteChanged): self.mod.check_form()


if __name__=='__main__': unittest.main()
