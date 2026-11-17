import base64
import hashlib
import io
import logging

import paramiko

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .clients import FtpClient, SftpClient, connect_ftp  # noqa: F401

_logger = logging.getLogger(__name__)


class _PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Trust-on-first-use: remember the fingerprint, refuse if it later changes."""

    def __init__(self, record):
        self.record = record

    def missing_host_key(self, client, hostname, key):
        fp = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
        known = self.record.host_fingerprint
        if not known:
            self.record.sudo().host_fingerprint = fp
        elif known != fp:
            raise UserError(_(
                "Host key for %(host)s has CHANGED (expected %(old)s, got %(new)s). "
                "Possible man-in-the-middle attack. If the server was reinstalled, "
                "clear the 'Host Fingerprint' field on the connection.",
                host=self.record.host, old=known, new=fp))


class SftpConnection(models.Model):
    _name = 'sftp.connection'
    _description = 'File Transfer Server Connection'
    _order = 'name'

    name = fields.Char(required=True)
    protocol = fields.Selection(
        [('sftp', 'SFTP'), ('ftp', 'FTP')], string='File Protocol', default='sftp', required=True)
    encryption = fields.Selection(
        [('none', 'No encryption'), ('tls', 'TLS/SSL Explicit encryption')],
        default='none', required=True, help="FTP only. Plain FTP sends the password unencrypted.")
    verify_tls = fields.Boolean(
        string='Verify TLS Certificate', default=True,
        help="FTP with TLS only. Untick to accept self-signed certificates (not recommended).")
    anonymous = fields.Boolean(string='Anonymous login', help="FTP only.")
    host = fields.Char(required=True)
    port = fields.Integer(default=22, required=True)
    username = fields.Char()
    auth_type = fields.Selection(
        [('password', 'Password'), ('key', 'Private Key')],
        default='password', required=True)
    password = fields.Char(groups='sftp_file_manager.group_sftp_manager')
    private_key = fields.Text(
        string='Private Key (PEM/OpenSSH)', groups='sftp_file_manager.group_sftp_manager')
    key_passphrase = fields.Char(groups='sftp_file_manager.group_sftp_manager')
    start_path = fields.Char(string='Start Folder', default='/')
    timeout = fields.Integer(default=15)
    host_fingerprint = fields.Char(
        readonly=False, help="SFTP only. Learned on first connection (trust on first use). "
                             "Clear it to accept a new host key.")
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    def _load_pkey(self):
        self.ensure_one()
        data = (self.sudo().private_key or '').strip()
        if not data:
            raise UserError(_("No private key configured."))
        passphrase = self.sudo().key_passphrase or None
        for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
            try:
                return cls.from_private_key(io.StringIO(data), password=passphrase)
            except (paramiko.SSHException, ValueError):
                continue
        raise UserError(_("Could not read the private key (unsupported type or wrong passphrase)."))

    def _open(self):
        """Return a connected client (see clients.py). Caller must call .close()."""
        self.ensure_one()
        rec = self.sudo()
        if rec.protocol == 'ftp':
            login, pwd = (rec.username, rec.password)
            if rec.anonymous:
                login, pwd = "anonymous", "anonymous@"
            try:
                return connect_ftp(rec.host, rec.port, login, pwd,
                                   rec.timeout, rec.encryption == 'tls', rec.verify_tls)
            except Exception as e:
                raise UserError(_("Connection to %(host)s failed: %(err)s", host=rec.host, err=e))
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(_PinnedHostKeyPolicy(rec))
        kwargs = dict(hostname=rec.host, port=rec.port, username=rec.username,
                      timeout=rec.timeout, banner_timeout=rec.timeout, auth_timeout=rec.timeout,
                      allow_agent=False, look_for_keys=False)
        if rec.auth_type == 'key':
            kwargs['pkey'] = rec._load_pkey()
        else:
            kwargs['password'] = rec.password or ''
        try:
            ssh.connect(**kwargs)
            sftp = ssh.open_sftp()
        except UserError:
            ssh.close()
            raise
        except Exception as e:  # paramiko/socket errors
            ssh.close()
            raise UserError(_("Connection to %(host)s failed: %(err)s", host=rec.host, err=e))
        return SftpClient(ssh, sftp)

    @api.constrains('username', 'anonymous', 'protocol')
    def _check_username(self):
        for rec in self:
            if not rec.username and not (rec.protocol == 'ftp' and rec.anonymous):
                raise UserError(_("Username is required."))

    @api.onchange('protocol')
    def _onchange_protocol(self):
        self.port = 22 if self.protocol == 'sftp' else 21
        if self.protocol != 'sftp':
            self.auth_type = 'password'
        else:
            self.anonymous = False

    def action_test_connection(self):
        self.ensure_one()
        client = self._open()
        try:
            cwd = client.normalize('.')
        except OSError as e:
            raise UserError(str(e))
        finally:
            client.close()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _("Connection OK"), 'type': 'success', 'sticky': False,
                       'message': _("Connected to %(host)s (home: %(cwd)s)", host=self.host, cwd=cwd)},
        }

    def action_open_browser(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'sftp_file_manager.browser',
                'name': self.name, 'params': {'connection_id': self.id}}

    @api.model
    def get_connections(self):
        return self.search_read([], ['name', 'host', 'username', 'start_path', 'protocol'])
