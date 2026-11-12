import io
import os
import shutil
import tempfile

import paramiko

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from .sftp_test_server import SftpTestServer


class SftpCommon:
    @classmethod
    def _setup_sftp(cls):
        cls.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.root, 'docs'))
        with open(os.path.join(cls.root, 'hello.txt'), 'wb') as f:
            f.write(b'hello world')
        with open(os.path.join(cls.root, 'docs', 'a.txt'), 'wb') as f:
            f.write(b'A')
        cls.key = paramiko.RSAKey.generate(2048)
        cls.server = SftpTestServer(cls.root, pubkey=cls.key)
        cls.addClassCleanup(cls.server.close)
        cls.addClassCleanup(shutil.rmtree, cls.root, True)

    def _make_conn(self, **kw):
        vals = {'name': 'Test', 'host': '127.0.0.1', 'port': self.server.port,
                'username': 'tester', 'password': 'secret', 'start_path': '/'}
        vals.update(kw)
        return self.env['sftp.connection'].create(vals)


@tagged('post_install', '-at_install', 'sftp_file_manager')
class TestSftpModel(SftpCommon, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sftp()

    def test_password_ok_and_fingerprint_pinned(self):
        rec = self._make_conn()
        self.assertFalse(rec.host_fingerprint)
        res = rec.action_test_connection()
        self.assertEqual(res['params']['type'], 'success')
        self.assertTrue(rec.host_fingerprint.startswith('SHA256:'))

    def test_wrong_password(self):
        rec = self._make_conn(password='bad')
        with self.assertRaises(UserError):
            rec.action_test_connection()

    def test_key_auth(self):
        buf = io.StringIO()
        self.key.write_private_key(buf)
        rec = self._make_conn(auth_type='key', private_key=buf.getvalue(), password=False)
        self.assertEqual(rec.action_test_connection()['params']['type'], 'success')

    def test_bad_key_text(self):
        rec = self._make_conn(auth_type='key', private_key='garbage')
        with self.assertRaises(UserError):
            rec.action_test_connection()

    def test_host_key_change_refused(self):
        rec = self._make_conn(host_fingerprint='SHA256:somethingelse')
        with self.assertRaisesRegex(UserError, 'CHANGED'):
            rec.action_test_connection()

    def test_unreachable(self):
        rec = self._make_conn(port=1, timeout=2)
        with self.assertRaises(UserError):
            rec.action_test_connection()

    def test_open_browser_action(self):
        rec = self._make_conn()
        act = rec.action_open_browser()
        self.assertEqual(act['tag'], 'sftp_file_manager.browser')
        self.assertEqual(act['params']['connection_id'], rec.id)


@tagged('post_install', '-at_install', 'sftp_file_manager')
class TestSftpController(SftpCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sftp()

    def setUp(self):
        super().setUp()
        self.conn = self._make_conn()
        self.authenticate('admin', 'admin')

    def _csrf(self):
        import re
        html = self.url_open('/odoo').text
        return re.search(r'csrf_token["\']?\s*[:=]\s*["\']([0-9a-f]+o[0-9a-f]+)', html).group(1)

    def _rpc(self, route, **params):
        r = self.url_open(route, json={'params': params})
        data = r.json()
        return data

    def test_list(self):
        data = self._rpc('/sftp_file_manager/list', connection_id=self.conn.id, path='/')
        self.assertNotIn('error', data, data)
        entries = {e['name']: e for e in data['result']['entries']}
        self.assertTrue(entries['docs']['is_dir'])
        self.assertEqual(entries['hello.txt']['size'], 11)
        # folders first
        self.assertEqual(data['result']['entries'][0]['name'], 'docs')

    def test_list_missing_path_error(self):
        data = self._rpc('/sftp_file_manager/list', connection_id=self.conn.id, path='/nope')
        self.assertIn('error', data)

    def test_download(self):
        r = self.url_open('/sftp_file_manager/download?connection_id=%s&path=/hello.txt' % self.conn.id)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b'hello world')
        self.assertIn('hello.txt', r.headers['Content-Disposition'])

    def test_download_missing(self):
        r = self.url_open('/sftp_file_manager/download?connection_id=%s&path=/nope.bin' % self.conn.id)
        self.assertEqual(r.status_code, 404)

    def test_upload(self):
        r = self.url_open('/sftp_file_manager/upload',
                          data={'connection_id': self.conn.id, 'path': '/docs', 'csrf_token': self._csrf()},
                          files={'files': ('up.bin', b'\x00\x01' * 1000)})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {'uploaded': ['up.bin'], 'error': None})
        with open(os.path.join(self.root, 'docs', 'up.bin'), 'rb') as f:
            self.assertEqual(f.read(), b'\x00\x01' * 1000)

    def test_upload_strips_path_components(self):
        r = self.url_open('/sftp_file_manager/upload',
                          data={'connection_id': self.conn.id, 'path': '/docs', 'csrf_token': self._csrf()},
                          files={'files': ('../../evil.txt', b'x')})
        self.assertEqual(r.json()['uploaded'], ['evil.txt'])
        self.assertTrue(os.path.exists(os.path.join(self.root, 'docs', 'evil.txt')))

    def test_mkdir_rename_delete(self):
        c = self.conn.id
        self.assertNotIn('error', self._rpc('/sftp_file_manager/mkdir', connection_id=c, path='/newdir'))
        self.assertTrue(os.path.isdir(os.path.join(self.root, 'newdir')))
        self.assertNotIn('error', self._rpc('/sftp_file_manager/rename', connection_id=c, old='/newdir', new='/renamed'))
        self.assertTrue(os.path.isdir(os.path.join(self.root, 'renamed')))
        self.assertNotIn('error', self._rpc('/sftp_file_manager/delete', connection_id=c, path='/renamed', is_dir=True))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'renamed')))
        self.assertNotIn('error', self._rpc('/sftp_file_manager/delete', connection_id=c, path='/hello.txt'))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'hello.txt')))

    def test_delete_nonempty_dir_error(self):
        data = self._rpc('/sftp_file_manager/delete', connection_id=self.conn.id, path='/docs', is_dir=True)
        self.assertIn('error', data)

    def test_user_group_cannot_write(self):
        user = self.env['res.users'].create({
            'name': 'sftp plain', 'login': 'sftp_plain', 'password': 'sftp_plain_pw',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('sftp_file_manager.group_sftp_user').id])],
        })
        self.authenticate('sftp_plain', 'sftp_plain_pw')
        ok = self._rpc('/sftp_file_manager/list', connection_id=self.conn.id, path='/')
        self.assertNotIn('error', ok, ok)
        bad = self._rpc('/sftp_file_manager/mkdir', connection_id=self.conn.id, path='/x')
        self.assertIn('error', bad)
        self.assertFalse(os.path.exists(os.path.join(self.root, 'x')))
        self.assertTrue(user)

    def test_no_group_denied(self):
        self.env['res.users'].create({
            'name': 'nogrp', 'login': 'nogrp', 'password': 'nogrp_pw',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.authenticate('nogrp', 'nogrp_pw')
        data = self._rpc('/sftp_file_manager/list', connection_id=self.conn.id, path='/')
        self.assertIn('error', data)
