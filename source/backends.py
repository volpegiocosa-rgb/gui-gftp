"""Backend filesystem: Local, FTP/FTPS (ftplib), SFTP (paramiko, import pigro).

Interfaccia comune: list(path) -> [(nome, is_dir, size, mtime)], norm(path), join(a, b), parent(p),
mkdir(path), download(path, fileobj), upload(path, fileobj), close().
Ogni backend remoto serializza le operazioni con self.lock (ftplib non e thread-safe).
"""
import ftplib
import os
import posixpath
import shutil
import stat
import threading
import time


def sort_rows(rows):
    return sorted(rows, key=lambda r: (not r[1], r[0].lower()))


class LocalFS:
    def norm(self, p):
        return os.path.abspath(os.path.expanduser(p))

    join = staticmethod(os.path.join)
    parent = staticmethod(os.path.dirname)

    def list(self, path):
        rows = []
        with os.scandir(path) as it:
            for e in it:
                try:
                    st = e.stat()
                except OSError:
                    continue
                rows.append((e.name, stat.S_ISDIR(st.st_mode), st.st_size, st.st_mtime))
        return sort_rows(rows)

    def mkdir(self, path):
        os.makedirs(path, exist_ok=True)

    def download(self, path, fileobj):
        with open(path, "rb") as f:
            shutil.copyfileobj(f, fileobj)

    def upload(self, path, fileobj):
        with open(path, "wb") as f:
            shutil.copyfileobj(fileobj, f)

    def close(self):
        pass


class _PosixFS:
    def norm(self, p):
        return posixpath.normpath(p) if p else "/"

    join = staticmethod(posixpath.join)
    parent = staticmethod(posixpath.dirname)
    lock = None  # impostato dai backend remoti


class FtpFS(_PosixFS):
    def __init__(self, host, port, user, password, tls=False, timeout=15):
        self.c = (ftplib.FTP_TLS if tls else ftplib.FTP)(timeout=timeout)
        self.c.connect(host, port or 21)
        self.c.login(user or "anonymous", password or "anonymous@")
        if tls:
            self.c.prot_p()
        self.home = self.c.pwd()
        self.lock = threading.Lock()

    def list(self, path):
        with self.lock:
            entries = list(self.c.mlsd(path, facts=["type", "size", "modify"]))
        rows = []
        for name, f in entries:
            t = f.get("type", "")
            if t in ("cdir", "pdir") or name in (".", ".."):
                continue
            m = f.get("modify")
            mtime = time.mktime(time.strptime(m[:14], "%Y%m%d%H%M%S")) if m else 0
            rows.append((name, t == "dir", int(f.get("size", 0)), mtime))
        return sort_rows(rows)

    def mkdir(self, path):
        with self.lock:
            try:
                self.c.mkd(path)
            except ftplib.error_perm:  # esiste gia: i file successivi segnalano un errore reale
                pass

    def download(self, path, fileobj):
        with self.lock:
            self.c.retrbinary("RETR " + path, fileobj.write)

    def upload(self, path, fileobj):
        with self.lock:
            self.c.storbinary("STOR " + path, fileobj)

    def close(self):
        try:
            self.c.quit()
        except Exception:
            self.c.close()


class SftpFS(_PosixFS):
    def __init__(self, host, port, user, password, timeout=15):
        import paramiko  # ponytail: import pigro, costa RAM (cryptography) solo se si usa SFTP

        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        # ponytail: host sconosciuti rifiutati (default paramiko); gestione conferma chiave in G4 se serve
        self.ssh.connect(host, port or 22, user or None, password or None, timeout=timeout)
        self.c = self.ssh.open_sftp()
        self.home = self.c.normalize(".")
        self.lock = threading.Lock()

    def list(self, path):
        with self.lock:
            attrs = self.c.listdir_attr(path)
        return sort_rows([
            (a.filename, stat.S_ISDIR(a.st_mode or 0), a.st_size or 0, a.st_mtime or 0)
            for a in attrs
        ])

    def mkdir(self, path):
        with self.lock:
            try:
                self.c.mkdir(path)
            except OSError:  # esiste gia: i file successivi segnalano un errore reale
                pass

    def download(self, path, fileobj):
        with self.lock:
            self.c.getfo(path, fileobj)

    def upload(self, path, fileobj):
        with self.lock:
            self.c.putfo(fileobj, path)

    def close(self):
        self.ssh.close()


def connect(proto, host, port, user, password):
    if proto == "FTP":
        return FtpFS(host, port, user, password)
    if proto == "FTPS":
        return FtpFS(host, port, user, password, tls=True)
    if proto == "SFTP":
        return SftpFS(host, port, user, password)
    raise ValueError(proto)


def copy_tree(src_fs, src, dst_fs, dst, is_dir, progress=lambda name: None):
    """Copia file o directory (ricorsivo). Almeno uno tra src_fs e dst_fs deve essere LocalFS."""
    if is_dir:
        dst_fs.mkdir(dst)
        for name, d, _, _ in src_fs.list(src):
            copy_tree(src_fs, src_fs.join(src, name), dst_fs, dst_fs.join(dst, name), d, progress)
        return
    progress(posixpath.basename(src))
    if isinstance(dst_fs, LocalFS):
        with open(dst, "wb") as f:
            src_fs.download(src, f)
    else:
        with open(src, "rb") as f:
            dst_fs.upload(dst, f)
