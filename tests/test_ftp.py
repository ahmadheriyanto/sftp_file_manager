"""FTP tests: the same suites as test_sftp.py, run against a local pyftpdlib server.

Needs the optional test dependency ``pyftpdlib`` (tests are skipped without it).
"""
import os
import shutil
import tempfile
import threading
import unittest

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .test_sftp import SftpCommon, TestSftpController

# ----------------------------------------------------------------------
# FTP (plain) -- needs the optional test dependency pyftpdlib
# ----------------------------------------------------------------------
try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import ThreadedFTPServer
except ImportError:  # pragma: no cover
    ThreadedFTPServer = None


class FtpCommon(SftpCommon):
    @classmethod
    def _setup_sftp(cls):
        cls.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.root, 'docs'))
        with open(os.path.join(cls.root, 'hello.txt'), 'wb') as f:
            f.write(b'hello world')
        with open(os.path.join(cls.root, 'docs', 'a.txt'), 'wb') as f:
            f.write(b'A')
        auth = DummyAuthorizer()
        auth.add_user('tester', 'secret', cls.root, perm='elradfmw')
        handler = type('H', (FTPHandler,), {'authorizer': auth})
        srv = ThreadedFTPServer(('127.0.0.1', 0), handler)
        cls.server = type('S', (), {'port': srv.address[1]})()
        t = threading.Thread(target=srv.serve_forever, kwargs={'handle_exit': False}, daemon=True)
        t.start()
        cls.addClassCleanup(srv.close_all)
        cls.addClassCleanup(shutil.rmtree, cls.root, True)

    def _make_conn(self, **kw):
        kw.setdefault('protocol', 'ftp')
        return super()._make_conn(**kw)


@unittest.skipIf(ThreadedFTPServer is None, 'pyftpdlib not installed')
@tagged('post_install', '-at_install', 'sftp_file_manager')
class TestFtpModel(FtpCommon, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sftp()

    def test_login_ok(self):
        rec = self._make_conn()
        self.assertEqual(rec.action_test_connection()['params']['type'], 'success')

    def test_wrong_password(self):
        with self.assertRaises(UserError):
            self._make_conn(password='bad').action_test_connection()

    def test_unreachable(self):
        with self.assertRaises(UserError):
            self._make_conn(port=1, timeout=2).action_test_connection()

    def test_anonymous_ignores_credentials(self):
        # pyftpdlib test server has no anonymous user -> login must be attempted as anonymous and fail
        with self.assertRaises(UserError):
            self._make_conn(anonymous=True, username=False, password=False).action_test_connection()

    def test_username_required(self):
        with self.assertRaises(UserError):
            self._make_conn(username=False)

    def test_protocol_onchange_port(self):
        rec = self.env['sftp.connection'].new({'protocol': 'ftp'})
        rec._onchange_protocol()
        self.assertEqual(rec.port, 21)


@unittest.skipIf(ThreadedFTPServer is None, 'pyftpdlib not installed')
@tagged('post_install', '-at_install', 'sftp_file_manager')
class TestFtpController(FtpCommon, TestSftpController):
    """Re-runs the whole controller suite against an FTP server."""
    allow_inherited_tests_method = True
