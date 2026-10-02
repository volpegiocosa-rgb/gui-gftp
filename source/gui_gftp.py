#!/usr/bin/env python3
"""G3: 2 colonne (locale | remoto) in GTK3, FTP/FTPS/SFTP (backends.py), drag & drop e trasferimenti."""
import json
import os
import posixpath
import sys
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import backends  # noqa: E402


CSS = b"""
entry, button, combobox button { border-radius: 8px; min-height: 30px; }
button.flat { background: transparent; box-shadow: none; }
.pane-title { font-weight: bold; }
.status { opacity: .7; font-size: 90%; }
treeview.view { padding: 2px; }
treeview.view header button { font-weight: bold; }
paned > separator { min-width: 6px; }
"""
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui-gftp.svg")

URI_TARGET = Gtk.TargetEntry.new("text/uri-list", 0, 0)
REMOTE_TARGET = Gtk.TargetEntry.new("application/x-gui-gftp", Gtk.TargetFlags.SAME_APP, 1)
REMOTE_ATOM = Gdk.Atom.intern("application/x-gui-gftp", False)


PROTOS = ("FTP", "FTPS", "SFTP")
MAX_PROFILES = 10
CONF = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                    "gui-gftp", "profiles.json")


def load_profiles(path=CONF):
    """Ultimi profili, piu recente prima. Mai la password: solo proto, host, port, user."""
    try:
        with open(path) as f:
            return [p for p in json.load(f) if isinstance(p, dict) and p.get("host")][:MAX_PROFILES]
    except (OSError, ValueError):
        return []


def save_profile(p, path=CONF):
    profs = [q for q in load_profiles(path) if q != p]
    profs.insert(0, p)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(profs[:MAX_PROFILES], f)
    os.replace(path + ".tmp", path)


def _secret_attrs(p):
    return {k: str(p[k]) for k in ("proto", "host", "port", "user")}


def _secret_schema():
    gi.require_version("Secret", "1")  # import pigro: libsecret solo quando serve
    from gi.repository import Secret
    return Secret, Secret.Schema.new("it.gui-gftp.profile", Secret.SchemaFlags.NONE,
                                     {k: Secret.SchemaAttributeType.STRING for k in ("proto", "host", "port", "user")})


def store_password(p, password):
    """Password nel portachiavi di sistema (libsecret), mai nel file dei profili."""
    Secret, schema = _secret_schema()
    Secret.password_store_sync(schema, _secret_attrs(p), Secret.COLLECTION_DEFAULT,
                               f"gui-gftp {profile_label(p)}", password, None)


def lookup_password(p):
    Secret, schema = _secret_schema()
    return Secret.password_lookup_sync(schema, _secret_attrs(p), None) or ""


def profile_label(p):
    return f"{p['proto']}  {p['user'] + '@' if p['user'] else ''}{p['host']}" + (f":{p['port']}" if p["port"] else "")


def run_async(fn, done):
    """Esegue fn in un thread, chiama done(result, errore) nel main loop."""
    def work():
        try:
            res, err = fn(), None
        except Exception as e:  # errori di rete/auth vanno mostrati, non fatali
            res, err = None, e
        GLib.idle_add(done, res, err)
    threading.Thread(target=work, daemon=True).start()


class Pane(Gtk.Box):
    drag_targets = [URI_TARGET]  # cosa offre il pannello come sorgente
    drop_targets = [URI_TARGET, REMOTE_TARGET]  # cosa accetta come destinazione

    def __init__(self, title, fs=None, path=""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.fs, self.path, self.gen, self.peer = None, "", 0, None
        self.entry = Gtk.Entry()
        self.entry.connect("activate", lambda e: self.go(e.get_text()))
        up = Gtk.Button.new_from_icon_name("go-up", Gtk.IconSize.BUTTON)
        up.connect("clicked", lambda _: self.fs and self.go(self.fs.parent(self.path)))
        up.get_style_context().add_class("flat")
        self.bar = Gtk.Box(spacing=6, margin=8)
        lbl = Gtk.Label(label=title)
        lbl.get_style_context().add_class("pane-title")
        self.bar.pack_start(lbl, False, False, 4)
        self.bar.pack_start(up, False, False, 0)
        self.bar.pack_start(self.entry, True, True, 0)

        self.store = Gtk.ListStore(str, str, str, str, bool)  # nome, dim, data, icona, is_dir
        self.view = Gtk.TreeView(model=self.store)
        self.view.connect("row-activated", self.on_activated)
        self.view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, self.drag_targets, Gdk.DragAction.COPY)
        self.view.enable_model_drag_dest(self.drop_targets, Gdk.DragAction.COPY)
        self.view.connect("drag-data-get", self.on_drag_get)
        self.view.connect("drag-data-received", self.on_drag_received)
        col = Gtk.TreeViewColumn("Nome")
        icon, text = Gtk.CellRendererPixbuf(xpad=4), Gtk.CellRendererText(ypad=4)
        col.pack_start(icon, False)
        col.pack_start(text, True)
        col.add_attribute(icon, "icon-name", 3)
        col.add_attribute(text, "text", 0)
        col.set_min_width(120)
        col.set_fixed_width(300)
        self.view.append_column(col)
        for i, name in ((1, "Dim."), (2, "Modificato")):
            self.view.append_column(Gtk.TreeViewColumn(name, Gtk.CellRendererText(ypad=4), text=i))
        for c in self.view.get_columns():
            c.set_resizable(True)  # larghezza colonne regolabile trascinando il bordo dell'intestazione
        sw = Gtk.ScrolledWindow()
        sw.add(self.view)

        self.status = Gtk.Label(xalign=0, margin=6)
        self.status.get_style_context().add_class("status")
        self.pack_start(self.bar, False, False, 0)
        self.pack_start(sw, True, True, 0)
        self.pack_start(self.status, False, False, 2)
        if fs:
            self.set_fs(fs, path)

    def set_fs(self, fs, path):
        if self.fs:
            self.fs.close()
        self.fs = fs
        self.go(path)

    def go(self, path):
        fs = self.fs
        path = fs.norm(path)
        self.gen += 1
        gen = self.gen
        self.status.set_text("Caricamento...")

        def done(rows, err):
            if gen != self.gen or fs is not self.fs:  # risposta obsoleta
                return
            if err:
                self.status.set_text(f"Errore: {err}")
                return
            self.path = path
            self.entry.set_text(path)
            self.status.set_text(f"{len(rows)} elementi")
            self.store.clear()
            for name, is_dir, size, mtime in rows:
                self.store.append((
                    name, "" if is_dir else str(size),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)) if mtime else "",
                    "folder" if is_dir else "text-x-generic", is_dir,
                ))
        run_async(lambda: fs.list(path), done)

    def on_activated(self, view, tpath, _col):
        row = self.store[tpath]
        if row[4]:
            self.go(self.fs.join(self.path, row[0]))


    def selected(self):
        model, paths = self.view.get_selection().get_selected_rows()
        return [(model[p][0], model[p][4]) for p in paths]

    def on_drag_get(self, view, ctx, sel, info, time_):
        items = self.selected()
        if self.fs is None or not items:
            return
        if info == 0:  # file:// URI, per file manager e pannello locale
            sel.set_uris([GLib.filename_to_uri(self.fs.join(self.path, n)) for n, _ in items])
        else:  # percorsi remoti "d|f<TAB>percorso", per il pannello locale
            data = "\n".join(("d" if d else "f") + "\t" + self.fs.join(self.path, n) for n, d in items)
            sel.set(REMOTE_ATOM, 8, data.encode())

    def on_drag_received(self, view, ctx, x, y, sel, info, time_):
        ok = False
        try:
            if self.fs is None:
                return
            if info == 0:
                src_fs = backends.LocalFS()
                paths = [GLib.filename_from_uri(u)[0] for u in sel.get_uris()]
                items = [(p, os.path.isdir(p)) for p in paths]
            elif self.peer and self.peer.fs:
                src_fs = self.peer.fs
                items = [(ln[2:], ln[0] == "d") for ln in sel.get_data().decode().split("\n")]
            else:
                return
            dest = self.path
            hit = view.get_dest_row_at_pos(x, y)
            if hit and hit[0] is not None and self.store[hit[0]][4]:
                dest = self.fs.join(self.path, self.store[hit[0]][0])
            ok = self.start_transfer(src_fs, items, dest)
        finally:
            Gtk.drag_finish(ctx, ok, False, time_)

    def start_transfer(self, src_fs, items, dest):
        dst_fs = self.fs
        local_only = isinstance(src_fs, backends.LocalFS) and isinstance(dst_fs, backends.LocalFS)
        items = [(p, d) for p, d in items if not (local_only and src_fs.parent(p) == dest)]  # no copia su se stesso
        if not items:
            return False
        self.status.set_text("Controllo destinazione...")

        def listed(rows, err):
            if err:
                self.status.set_text(f"Errore: {err}")
                return
            exist = {r[0] for r in rows}
            clash = [os.path.basename(p) for p, _ in items if os.path.basename(p) in exist]
            if clash:
                dlg = Gtk.MessageDialog(transient_for=self.get_toplevel(), message_type=Gtk.MessageType.QUESTION,
                                        buttons=Gtk.ButtonsType.YES_NO,
                                        text=f"Sovrascrivere {len(clash)} elementi esistenti?")
                dlg.format_secondary_text(", ".join(clash[:5]) + ("..." if len(clash) > 5 else ""))
                yes = dlg.run() == Gtk.ResponseType.YES
                dlg.destroy()
                if not yes:
                    self.status.set_text("Annullato")
                    return

            def work():
                for p, d in items:
                    backends.copy_tree(src_fs, p, dst_fs, dst_fs.join(dest, os.path.basename(p)), d,
                                       lambda n: GLib.idle_add(self.status.set_text, f"Trasferimento: {n}"))
                return len(items)

            def finished(n, err):
                self.status.set_text(f"Errore: {err}" if err else f"{n} elementi copiati")
                for pane in (self, self.peer):  # aggiorna entrambi: la sorgente puo essere la stessa cartella
                    if pane and pane.fs:
                        pane.go(pane.path)
            run_async(work, finished)
        run_async(lambda: dst_fs.list(dest), listed)
        return True


class RemotePane(Pane):
    drag_targets = [REMOTE_TARGET]
    drop_targets = [URI_TARGET]

    def __init__(self):
        super().__init__("Remoto")
        self.profiles = []
        self.prof = Gtk.ComboBoxText()
        self.prof.connect("changed", self.on_profile)
        self.proto = Gtk.ComboBoxText()
        for p in PROTOS:
            self.proto.append_text(p)
        self.proto.set_active(0)
        self.host = Gtk.Entry(placeholder_text="host", width_chars=14)
        self.port = Gtk.Entry(placeholder_text="porta", width_chars=5)
        self.user = Gtk.Entry(placeholder_text="utente", width_chars=10)
        self.pw = Gtk.Entry(placeholder_text="password", width_chars=10, visibility=False)
        btn = Gtk.Button(label="Connetti")
        btn.get_style_context().add_class("suggested-action")
        btn.connect("clicked", self.on_connect)
        for w in (self.host, self.port, self.user, self.pw):
            w.connect("activate", self.on_connect)
        conn = Gtk.Box(spacing=6, margin=8, margin_bottom=0)
        for w in (self.prof, self.proto, self.host, self.port, self.user, self.pw, btn):
            conn.pack_start(w, w is self.host, True, 0)
        self.conn = conn  # impaginata da main() sopra i due pannelli, per allinearli
        self.refresh_profiles()
        if self.profiles:
            self.prof.set_active(0)  # ultimo profilo usato: resta solo la password

    def refresh_profiles(self):
        self.profiles = load_profiles()
        self.prof.remove_all()
        self.prof.append_text("Profili recenti...") if not self.profiles else None
        for p in self.profiles:
            self.prof.append_text(profile_label(p))

    def on_profile(self, combo):
        i = combo.get_active()
        if i < 0 or i >= len(self.profiles):
            return
        p = self.profiles[i]
        self.proto.set_active(PROTOS.index(p["proto"]) if p["proto"] in PROTOS else 0)
        self.host.set_text(p["host"])
        self.port.set_text(str(p["port"]) if p["port"] else "")
        self.user.set_text(p["user"])
        self.pw.set_text("")
        self.pw.grab_focus()
        run_async(lambda: lookup_password(p), lambda pw, err: self.fill_password(p, pw))

    def fill_password(self, p, pw):
        i = self.prof.get_active()  # ignora la risposta se nel frattempo e stato scelto un altro profilo
        if pw and 0 <= i < len(self.profiles) and self.profiles[i] == p and not self.pw.get_text():
            self.pw.set_text(pw)

    def on_connect(self, _w):
        proto, host = self.proto.get_active_text(), self.host.get_text().strip()
        port = self.port.get_text().strip()
        if not host or (port and not port.isdigit()):
            self.status.set_text("Host mancante o porta non valida")
            return
        args = (proto, host, int(port) if port else 0, self.user.get_text(), self.pw.get_text())
        self.status.set_text("Connessione...")

        def done(fs, err):
            if err:
                self.status.set_text(f"Errore: {err}")
                return
            self.set_fs(fs, fs.home)
            prof = {"proto": args[0], "host": args[1], "port": args[2], "user": args[3]}
            if args[4]:
                run_async(lambda: store_password(prof, args[4]),
                          lambda _r, e: e and self.status.set_text(f"Password non salvata: {e}"))
            try:
                save_profile(prof)
                self.prof.handler_block_by_func(self.on_profile)
                self.refresh_profiles()
                self.prof.set_active(0)
                self.prof.handler_unblock_by_func(self.on_profile)
            except OSError as e:
                self.status.set_text(f"Connesso, profilo non salvato: {e}")
        run_async(lambda: backends.connect(*args), done)


def main():
    GLib.set_prgname("gui-gftp")  # deve coincidere con StartupWMClass nel .desktop
    css = Gtk.CssProvider()
    css.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    try:
        Gtk.Window.set_default_icon_from_file(ICON)  # anche senza install.sh
    except GLib.Error:
        pass
    win = Gtk.Window()
    win.set_titlebar(Gtk.HeaderBar(title="gui-gftp", show_close_button=True))
    win.set_default_size(1000, 600)
    win.connect("destroy", Gtk.main_quit)
    paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
    local, remote = Pane("Locale", backends.LocalFS(), os.path.expanduser("~")), RemotePane()
    local.peer, remote.peer = remote, local
    paned.pack1(local, True, False)
    paned.pack2(remote, True, False)
    paned.set_position(500)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.pack_start(remote.conn, False, False, 0)
    box.pack_start(paned, True, True, 0)
    win.add(box)
    win.show_all()
    Gtk.main()


def selftest():
    import tempfile
    fs = backends.LocalFS()
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "b.txt"), "w").write("xx")
        open(os.path.join(d, "A.txt"), "w").write("")
        os.mkdir(os.path.join(d, "zdir"))
        rows = fs.list(d)
        assert [r[0] for r in rows] == ["zdir", "A.txt", "b.txt"], rows
        assert [r[2] for r in rows if r[0] == "b.txt"] == [2]
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "c", "p.json")
        assert load_profiles(f) == []
        a = {"proto": "FTP", "host": "a", "port": 0, "user": "u"}
        b = {"proto": "SFTP", "host": "b", "port": 22, "user": ""}
        save_profile(a, f), save_profile(b, f), save_profile(a, f)
        assert load_profiles(f) == [a, b], load_profiles(f)  # a riusato risale in testa, senza duplicati
        assert oct(os.stat(f).st_mode & 0o777) == "0o600"
        for i in range(15):
            save_profile({**a, "host": f"h{i}"}, f)
        assert len(load_profiles(f)) == MAX_PROFILES
        open(f, "w").write("{rotto")
        assert load_profiles(f) == []
    print("selftest ok")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
