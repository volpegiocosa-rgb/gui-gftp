#!/usr/bin/env python3
"""Test di rete locali: FTP (pyftpdlib) e SFTP (server paramiko in-process). Run: python3 test_backends.py"""
import os
import socket
import tempfile
import threading

import paramiko
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

import backends


def make_tree(root):
    open(os.path.join(root, "b.txt"), "w").write("xx")
    open(os.path.join(root, "A.txt"), "w").write("")
    os.mkdir(os.path.join(root, "zdir"))
    open(os.path.join(root, "zdir", "in.txt"), "w").write("1")


def check(fs, base):
    rows = fs.list(base)
    assert [r[0] for r in rows] == ["zdir", "A.txt", "b.txt"], rows
    assert rows[0][1] is True and rows[2][1] is False
    assert rows[2][2] == 2, rows
    sub = fs.list(fs.join(base, "zdir"))
    assert [r[0] for r in sub] == ["in.txt"], sub
    assert fs.parent(fs.join(base, "zdir")) == base.rstrip("/") or base == "/"


def check_transfer(fs, base):
    """Upload di una directory (con sottodirectory) e download, contenuto identico."""
    loc = backends.LocalFS()
    with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as back:
        os.makedirs(os.path.join(src, "d", "sub"))
        open(os.path.join(src, "d", "f.bin"), "wb").write(os.urandom(300_000))
        open(os.path.join(src, "d", "sub", "g.txt"), "w").write("ciao")
        dst = fs.join(base, "up")
        backends.copy_tree(loc, os.path.join(src, "d"), fs, dst, True)
        assert [r[0] for r in fs.list(dst)] == ["sub", "f.bin"], fs.list(dst)
        backends.copy_tree(fs, dst, loc, os.path.join(back, "d"), True)
        for rel in ("f.bin", os.path.join("sub", "g.txt")):
            assert open(os.path.join(src, "d", rel), "rb").read() == open(os.path.join(back, "d", rel), "rb").read(), rel


def test_ftp(root):
    auth = DummyAuthorizer()
    auth.add_user("u", "p", root, perm="elradfmw")
    h = type("H", (FTPHandler,), {"authorizer": auth})
    srv = FTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, kwargs={"handle_exit": False}, daemon=True).start()
    fs = backends.connect("FTP", "127.0.0.1", srv.address[1], "u", "p")
    check(fs, fs.home)
    check_transfer(fs, fs.home)
    fs.close()
    try:
        backends.connect("FTP", "127.0.0.1", srv.address[1], "u", "sbagliata")
        raise SystemExit("login errato accettato")
    except Exception as e:
        assert "530" in str(e), e
    srv.close_all()
    print("FTP ok")


class _SFTP(paramiko.SFTPServerInterface):
    root = ""

    def _p(self, p):
        return os.path.join(self.root, p.lstrip("/"))

    def canonicalize(self, path):
        return "/" + os.path.relpath(os.path.normpath("/" + path.lstrip("/")), "/").lstrip(".")

    def list_folder(self, path):
        out = []
        for n in os.listdir(self._p(path)):
            a = paramiko.SFTPAttributes.from_stat(os.stat(os.path.join(self._p(path), n)))
            a.filename = n
            out.append(a)
        return out

    def stat(self, path):
        return paramiko.SFTPAttributes.from_stat(os.stat(self._p(path)))

    lstat = stat

    def mkdir(self, path, attr):
        os.mkdir(self._p(path))
        return paramiko.SFTP_OK

    def open(self, path, flags, attr):
        mode = "wb" if flags & os.O_WRONLY or flags & os.O_RDWR else "rb"
        f = open(self._p(path), mode)
        h = paramiko.SFTPHandle(flags)
        h.filename = self._p(path)
        h.readfile = h.writefile = f
        return h


class _Auth(paramiko.ServerInterface):
    def check_auth_password(self, u, p):
        return paramiko.AUTH_SUCCESSFUL if (u, p) == ("u", "p") else paramiko.AUTH_FAILED

    def get_allowed_auths(self, u):
        return "password"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED


def test_sftp(root):
    key = paramiko.RSAKey.generate(2048)
    _SFTP.root = root
    ls = socket.socket()
    ls.bind(("127.0.0.1", 0))
    ls.listen(5)

    def serve():
        while True:
            try:
                c, _ = ls.accept()
            except OSError:
                return
            t = paramiko.Transport(c)
            t.add_server_key(key)
            t.set_subsystem_handler("sftp", paramiko.SFTPServer, _SFTP)
            t.start_server(server=_Auth())

    threading.Thread(target=serve, daemon=True).start()
    port = ls.getsockname()[1]
    # known_hosts di sistema non contiene il server di test: si accetta la chiave solo qui
    orig = paramiko.SSHClient.connect

    def connect(self, *a, **k):
        self.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return orig(self, *a, **k)
    paramiko.SSHClient.connect = connect
    try:
        fs = backends.connect("SFTP", "127.0.0.1", port, "u", "p")
        check(fs, "/")
        check_transfer(fs, "/")
        fs.close()
        try:
            backends.connect("SFTP", "127.0.0.1", port, "u", "sbagliata")
            raise SystemExit("login errato accettato")
        except paramiko.AuthenticationException:
            pass
    finally:
        paramiko.SSHClient.connect = orig
        ls.close()
    print("SFTP ok")


if __name__ == "__main__":
    for test in (test_ftp, test_sftp):
        with tempfile.TemporaryDirectory() as d:
            make_tree(d)
            test(d)
