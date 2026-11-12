/** @odoo-module **/
import { registry } from "@web/core/registry";

const row = (name) => `.o_sftp_browser tr.o_sftp_row:contains('${name}')`;

registry.category("web_tour.tours").add("sftp_file_manager_tour", {
    steps: () => [
        {
            content: "pick the server",
            trigger: ".o_sftp_browser select.form-select",
            run() {
                const sel = document.querySelector(".o_sftp_browser select.form-select");
                const opt = [...sel.options].find((o) => o.value);
                sel.value = opt.value;
                sel.dispatchEvent(new Event("change", { bubbles: true }));
            },
        },
        { content: "listing shows file", trigger: row("hello.txt") },
        { content: "listing shows folder", trigger: row("docs") },
        // ---- open folder / go up
        { content: "open docs", trigger: `${row("docs")} button[title='Open']`, run: "click" },
        { content: "docs content", trigger: row("a.txt") },
        { content: "up", trigger: ".o_sftp_browser button:contains('Up')", run: "click" },
        { content: "back at root", trigger: row("hello.txt") },
        // ---- new folder
        { content: "new folder", trigger: ".o_sftp_browser button:contains('New Folder')", run: "click" },
        { content: "type name", trigger: ".modal input.form-control", run: "edit newdir" },
        { content: "ok", trigger: ".modal button:contains('OK')", run: "click" },
        { content: "folder created", trigger: row("newdir") },
        // ---- rename
        { content: "rename", trigger: `${row("newdir")} button[title='Rename']`, run: "click" },
        { content: "rename value", trigger: ".modal input.form-control", run: "edit renamed" },
        { content: "ok", trigger: ".modal button:contains('OK')", run: "click" },
        { content: "renamed", trigger: row("renamed") },
        { content: "old name gone", trigger: ".o_sftp_browser:not(:has(tr.o_sftp_row:contains('newdir')))" },
        // ---- upload
        {
            content: "upload file",
            trigger: ".o_sftp_browser button:contains('Upload')",
            run() {
                const dt = new DataTransfer();
                dt.items.add(new File(["tour upload"], "up.txt", { type: "text/plain" }));
                const input = document.querySelector(".o_sftp_browser input[type=file]");
                input.files = dt.files;
                input.dispatchEvent(new Event("change", { bubbles: true }));
            },
        },
        { content: "uploaded", trigger: row("up.txt") },
        // ---- delete file
        { content: "delete file", trigger: `${row("up.txt")} button[title='Delete']`, run: "click" },
        { content: "confirm", trigger: ".modal button.btn-danger", run: "click" },
        { content: "file gone", trigger: ".o_sftp_browser:not(:has(tr.o_sftp_row:contains('up.txt')))" },
        // ---- delete folder
        { content: "delete folder", trigger: `${row("renamed")} button[title='Delete']`, run: "click" },
        { content: "confirm", trigger: ".modal button.btn-danger", run: "click" },
        { content: "folder gone", trigger: ".o_sftp_browser:not(:has(tr.o_sftp_row:contains('renamed')))" },
        // ---- cancel on prompt does nothing
        { content: "new folder", trigger: ".o_sftp_browser button:contains('New Folder')", run: "click" },
        { content: "cancel", trigger: ".modal button:contains('Cancel')", run: "click" },
        { content: "done", trigger: ".o_sftp_browser tr.o_sftp_row:contains('hello.txt')" },
    ],
});

const field = (name) => `.o_form_view .o_field_widget[name='${name}']`;
const pick = (name, label) => [
    { content: `open ${name}`, trigger: `${field(name)} input`, run: "click" },
    {
        content: `choose ${label}`,
        trigger: `.o_select_menu_menu .o_select_menu_item:contains('${label}')`,
        run() {
            const item = [...document.querySelectorAll(".o_select_menu_menu .o_select_menu_item")]
                .find((i) => i.textContent.trim().startsWith(label) && !i.textContent.trim().startsWith("S" + label));
            item.click();
        },
    },
];
const absent = (sel) => `.o_form_view:not(:has(${sel}))`;

registry.category("web_tour.tours").add("sftp_file_manager_form_tour", {
    steps: () => [
        { content: "default is SFTP, port 22", trigger: `${field("port")} input:value(22)` },
        { content: "auth_type visible for SFTP", trigger: field("auth_type") },
        { content: "no encryption field for SFTP", trigger: absent(field("encryption")) },
        ...pick("protocol", "FTP"),
        { content: "port reset to 21 (onchange)", trigger: `${field("port")} input:value(21)` },
        { content: "encryption visible for FTP", trigger: field("encryption") },
        { content: "anonymous visible for FTP", trigger: field("anonymous") },
        { content: "auth_type hidden for FTP", trigger: absent(field("auth_type")) },
        { content: "private key hidden for FTP", trigger: absent(field("private_key")) },
        { content: "fingerprint hidden for FTP", trigger: absent(field("host_fingerprint")) },
        { content: "verify tls hidden without TLS", trigger: absent(field("verify_tls")) },
        ...pick("encryption", "TLS/SSL"),
        { content: "verify tls shown", trigger: field("verify_tls") },
        { content: "tick anonymous", trigger: `${field("anonymous")} input`, run: "click" },
        { content: "username hidden when anonymous", trigger: absent(field("username")) },
        { content: "password hidden when anonymous", trigger: absent(field("password")) },
        { content: "untick anonymous", trigger: `${field("anonymous")} input`, run: "click" },
        { content: "name", trigger: `${field("name")} input`, run: "edit Form tour" },
        { content: "host", trigger: `${field("host")} input`, run: "edit ftp.example.com" },
        { content: "username", trigger: `${field("username")} input`, run: "edit bob" },
        { content: "save", trigger: ".o_form_button_save", run: "click" },
        { content: "saved: browser button appears", trigger: ".o_statusbar_buttons button:contains('Open Browser')" },
        ...pick("protocol", "SFTP"),
        { content: "auth_type back", trigger: field("auth_type") },
        { content: "encryption hidden again", trigger: absent(field("encryption")) },
        { content: "save again", trigger: ".o_form_button_save", run: "click" },
        { content: "saved", trigger: ".o_form_view .o_form_saved" },
    ],
});
