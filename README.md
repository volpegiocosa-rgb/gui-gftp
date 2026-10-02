# gui-gftp

A lightweight two-pane graphical FTP / FTPS / SFTP client for Linux, with drag & drop.
Python 3 + GTK 3. Written for Debian 13, where `gftp-gtk` is no longer packaged.

- Two panes (local | remote), FileZilla style
- Drag & drop: file manager → either pane, local ↔ remote; multiple selection, folders copied recursively
- Protocols: FTP, FTPS (`ftplib`), SFTP (`paramiko`, loaded only on first SFTP connection)
- Recent connection profiles (last 10); passwords are stored in the system keyring (libsecret), never in a file
- Resizable columns, confirmation before overwriting existing files
- Streaming transfers: memory stays flat (100 MB download measured with no RAM growth)
- Low footprint: about 25 MB PSS at idle, about 38 MB with SFTP loaded (see [`output/ram.md`](output/ram.md))

## Requirements

Debian / Ubuntu:

```
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-secret-1 python3-paramiko
```

Tests only: `python3-pyftpdlib` (plus `python3-openssl` for FTPS).

## Run

```
python3 source/gui_gftp.py
```

To add an entry to the Internet menu (with icon):

```
source/install.sh            # install for the current user
source/install.sh --remove   # uninstall
```

## Usage

1. Pick a recent profile, or fill in protocol / host / port / user / password, then **Connetti** (Connect).
2. Double-click a folder to enter it; use the up button or the path bar to navigate.
3. Drag files or folders between the panes, or from your file manager. Dropping on a folder copies into it.
4. With SFTP and an empty password, `paramiko` tries your SSH keys and agent.

The interface language is Italian.

## Tests

```
python3 source/gui_gftp.py --selftest
python3 source/test_backends.py
```

`test_backends.py` runs FTP (pyftpdlib) and SFTP (in-process paramiko server) against localhost, including recursive upload/download.

## Known limitations

- Remote → file manager drag is not supported; drag to the local pane instead.
- FTPS is implemented but not covered by the automated tests.
- SFTP rejects hosts missing from `known_hosts`; there is no interactive key confirmation.
- No progress bar and no resume: an interrupted transfer leaves a partial file.
- The saved password cannot be forgotten from the UI; remove the `gui-gftp ...` entries with Seahorse ("Passwords and Keys").

More details (in Italian): [`docs/gui-gftp.md`](docs/gui-gftp.md).
