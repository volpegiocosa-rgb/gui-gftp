# Misure RAM gui-gftp

Metodo: `/proc/self/status` (VmRSS) e `/proc/self/smaps_rollup` (Pss), finestra aperta, display X11. Tetto concordato: 60 MB, metrica PSS.

| Scenario | RSS | PSS |
|---|---|---|
| Avvio, a riposo | 58,8 MB | 23,7 MB |
| FTP connesso, 501 file listati | 60,1 MB | 24,8 MB |
| Dopo download FTP 100 MB | 60,2 MB | 24,9 MB |
| Con `paramiko` caricato (SFTP), a riposo (misura precedente) | 75,2 MB | 38,4 MB |

Il trasferimento è in streaming: 100 MB scaricati non aumentano la RAM.

## Confronto con FileZilla

Rimosso su decisione dell'utente (2026-10-02): FileZilla non viene installato solo per la misura. Resta il tetto assoluto di 60 MB (PSS).
