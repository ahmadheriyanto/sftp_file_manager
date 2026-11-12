import posixpath

from werkzeug.wrappers import Response

from odoo import http, _
from odoo.exceptions import UserError
from odoo.http import request

CHUNK = 256 * 1024


class SftpController(http.Controller):

    def _conn(self, connection_id):
        rec = request.env['sftp.connection'].browse(int(connection_id)).exists()
        if not rec:
            raise UserError(_("Connection not found."))
        rec.check_access('read')
        return rec

    @staticmethod
    def _clean(path):
        path = posixpath.normpath(path or '/')
        return path if path.startswith('/') else '/' + path

    @http.route('/sftp_file_manager/list', type='jsonrpc', auth='user')
    def list_dir(self, connection_id, path=None):
        rec = self._conn(connection_id)
        client = rec._open()
        try:
            if not path:
                path = rec.start_path or client.normalize('.')
            path = client.normalize(path)
            entries = client.listdir(path)
            entries.sort(key=lambda e: (not e['is_dir'], e['name'].lower()))
            return {'path': path, 'entries': entries}
        except OSError as e:
            raise UserError(_("Cannot read %(path)s: %(err)s", path=path, err=e))
        finally:
            client.close()

    @http.route('/sftp_file_manager/download', type='http', auth='user')
    def download(self, connection_id, path, **kw):
        rec = self._conn(connection_id)
        path = self._clean(path)
        client = rec._open()
        try:
            size = client.size(path)
            chunks, close_remote = client.open_read(path)
        except Exception as e:
            client.close()
            return request.make_response(str(e), status=404)

        resp = Response(chunks, direct_passthrough=True, mimetype='application/octet-stream')
        if size:
            resp.headers['Content-Length'] = str(size)
        resp.headers['Content-Disposition'] = http.content_disposition(posixpath.basename(path))
        resp.call_on_close(lambda: (close_remote(), client.close()))
        return resp

    @http.route('/sftp_file_manager/upload', type='http', auth='user', methods=['POST'])
    def upload(self, connection_id, path, **kw):
        rec = self._conn(connection_id)
        path = self._clean(path)
        client = rec._open()
        names, error = [], None
        try:
            for f in request.httprequest.files.getlist('files'):
                name = posixpath.basename(f.filename.replace('\\', '/'))
                if not name:
                    continue
                client.write(posixpath.join(path, name), f.stream)
                names.append(name)
        except Exception as e:
            error = str(e)
        finally:
            client.close()
        return request.make_json_response({'uploaded': names, 'error': error})

    def _write_op(self, connection_id, fn):
        rec = self._conn(connection_id)
        rec.check_access('write')
        client = rec._open()
        try:
            fn(client)
        except OSError as e:
            raise UserError(str(e))
        finally:
            client.close()
        return True

    @http.route('/sftp_file_manager/mkdir', type='jsonrpc', auth='user')
    def mkdir(self, connection_id, path):
        return self._write_op(connection_id, lambda s: s.mkdir(self._clean(path)))

    @http.route('/sftp_file_manager/rename', type='jsonrpc', auth='user')
    def rename(self, connection_id, old, new):
        return self._write_op(connection_id, lambda s: s.rename(self._clean(old), self._clean(new)))

    @http.route('/sftp_file_manager/delete', type='jsonrpc', auth='user')
    def delete(self, connection_id, path, is_dir=False):
        p = self._clean(path)
        return self._write_op(connection_id, lambda s: s.rmdir(p) if is_dir else s.remove(p))
