"""Tiny in-process SFTP server (paramiko) rooted in a local directory, for tests."""
import os
import socket
import threading

import paramiko
from paramiko import SFTPAttributes, SFTPHandle, SFTPServer, SFTPServerInterface
from paramiko.sftp import SFTP_NO_SUCH_FILE, SFTP_OK, SFTP_FAILURE


class _Handle(SFTPHandle):
    def stat(self):
        try:
            return SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)


class _Iface(SFTPServerInterface):
    ROOT = None

    def _real(self, path):
        return os.path.normpath(self.ROOT + os.sep + os.path.normpath('/' + path.lstrip('/')))

    def list_folder(self, path):
        try:
            out = []
            for f in os.listdir(self._real(path)):
                a = SFTPAttributes.from_stat(os.lstat(os.path.join(self._real(path), f)))
                a.filename = f
                out.append(a)
            return out
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    def stat(self, path):
        try:
            return SFTPAttributes.from_stat(os.stat(self._real(path)))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    lstat = stat

    def open(self, path, flags, attr):
        real = self._real(path)
        try:
            fd = os.open(real, flags | getattr(os, 'O_BINARY', 0), 0o666)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        if flags & os.O_WRONLY:
            mode = 'wb'
        elif flags & os.O_RDWR:
            mode = 'r+b'
        else:
            mode = 'rb'
        f = os.fdopen(fd, mode)
        h = _Handle(flags)
        h.filename = real
        h.readfile = f
        h.writefile = f
        return h

    def remove(self, path):
        try:
            os.remove(self._real(path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rename(self, old, new):
        try:
            os.rename(self._real(old), self._real(new))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def mkdir(self, path, attr):
        try:
            os.mkdir(self._real(path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rmdir(self, path):
        try:
            os.rmdir(self._real(path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def canonicalize(self, path):
        return os.path.normpath('/' + path.lstrip('/')) if path not in ('', '.') else '/'


class _Auth(paramiko.ServerInterface):
    def __init__(self, user, password, pubkey):
        self.user, self.password, self.pubkey = user, password, pubkey

    def get_allowed_auths(self, username):
        return 'password,publickey'

    def check_auth_password(self, username, password):
        ok = username == self.user and self.password is not None and password == self.password
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        ok = self.pubkey is not None and username == self.user and key == self.pubkey
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED


class SftpTestServer:
    def __init__(self, root, user='tester', password='secret', pubkey=None, host_key=None):
        self.root = root
        self.host_key = host_key or paramiko.RSAKey.generate(2048)
        iface = type('Iface', (_Iface,), {'ROOT': root})
        self._iface = iface
        self._auth = (user, password, pubkey)
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(10)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            t = paramiko.Transport(conn)
            t.add_server_key(self.host_key)
            t.set_subsystem_handler('sftp', SFTPServer, self._iface)
            try:
                t.start_server(server=_Auth(*self._auth))
            except Exception:
                pass

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass
