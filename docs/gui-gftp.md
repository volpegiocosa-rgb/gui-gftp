# gui-gftp

GUI a 2 colonne (locale | remoto) per FTP, FTPS, SFTP, con drag & drop. Python 3 + GTK3, nessun backend gftp.

## Avvio

```
python3 source/gui_gftp.py
```

Dipendenze Debian: `python3-gi`, `gir1.2-gtk-3.0` (già presenti), `gir1.2-secret-1` (portachiavi), `python3-paramiko` (SFTP; caricato solo alla prima connessione SFTP).
Solo per i test: `python3-pyftpdlib` (+ `python3-openssl` per FTPS).

## Menu applicazioni

`source/install.sh` installa la voce **Internet** (categoria `Network;FileTransfer`) e l'icona in `~/.local/share`, senza toccare la scrivania. `source/install.sh --remove` la elimina. Va rilanciato se si sposta la cartella del progetto.

## Uso

- Pannello Remoto: scegli un profilo recente o compila protocollo/host/porta/utente/password, poi *Connetti*.
- Doppio click su una cartella per entrare, pulsante "su" o barra del percorso per navigare.
- Drag & drop (selezione multipla, cartelle ricorsive):
  - file manager → pannello locale o remoto;
  - locale ↔ remoto;
  - rilascio su una cartella = copia dentro quella cartella.
- Se i nomi esistono già in destinazione: richiesta di conferma per sovrascrivere tutto (sì) o annullare (no).
- SFTP con password vuota: `paramiko` prova chiave SSH e agent.

## File

| File | Contenuto |
|---|---|
| `source/gui_gftp.py` | GUI, profili, drag & drop. `--selftest` per i test dei profili |
| `source/backends.py` | `LocalFS`, `FtpFS` (FTP/FTPS), `SftpFS`, `copy_tree` |
| `source/install.sh`, `source/gui-gftp.svg` | Voce di menu e icona |
| `source/test_backends.py` | Test di rete locali (FTP con pyftpdlib, SFTP con server paramiko in-process) |
| `~/.config/gui-gftp/profiles.json` | Ultimi 10 profili, permessi 0600. Mai la password (sta nel portachiavi) |

## Verifiche

```
python3 source/gui_gftp.py --selftest
python3 source/test_backends.py
```

## Limiti noti

- Remoto → file manager non supportato: trascinare prima sul pannello locale.
- FTPS non testato (manca `python3-openssl` per il server di test).
- SFTP: host non presenti in `known_hosts` sono rifiutati; nessuna conferma interattiva della chiave.
- Nessuna barra di progresso (solo il nome del file corrente), nessuna ripresa dei trasferimenti: un trasferimento interrotto lascia file parziali.
- La password è salvata nel portachiavi di sistema (libsecret), mai in `profiles.json`. Non c'è un pulsante "dimentica": usare Seahorse.
- Il drag con il mouse è stato provato solo a mano dall'utente; i test automatici chiamano `start_transfer` direttamente.

## RAM (misurata, vedi `output/ram.md`)

Metrica adottata: PSS (memoria realmente attribuibile al processo, librerie condivise divise tra i processi). Tetto: 60 MB.

Il requisito originale "più leggero di FileZilla" è stato rimosso su decisione dell'utente (nessun confronto misurato). `gui-gftp.md` resta invariato.
