"""Browser (tour) tests: drives the real OWL file browser against a local SFTP / FTP server."""
import os
import unittest

from odoo.tests import HttpCase, tagged

from .test_ftp import FtpCommon, ThreadedFTPServer
from .test_sftp import SftpCommon


class UiScenario:
    def _run_ui(self):
        self._make_conn()
        self.start_tour('/odoo/action-sftp_file_manager.action_sftp_browser',
                        'sftp_file_manager_tour', login='admin', timeout=120)
        # everything the tour created has been removed again, original content untouched
        self.assertTrue(os.path.exists(os.path.join(self.root, 'hello.txt')))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'renamed')))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'newdir')))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'up.txt')))


@tagged('post_install', '-at_install', 'sftp_file_manager')
class TestConnectionFormUi(HttpCase):
    def test_form_fields_follow_protocol(self):
        self.start_tour('/odoo/action-sftp_file_manager.action_sftp_connection/new',
                        'sftp_file_manager_form_tour', login='admin', timeout=120)
        rec = self.env['sftp.connection'].search([('name', '=', 'Form tour')])
        self.assertEqual(rec.protocol, 'sftp')
        self.assertEqual(rec.port, 22)  # switching back to SFTP resets the port
        self.assertEqual(rec.host, 'ftp.example.com')


@tagged('post_install', '-at_install', 'sftp_file_manager')
class TestSftpUi(SftpCommon, UiScenario, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sftp()

    def test_ui_flow(self):
        self._run_ui()


@unittest.skipIf(ThreadedFTPServer is None, 'pyftpdlib not installed')
@tagged('post_install', '-at_install', 'sftp_file_manager')
class TestFtpUi(FtpCommon, UiScenario, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sftp()

    def test_ui_flow(self):
        self._run_ui()
