{
    'name': 'SFTP File Manager',
    'version': '19.0.1.0.1',
    'summary': 'WinSCP/FileZilla-like SFTP / FTP / FTPS client: manage connections, browse, upload and download files',
    'category': 'Tools',
    'description': """
SFTP File Manager
=================
A WinSCP / FileZilla-like SFTP, FTP and FTPS client inside Odoo: define server connections,
browse remote folders, download/upload files (drag & drop), create folders,
rename and delete.

Components to install
---------------------
* Odoo modules: base, web (standard, nothing else required).
* Python library on the Odoo server:  pip install paramiko   (>= 2.9)
  Use the same virtualenv that runs Odoo, then restart the Odoo service.
* Remote server: SFTP (SSH subsystem), or FTP / FTPS (explicit TLS) on the configured port.
  FTP/FTPS use Python's standard ftplib - nothing extra to install.
  Plain FTP sends the password unencrypted; prefer SFTP or FTPS.

Setup
-----
1. Install the module, then give users the group
   "SFTP File Manager: User" (browse/transfer) or "Manager" (also edit connections).
2. SFTP File Manager > Connections: create a server, press "Test Connection".
   The host key is pinned on first connect (trust on first use).
3. SFTP File Manager > File Browser: pick a server and work with files.
""",
    'author': 'Ahmad Heriyanto',
    'images': ['static/description/banner.png'],
    'website': 'https://www.aplikasierp.online',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'external_dependencies': {'python': ['paramiko']},
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/sftp_connection_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sftp_file_manager/static/src/scss/*.scss',
            'sftp_file_manager/static/src/js/*.js',
            'sftp_file_manager/static/src/xml/*.xml',
        ],
        'web.assets_tests': [
            'sftp_file_manager/static/tests/*.js',
        ],
    },
    'application': True,
    'installable': True,
}
