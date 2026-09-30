"""Run backup/restore from the terminal. Restore requires a stopped service."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path
from config import Settings
from store import Store
from backups import Backups


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['backup','restore','init'])
    p.add_argument('source',nargs='?')
    p.add_argument('--service-stopped',action='store_true')
    args=p.parse_args()
    os.umask(0o077)
    settings=Settings.from_env()
    store=Store(settings.data/'alba.sqlite3')
    manager=Backups(store,settings)
    if args.action=='backup':
        print(manager.create('manual'))
    elif args.action=='restore':
        if not args.service_stopped or not args.source:
            p.error('Ferma alba.service e passa SOURCE --service-stopped.')
        if shutil.which('systemctl') and subprocess.run(['systemctl','is-active','--quiet','alba.service']).returncode==0:
            p.error('alba.service è ancora attivo: il ripristino è vietato finché non viene fermato.')
        manager.create('manual')
        restored=settings.data/'restored.sqlite3'
        manager.restore(args.source,restored)
        store.close()
        for suffix in ('-wal','-shm'):
            Path(str(settings.data/'alba.sqlite3')+suffix).unlink(missing_ok=True)
        os.replace(restored,settings.data/'alba.sqlite3')
        print('Ripristino completato. Le vecchie chiavi e sessioni sono revocate.')
        return
    else:
        print('Database e chiavi locali inizializzati.')
    store.close()


if __name__=='__main__':
    main()
