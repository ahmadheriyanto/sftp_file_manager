"""Thin protocol adapters giving SFTP and FTP/FTPS the same small API.

Every adapter raises ``OSError`` for remote errors. Entries are plain dicts:
``{'name', 'is_dir', 'size', 'mtime', 'mode'}``.
"""
import ftplib
import posixpath
import socket
import ssl
import stat as statmod
import time
from datetime import datetime, timezone


class SftpClient:
    def __init__(self, ssh, sftp):
        self._ssh, self._sftp = ssh, sftp

    def close(self):
        self._ssh.close()

    def normalize(self, path):
        return self._sftp.normalize(path)

    def listdir(self, path):
        out = []
        for a in self._sftp.listdir_attr(path):
            mode = a.st_mode or 0
            is_dir = statmod.S_ISDIR(mode)
            if statmod.S_ISLNK(mode):
                try:
                    is_dir = statmod.S_ISDIR(self._sftp.stat(posixpath.join(path, a.filename)).st_mode)
                except IOError:
                    pass
            out.append({'name': a.filename, 'is_dir': is_dir, 'size': a.st_size or 0,
                        'mtime': a.st_mtime or 0, 'mode': statmod.filemode(mode)})
        return out

    def size(self, path):
        return self._sftp.stat(path).st_size

    def open_read(self, path):
        """Return (iterator of bytes chunks, close callable)."""
        fh = self._sftp.open(path, 'rb')
        fh.prefetch()

        def gen():
            while True:
                data = fh.read(256 * 1024)
                if not data:
                    return
                yield data
        return gen(), fh.close

    def write(self, path, stream):
        self._sftp.putfo(stream, path)

    def mkdir(self, path):
        self._sftp.mkdir(path)

    def rename(self, old, new):
        self._sftp.rename(old, new)

    def remove(self, path):
        self._sftp.remove(path)

    def rmdir(self, path):
        self._sftp.rmdir(path)


def _ftp_errors(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except ftplib.Error as e:
            raise OSError(str(e))
        except (socket.timeout, ssl.SSLError) as e:
            raise OSError(str(e))
    wrapper.__name__ = fn.__name__
    return wrapper


class FtpClient:
    def __init__(self, ftp):
        self._ftp = ftp
        self._ftp.encoding = 'utf-8'

    def close(self):
        try:
            self._ftp.quit()
        except Exception:
            self._ftp.close()

    @_ftp_errors
    def normalize(self, path):
        if path in ('', '.'):
            return self._ftp.pwd()
        cur = self._ftp.pwd()
        try:
            self._ftp.cwd(path)
            return self._ftp.pwd()
        finally:
            self._ftp.cwd(cur)

    @_ftp_errors
    def listdir(self, path):
        out = []
        try:
            for name, f in self._ftp.mlsd(path, facts=['type', 'size', 'modify', 'perm']):
                t = f.get('type', '')
                if t in ('cdir', 'pdir') or name in ('.', '..'):
                    continue
                mtime = 0
                if f.get('modify'):
                    try:
                        mtime = datetime.strptime(f['modify'][:14], '%Y%m%d%H%M%S').replace(
                            tzinfo=timezone.utc).timestamp()
                    except ValueError:
                        pass
                out.append({'name': name, 'is_dir': t == 'dir', 'size': int(f.get('size') or 0),
                            'mtime': mtime, 'mode': f.get('perm', '')})
            return out
        except ftplib.error_perm as e:
            if not str(e).startswith(('500', '501', '502', '504')):
                raise
        # Server has no MLSD: fall back to parsing a Unix-style LIST.
        lines = []
        self._ftp.retrlines('LIST ' + path, lines.append)
        for line in lines:
            parts = line.split(None, 8)
            if len(parts) < 9 or parts[8] in ('.', '..'):
                continue
            name = parts[8].split(' -> ')[0]
            out.append({'name': name, 'is_dir': parts[0].startswith('d'),
                        'size': int(parts[4]) if parts[4].isdigit() else 0,
                        'mtime': 0, 'mode': parts[0]})
        return out

    @_ftp_errors
    def size(self, path):
        self._ftp.voidcmd('TYPE I')
        return self._ftp.size(path) or 0

    @_ftp_errors
    def open_read(self, path):
        self._ftp.voidcmd('TYPE I')
        conn = self._ftp.transfercmd('RETR ' + path)
        ftp = self._ftp

        def gen():
            while True:
                data = conn.recv(256 * 1024)
                if not data:
                    return
                yield data

        def close():
            try:
                conn.close()
                ftp.voidresp()
            except Exception:
                pass
        return gen(), close

    @_ftp_errors
    def write(self, path, stream):
        self._ftp.voidcmd('TYPE I')
        self._ftp.storbinary('STOR ' + path, stream)

    @_ftp_errors
    def mkdir(self, path):
        self._ftp.mkd(path)

    @_ftp_errors
    def rename(self, old, new):
        self._ftp.rename(old, new)

    @_ftp_errors
    def remove(self, path):
        self._ftp.delete(path)

    @_ftp_errors
    def rmdir(self, path):
        self._ftp.rmd(path)


def connect_ftp(host, port, user, password, timeout, tls, verify):
    if tls:
        ctx = ssl.create_default_context()
        if not verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        ftp = ftplib.FTP_TLS(context=ctx, timeout=timeout)
    else:
        ftp = ftplib.FTP(timeout=timeout)
    ftp.connect(host, port)
    ftp.login(user or 'anonymous', password or '')
    if tls:
        ftp.prot_p()
    ftp.set_pasv(True)
    return FtpClient(ftp)
