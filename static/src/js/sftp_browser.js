/** @odoo-module **/
import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { Dialog } from "@web/core/dialog/dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

function fmtSize(n) {
    if (n < 1024) return n + " B";
    const u = ["KB", "MB", "GB", "TB"];
    let i = -1;
    do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
    return n.toFixed(1) + " " + u[i];
}

export class PromptDialog extends Component {
    static template = "sftp_file_manager.PromptDialog";
    static components = { Dialog };
    static props = {
        title: String,
        label: { type: String, optional: true },
        value: { type: String, optional: true },
        confirm: Function,
        close: Function,
    };

    setup() {
        this.state = useState({ value: this.props.value || "" });
        this.input = useRef("input");
        onMounted(() => {
            this.input.el?.focus();
            this.input.el?.select();
        });
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            this.onConfirm();
        }
    }

    onConfirm() {
        const value = this.state.value.trim();
        if (!value) {
            return;
        }
        this.props.confirm(value);
        this.props.close();
    }
}

export class SftpBrowser extends Component {
    static template = "sftp_file_manager.Browser";
    static props = ["*"];

    setup() {
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.fileInput = useRef("fileInput");
        this.state = useState({
            connections: [], connectionId: null, path: "", entries: [],
            loading: false, drag: false,
        });
        onWillStart(async () => {
            this.state.connections = await rpc("/web/dataset/call_kw/sftp.connection/get_connections", {
                model: "sftp.connection", method: "get_connections", args: [], kwargs: {},
            });
            const pid = this.props.action?.params?.connection_id;
            if (pid) {
                await this.connect(pid);
            }
        });
    }

    fmtSize = fmtSize;
    fmtDate(ts) { return ts ? new Date(ts * 1000).toLocaleString() : ""; }

    get crumbs() {
        const parts = this.state.path.split("/").filter(Boolean);
        const out = [{ label: "/", path: "/" }];
        parts.forEach((p, i) => out.push({ label: p, path: "/" + parts.slice(0, i + 1).join("/") }));
        return out;
    }

    async onSelectConnection(ev) {
        const id = parseInt(ev.target.value) || null;
        if (id) await this.connect(id);
        else { this.state.connectionId = null; this.state.entries = []; }
    }

    async connect(id) {
        this.state.connectionId = id;
        await this.load(null);
    }

    async load(path) {
        this.state.loading = true;
        try {
            const res = await rpc("/sftp_file_manager/list", {
                connection_id: this.state.connectionId, path,
            });
            this.state.path = res.path;
            this.state.entries = res.entries;
        } finally {
            this.state.loading = false;
        }
    }

    join(name) {
        return (this.state.path === "/" ? "" : this.state.path) + "/" + name;
    }

    refresh() { return this.load(this.state.path); }
    up() {
        const parts = this.state.path.split("/").filter(Boolean);
        parts.pop();
        return this.load("/" + parts.join("/"));
    }

    open(e) {
        if (e.is_dir) return this.load(this.join(e.name));
        return this.download(e);
    }

    download(e) {
        const qs = new URLSearchParams({ connection_id: this.state.connectionId, path: this.join(e.name) });
        browser.location.href = "/sftp_file_manager/download?" + qs;
    }

    onUploadClick() { this.fileInput.el.click(); }
    onFilesPicked(ev) { return this.upload(ev.target.files).finally(() => (ev.target.value = "")); }
    onDragOver(ev) { ev.preventDefault(); this.state.drag = true; }
    onDragLeave() { this.state.drag = false; }
    onDrop(ev) {
        ev.preventDefault();
        this.state.drag = false;
        if (this.state.connectionId) return this.upload(ev.dataTransfer.files);
    }

    async upload(files) {
        if (!files.length) return;
        const fd = new FormData();
        fd.append("csrf_token", odoo.csrf_token);
        fd.append("connection_id", this.state.connectionId);
        fd.append("path", this.state.path);
        for (const f of files) fd.append("files", f);
        this.state.loading = true;
        try {
            const resp = await fetch("/sftp_file_manager/upload", { method: "POST", body: fd });
            const res = await resp.json();
            if (res.error) {
                this.notification.add(res.error, { type: "danger", sticky: true });
            }
            if (res.uploaded.length) {
                this.notification.add(`Uploaded ${res.uploaded.length} file(s)`, { type: "success" });
            }
        } catch (err) {
            this.notification.add(String(err), { type: "danger" });
        }
        await this.refresh();
    }

    prompt(title, label, value) {
        return new Promise((resolve) => {
            this.dialog.add(
                PromptDialog,
                { title, label, value, confirm: resolve },
                { onClose: () => resolve(null) }
            );
        });
    }

    confirmDialog(body) {
        return new Promise((resolve) => {
            this.dialog.add(
                ConfirmationDialog,
                {
                    title: "Confirm",
                    body,
                    confirmLabel: "Delete",
                    confirmClass: "btn-danger",
                    confirm: () => resolve(true),
                    cancel: () => resolve(false),
                },
                { onClose: () => resolve(false) }
            );
        });
    }

    async mkdir() {
        const name = await this.prompt("New Folder", "Folder name");
        if (!name) return;
        await rpc("/sftp_file_manager/mkdir", { connection_id: this.state.connectionId, path: this.join(name) });
        await this.refresh();
    }

    async rename(e) {
        const name = await this.prompt("Rename", "New name", e.name);
        if (!name || name === e.name) return;
        await rpc("/sftp_file_manager/rename", {
            connection_id: this.state.connectionId, old: this.join(e.name), new: this.join(name),
        });
        await this.refresh();
    }

    async remove(e) {
        if (!(await this.confirmDialog(`Delete ${e.is_dir ? "folder" : "file"} "${e.name}"?`))) return;
        await rpc("/sftp_file_manager/delete", {
            connection_id: this.state.connectionId, path: this.join(e.name), is_dir: e.is_dir,
        });
        await this.refresh();
    }
}

registry.category("actions").add("sftp_file_manager.browser", SftpBrowser);
