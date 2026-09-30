"""Trusted host administrator CLI; run as the service user. Never expose this CLI as a public endpoint."""
import argparse,os
from config import Settings
from store import Store
from security import Keys,secret_file
from backups import Backups
from engine import Engine
from service import Service,Incoming

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['users','allow','deny','web-key','password','revoke','backup','stats']);parser.add_argument('user_id',nargs='?',type=int);parser.add_argument('--root');args=parser.parse_args();os.umask(0o077)
    settings=Settings.from_env(args.root);store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));actor=settings.admins[0] if settings.admins else int(store.setting('bootstrap_admin','0'))
    if not actor or not service.is_admin(actor):parser.error('Configura ADMIN_IDS oppure completa /bootstrap prima di usare il CLI amministratore.')
    uid=args.user_id
    if args.action in ('allow','deny','web-key','password','revoke') and uid is None:parser.error('Specifica USER_ID.')
    if args.action=='users':print(service.admin(Incoming(actor,'Admin',actor,'private',''),['users']).text)
    elif args.action in ('allow','deny'):print(service.admin(Incoming(actor,'Admin',actor,'private',''),[args.action,str(uid)]).text)
    elif args.action=='web-key':
        token=keys.issue(actor,uid,'web',settings.key_ttl);print((settings.public_url+'/#web_key='+token) if settings.public_url else token);store.audit(actor,'terminal_web_key',uid)
    elif args.action=='password':
        username,password=keys.set_web_password(actor,uid,'admin' if service.is_admin(uid) else None);print('Nome utente:',username);print('Password nuova:',password);store.audit(actor,'terminal_password',uid)
    elif args.action=='revoke':keys.revoke(actor,uid);print('Accessi revocati.')
    elif args.action=='backup':print(service.backups.create('manual'))
    elif args.action=='stats':print(service.stats(None))
    store.close()
if __name__=='__main__':main()
