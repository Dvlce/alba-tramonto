"""Permissions and commands shared by Telegram and authenticated private web chat."""
from __future__ import annotations
import asyncio
import json
import os
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from learning import record_feedback
from store import Scope
from memory import retrieve, relevant_messages, evaluate_memories
from exports import export_document
from runtime_features import Performance,touch_activity,Capacity
from engine import CRISIS

HELP = '''Sono Alba. Possiamo riflettere insieme su difficoltà quotidiane, relazioni e scelte.
Non sostituisco una professionista e non faccio diagnosi. I messaggi vengono conservati localmente;
Telegram resta un servizio online. Nei gruppi uso solo il contesto pubblico di quel gruppo.

/profile — scheda personale; /profile tone empathy 0.8 — cambia tono
/memory — memorie; /memory add categoria testo — salva un dato dichiarato
/memory exclude ID — esclude una memoria dall’esportazione
/timeline — eventi e cambiamenti; /search testo — cerca in questa chat
/stats — risorse e statistiche
/export_key — chiave monouso, valida 15 minuti; /export_key revoke — revoca
/export_key admin — autorizzazione esplicita per un’esportazione amministrativa
/export CHIAVE — info personale JSON
/export_personality CHIAVE — configurazione AI personale
/export_prompt CHIAVE — system prompt personale
/web_key — accesso al sito dalla propria chat Telegram
/web_password — crea o rinnova la password del sito; /web_password revoke — revoca
/notte — associa questa chat privata ai messaggi autonomi Notte (admin); /notte off — disattiva
/stop — interrompe la tua risposta in corso in questa chat
/forget ID — elimina memoria e fonti; /forget all confermo — cancella conversazioni e memorie
/memory_key — autorizza 15 minuti di lettura amministrativa; /memory_key revoke — revoca
/feedback utile|ripetitiva|fuori_tema|piu_concreta|troppo_lunga — adatta le risposte
/backup — snapshot locale (solo amministratore)
/group on|off|auto on|auto off — solo admin autorizzato e admin del gruppo

Le chiavi si richiedono in privato. Ogni file richiede una nuova chiave.
Una cancellazione elimina anche i backup precedenti di questo sistema per impedire il recupero dei dati cancellati.'''


@dataclass
class Incoming:
    uid: int
    name: str
    chat_id: int
    kind: str
    text: str
    message_id: int | None = None
    reply_id: int | None = None
    reply_to_bot: bool = False
    mention_bot: bool = False
    mentions: tuple = ()
    thread_id: int = 0
    transport: str = 'telegram'

    @property
    def scope(self):
        return Scope('user',self.uid) if self.kind=='private' else Scope('group',self.chat_id)


@dataclass
class Result:
    text: str = ''
    filename: str | None = None
    document: bytes | None = None
    cancelled: bool = False
    login_url: str | None = None
    break_notice: dict | None = None


class Service:
    def __init__(self,store,settings,keys,engine,backups):
        self.store,self.settings,self.keys,self.engine,self.backups = store,settings,keys,engine,backups
        self.group_admin_check = None
        self.telegram_avatar=None
        self.request_memory_access=None
        self.rates = {}
        self.scope_locks = {}
        self.active_responses = {}
        self.performance=Performance(settings.root)
        self.capacity=Capacity(settings.max_online)
        self.last_interaction=time.time()
        self.maintenance_task=None
        self.maintenance_notify=None
        self.maintenance={'running':False,'message':'','last_run':store.setting('memory_ai_last')}
        keys.is_admin = self.is_admin
        for uid in set(settings.admins+settings.allowed):
            if uid in settings.admins or not store.rows('SELECT user_id FROM access_blocks WHERE user_id=?',(uid,)):
                store.authorize(uid,settings.max_users)

    def is_admin(self,uid):
        return uid in self.settings.admins or str(uid)==self.store.setting('bootstrap_admin')

    def private(self,event,telegram=False):
        if event.kind!='private' or (event.transport=='telegram' and event.chat_id!=event.uid):
            raise PermissionError('Questo comando è disponibile solo nella tua chat privata.')
        if telegram and event.transport!='telegram':
            raise PermissionError('Richiedi la chiave nella tua chat privata Telegram.')

    def should_reply(self,event):
        if event.kind=='private' or event.text.startswith('/') or event.mention_bot or event.reply_to_bot:
            return True
        groups = self.store.rows('SELECT * FROM groups WHERE id=?',(event.chat_id,))
        if groups and groups[0]['auto_mode'] and len(event.text)>35 and time.time()-groups[0]['last_auto']>120:
            if '?' in event.text or 'alba' in event.text.lower():
                self.store.execute('UPDATE groups SET last_auto=? WHERE id=?',(time.time(),event.chat_id))
                return True
        return False

    async def handle(self,event):
        if event.text.strip().split() and event.text.strip().split()[0].split('@',1)[0].lower()=='/stop':
            if not self.store.allowed(event.uid):
                return Result('Utente non autorizzato.')
            if event.kind=='private' and event.transport=='telegram' and event.chat_id!=event.uid:
                return Result('Questo comando è disponibile solo nella tua chat privata.')
            entry=self.active_responses.get((event.scope.key,event.uid))
            if not entry or entry['task'].done():
                return Result('Non c’è una tua risposta da interrompere in questa chat.')
            entry['stopped']=True
            entry['task'].cancel()
            self.store.audit(event.uid,'response_cancel',event.uid)
            return Result('Risposta interrotta.')
        async with self.scope_locks.setdefault(event.scope.key,asyncio.Lock()):
            return await self._handle(event)

    async def _handle(self,event):
        if event.kind not in ('private','group','supergroup'):
            return Result()
        self.store.register(event.uid,event.name)
        self.store.execute('INSERT OR IGNORE INTO telegram_chats VALUES(?,?,?)',(event.chat_id,event.kind,''))
        try:
            if event.text.startswith('/bootstrap '):
                self.private(event,telegram=True)
                if self.settings.admins or self.store.setting('bootstrap_admin'):
                    raise PermissionError('Amministratore già configurato.')
                expected = self.store.setting('bootstrap_digest')
                given = self.keys.digest(event.text.split(' ',1)[1].strip())
                if not expected or not secrets.compare_digest(expected,given):
                    raise PermissionError('Chiave iniziale non valida.')
                self.store.set_setting('bootstrap_admin',event.uid)
                self.store.set_setting('bootstrap_digest','')
                (self.settings.data/'bootstrap.txt').unlink(missing_ok=True)
                self.store.authorize(event.uid,self.settings.max_users)
                self.store.audit(event.uid,'bootstrap_admin',event.uid)
                return Result('Amministratore configurato. Usa /admin allow USER_ID per autorizzare altri utenti e /help per i comandi.')
            automatic_key=event.text.strip().split()
            if (not self.store.allowed(event.uid) and len(automatic_key)==1 and
                    automatic_key[0].split('@',1)[0].lower() in ('/web_key','/web_password') and
                    self.store.setting('automatic_web_access')=='1' and
                    not self.store.rows('SELECT user_id FROM access_blocks WHERE user_id=?',(event.uid,))):
                self.private(event,telegram=True)
                self.store.authorize(event.uid,self.settings.max_users)
                self.store.audit(event.uid,'automatic_web_activation',event.uid)
            if not self.store.allowed(event.uid):
                return Result(f'Il tuo ID Telegram è {event.uid}. Chiedi all’amministratore di autorizzarlo.') if event.kind=='private' else Result()
            self.last_interaction=time.time()
            core=getattr(self,'core',None)
            if core and core.task and not core.task.done() and core.mode in ('reflection','consolidation','study','repository','tool'):
                core.task.cancel()
                await asyncio.gather(core.task,return_exceptions=True)
            if self.maintenance_task and not self.maintenance_task.done():
                self.maintenance_task.cancel()  # A person has priority over background inference.
                await asyncio.gather(self.maintenance_task,return_exceptions=True)
            if event.kind!='private':
                self.store.execute('INSERT OR IGNORE INTO groups(id) VALUES(?)',(event.chat_id,))
                enabled = self.store.rows('SELECT enabled FROM groups WHERE id=?',(event.chat_id,))[0]['enabled']
                if not enabled and not event.text.startswith('/group'):
                    return Result('Il gruppo deve essere abilitato da un amministratore con /group on.') if event.mention_bot else Result()
            if event.text.startswith('/'):
                return await self.command(event)
            if self.store.setting('bot_paused')=='1':
                return Result('Alba è in pausa. L’amministratore può riattivarla dal sito.') if event.kind=='private' else Result()
            if len(event.text)>3500:
                return Result('Il messaggio è molto lungo: dividilo in parti di massimo 3.500 caratteri per permettermi di leggerlo tutto.')
            respond = self.should_reply(event)
            if respond:
                now = time.time()
                timestamps = [t for t in self.rates.get(event.uid,[]) if now-t<60]
                if len(timestamps)>=8:
                    return Result('Hai inviato molte richieste. Aspetta un minuto e riprova.')
                self.rates[event.uid]=timestamps+[now]
            mid = self.store.add_message(event.scope,event.uid,'user',event.text,
                                        event.chat_id if event.transport=='telegram' else None,
                                        event.message_id,event.reply_id,event.mentions,event.thread_id)
            if not mid:
                return Result()  # Idempotency: duplicated Telegram delivery creates no duplicate response.
            if respond:
                active={owner for (_,owner),entry in self.active_responses.items() if not entry['task'].done()}
                admission=self.capacity.enter(event.uid,active=active)
                if not admission['admitted'] and not CRISIS.search(event.text):
                    evaluate_memories(self.store,event.scope,mid)
                    return Result('I cinque posti in chat sono occupati. Aspetta il tuo turno e riprova tra poco; il tuo messaggio è salvato. Posizione in attesa: '+str(admission['position'])+'.')
                if event.kind=='private' and CRISIS.search(event.text):
                    self.store.execute('DELETE FROM user_activity WHERE user_id=?',(event.uid,))
                notice=touch_activity(self.store,event.uid) if event.kind=='private' and not CRISIS.search(event.text) else None
                key=(event.scope.key,event.uid)
                entry={'task':asyncio.create_task(self.engine.respond(event.scope,event.uid,event.text,mid,event.thread_id)),
                       'stopped':False}
                self.active_responses[key]=entry
                try:
                    return Result(await entry['task'],break_notice=notice)
                except asyncio.CancelledError:
                    evaluate_memories(self.store,event.scope,mid)
                    self.store.add_message(event.scope,None,'assistant','Risposta interrotta.',thread_id=event.thread_id)
                    if entry['stopped']:
                        return Result('Risposta interrotta.',cancelled=True)
                    raise
                finally:
                    if self.active_responses.get(key) is entry:
                        self.active_responses.pop(key,None)
            evaluate_memories(self.store,event.scope,mid)
            return Result()
        except (PermissionError,ValueError) as error:
            self.store.audit(event.uid,'request_denied',event.uid,'denied')
            return Result(str(error))

    async def command(self,e):
        parts = e.text.strip().split()
        command = parts[0].split('@',1)[0].lower()
        args = parts[1:]
        if command=='/notte':
            self.private(e,telegram=True)
            if not self.is_admin(e.uid): raise PermissionError('Notte è riservata all’amministratore.')
            core=getattr(self,'core',None)
            if not core: raise ValueError('ALBA-CORE non avviato.')
            if args==['off']:
                core.config['telegram_enabled']=False
                core.save()
                return Result('Messaggi autonomi Notte su Telegram disattivati.')
            if args: raise ValueError('Usa /notte oppure /notte off.')
            core.config['telegram_matt_id']=e.uid
            core.config['telegram_enabled']=True
            core.save()
            self.store.audit(e.uid,'core_telegram_pair',e.uid)
            return Result('Matt associato a questa chat. Notte può scriverti autonomamente, senza limite giornaliero. /notte off per fermarli. Pannello: '+self.settings.public_url+'/notte')
        if command in ('/start','/help'):
            return Result(HELP)
        if command in ('/privacy','/cookies','/policy'):
            return Result('Informazioni su dati, memoria, accesso dell’amministratore e cookie tecnici: '
                +(self.settings.public_url or '')+('/cookies' if command=='/cookies' else '/privacy' if command=='/privacy' else '/policy')+
                '\nPer cancellare i tuoi dati: /forget all confermo. Per esportarli: /export_key e /export CHIAVE.')
        if command=='/profile':
            self.private(e)
            if args and args[0]=='tone':
                if len(args)!=3:
                    raise ValueError('Usa /profile tone empathy 0.8')
                self.store.set_tone(e.uid,args[1],float(args[2]))
            rows = self.store.profile(e.uid)
            text = 'Dichiarazioni personali:\n'+('\n'.join('• '+m['content'] for m in rows) or 'Nessuna informazione dichiarata salvata.')
            uncertain=[m for m in self.store.memories(e.scope,100) if m['evidence']!='fact']
            if uncertain:
                text+='\n\nInformazioni incerte e interpretazioni, non fatti confermati:\n'+'\n'.join(
                    '• ['+('INFERENZA' if m['evidence']=='inference' else 'INCERTO')+'] '+m['content'] for m in uncertain)
            return Result(text+'\n\nTono: '+json.dumps(self.store.tone(e.uid)))
        if command=='/memory':
            if args and args[0]=='add':
                if len(args)<3:
                    raise ValueError('Usa /memory add personal|preference|goal|relationship|event|temporary testo')
                if e.kind!='private':
                    raise PermissionError('Salva memorie manuali dalla chat privata.')
                content = ' '.join(args[2:])
                mid = self.store.add_message(e.scope,e.uid,'user',content)
                mem = self.store.add_memory(e.scope,content,args[1],[mid],
                                           expires=time.time()+7*86400 if args[1]=='temporary' else None)
                return Result(f'Memoria {mem} salvata come dichiarazione esplicita.')
            if args and args[0]=='exclude':
                self.private(e)
                if len(args)!=2:
                    raise ValueError('Usa /memory exclude ID')
                c=self.store.execute('UPDATE memories SET exportable=0 WHERE id=? AND scope=?',(int(args[1]),e.scope.key))
                return Result('Memoria esclusa dall’esportazione.' if c.rowcount else 'Memoria non trovata.')
            rows = self.store.memories(e.scope)
            return Result('\n'.join(f'{m["id"]} [{m["category"]}/{m["evidence"]}/{m["status"]}] {m["content"]}' for m in rows) or 'Nessuna memoria salvata in questa chat.')
        if command=='/timeline':
            rows = self.store.memories(e.scope,100,historical=True)
            rows.sort(key=lambda r:r['timestamp'])
            return Result('\n'.join(f'{time.strftime("%Y-%m-%d",time.localtime(m["timestamp"]))} [{m["status"]}] {m["content"]}' for m in rows) or 'Timeline vuota.')
        if command=='/search':
            if not args:
                raise ValueError('Usa /search testo')
            rows = retrieve(self.store,e.scope,' '.join(args),15)
            lines=[f'Memoria {m["id"]} [{m["evidence"]}] {m["content"]}' for m in rows]
            lines.extend(f'Messaggio {r["id"]}: «{r["content"][:350]}»' for r in relevant_messages(self.store,e.scope,' '.join(args),5))
            return Result('\n'.join(lines) or 'Non trovo questa informazione nella mia memoria.')
        if command=='/stats':
            return Result(self.stats(e.scope))
        if command=='/web_password':
            self.private(e,telegram=True)
            if args==['revoke']:
                self.keys.revoke_web_password(e.uid,e.uid)
                return Result('Password del sito e sessioni web revocate. Puoi ancora usare /web_key.')
            if args:
                raise ValueError('Usa /web_password oppure /web_password revoke.')
            username,password=self.keys.set_web_password(e.uid,e.uid)
            return Result(f'Credenziali personali del sito:\nNome utente: {username}\nPassword: {password}'
                          '\nLa password precedente è sostituita. Conservala nel tuo gestore di password. '
                          'Puoi revocarla con /web_password revoke.')
        if command in ('/export_key','/web_key'):
            self.private(e,telegram=True)
            if args==['revoke']:
                self.keys.revoke(e.uid,e.uid)
                return Result('Chiavi e sessioni web revocate.')
            if args and args!=['admin']:
                raise ValueError('Usa /export_key, /export_key admin oppure /export_key revoke.')
            purpose = 'web' if command=='/web_key' else ('delegate' if args==['admin'] else 'export')
            token = self.keys.issue(e.uid,e.uid,purpose,self.settings.key_ttl)
            text = f'Chiave {purpose}, monouso, valida 15 minuti:\n{token}'
            if purpose=='web':
                link=self.settings.public_url+'/#web_key='+token if self.settings.public_url else None
                text += '\nTocca «Entra nel sito»: l’accesso è automatico, senza copiare la chiave. Il link è personale: non condividerlo.'
                return Result(text,login_url=link)
            elif purpose=='delegate':
                text += '\nHai autorizzato una sola esportazione dei tuoi dati privati. Consegna questa chiave esclusivamente all’amministratore.'
            else:
                text += '\nUsa /export CHIAVE, /export_personality CHIAVE oppure /export_prompt CHIAVE.'
            return Result(text)
        if command in ('/export','/export_personality','/export_prompt'):
            self.private(e)
            if len(args)!=1:
                raise ValueError('Richiedi prima /export_key in privato e poi usa '+command+' CHIAVE.')
            kind = {'/export':'info','/export_personality':'personality','/export_prompt':'prompt'}[command]
            filename,document = export_document(self.store,self.keys,e.uid,e.uid,args[0],kind)
            return Result('File personale generato.',filename,document)
        if command=='/memory_key':
            self.private(e)
            if args==['revoke']:
                self.store.execute("UPDATE export_keys SET revoked=1 WHERE user_id=? AND purpose='memory_read'",(e.uid,))
                self.store.execute('DELETE FROM memory_access_grants WHERE user_id=?',(e.uid,))
                self.store.audit(e.uid,'memory_access_revoke',e.uid)
                return Result('Codici e permessi temporanei di lettura delle tue memorie revocati.')
            if args: raise ValueError('Usa /memory_key oppure /memory_key revoke.')
            token=self.keys.issue(e.uid,e.uid,'memory_read',900)
            return Result('Codice temporaneo per l’amministratore, monouso e valido 15 minuti:\n'+token+'\nConsegnalo solo se vuoi autorizzare la lettura delle tue memorie e dei riassunti privati. Dopo l’utilizzo permette 15 minuti di consultazione, senza esportazione. Per revocare: /memory_key revoke.')
        if command=='/feedback':
            self.private(e)
            if len(args)!=1: raise ValueError('Usa /feedback utile|ripetitiva|fuori_tema|piu_concreta|troppo_lunga.')
            record_feedback(self.store,e.uid,args[0])
            return Result('Feedback salvato per il tuo stile di risposta. Non cambia i fatti in memoria e non addestra i pesi del modello.')
        if command=='/forget':
            self.private(e,telegram=True)
            if args==['all','confermo']:
                self.store.forget_user(e.uid)
            elif len(args)==1 and args[0].isdigit():
                self.store.forget_memory(e.scope,int(args[0]))
            else:
                raise ValueError('Usa /forget ID oppure /forget all confermo. Verranno eliminati anche i backup precedenti di questo sistema.')
            self.backups.purge_after_erasure()
            self.store.audit(e.uid,'forget',e.uid)
            return Result('Dati richiesti cancellati dal sistema e dai suoi backup precedenti. Le copie già scaricate e i messaggi su Telegram vanno eliminati separatamente.')
        if command=='/backup':
            self.private(e)
            if not self.is_admin(e.uid):
                raise PermissionError('Solo l’amministratore può creare un backup completo. Per i tuoi dati usa /export.')
            path=self.backups.create('manual')
            self.store.audit(e.uid,'backup')
            return Result('Backup cifrato creato sul server: '+path.name)
        if command=='/group':
            if e.kind=='private' or not self.is_admin(e.uid):
                raise PermissionError('Comando riservato all’amministratore nella chat del gruppo.')
            if not self.group_admin_check or not await self.group_admin_check(e.chat_id,e.uid):
                raise PermissionError('Devi essere anche amministratore Telegram di questo gruppo.')
            if args in (['on'],['off']):
                self.store.execute('UPDATE groups SET enabled=? WHERE id=?',(int(args==['on']),e.chat_id))
            elif args in (['auto','on'],['auto','off']):
                self.store.execute('UPDATE groups SET auto_mode=? WHERE id=?',(int(args==['auto','on']),e.chat_id))
            else:
                raise ValueError('Usa /group on|off oppure /group auto on|off.')
            self.store.audit(e.uid,'group_config',e.chat_id)
            return Result('Configurazione del gruppo aggiornata.')
        if command=='/admin':
            self.private(e,telegram=True)
            if not self.is_admin(e.uid):
                raise PermissionError('Permessi amministratore richiesti.')
            return self.admin(e,args)
        return Result('Comando non riconosciuto. Usa /help.')

    def admin(self,e,args):
        if not args:
            return Result('/admin users|allow USER_ID|deny USER_ID|export USER_ID CHIAVE|generate_test_key USER_ID|revoke_key USER_ID|logs|stats|pause|resume')
        action=args[0]
        target=int(args[1]) if len(args)>1 and args[1].lstrip('-').isdigit() else None
        self.store.audit(e.uid,'admin_'+action,target)
        if action in ('pause','resume'):
            self.store.set_setting('bot_paused','1' if action=='pause' else '0')
            return Result('Bot in pausa; il pannello e i comandi rimangono disponibili.' if action=='pause' else 'Bot riattivato.')
        if action=='users':
            return Result('\n'.join(f'{r["id"]}: {r["name"]} — autorizzato={r["authorized"]}' for r in self.store.rows('SELECT * FROM users LIMIT 100')) or 'Nessun utente.')
        if action=='allow' and target:
            self.store.authorize(target,self.settings.max_users)
            self.store.execute('DELETE FROM access_blocks WHERE user_id=?',(target,))
            return Result('Utente autorizzato.')
        if action=='deny' and target:
            if self.is_admin(target):
                raise ValueError('Non puoi disabilitare l’amministratore con questo comando.')
            self.store.execute('UPDATE users SET authorized=0 WHERE id=?',(target,))
            self.store.execute('INSERT OR REPLACE INTO access_blocks VALUES(?,?)',(target,time.time()))
            self.keys.revoke(e.uid,target)
            self.capacity.leave(target)
            for (_,owner),entry in self.active_responses.items():
                if owner==target:
                    entry['stopped']=True; entry['task'].cancel()
            return Result('Accesso dell’utente disabilitato.')
        if action=='generate_test_key' and target:
            return Result('Chiave di test monouso: '+self.keys.issue(e.uid,target,'test')+'\nConsente solo un export sintetico, senza dati personali reali.')
        if action=='revoke_key' and target:
            self.keys.revoke(e.uid,target)
            return Result('Chiavi e sessioni revocate.')
        if action=='export' and target and len(args)==3:
            filename,document=export_document(self.store,self.keys,e.uid,target,args[2],admin=True)
            return Result('Esportazione autorizzata.',filename,document)
        if action=='logs':
            return Result(json.dumps(self.store.rows('SELECT * FROM audit_logs ORDER BY id DESC LIMIT 20'),ensure_ascii=False,indent=2))
        if action=='stats':
            return Result(self.stats(None))
        raise ValueError('Argomenti non validi. Usa /admin per l’elenco dei comandi.')

    def stats(self,scope):
        disk=shutil.disk_usage(self.settings.root)
        ram='n/d'
        if Path('/proc/meminfo').exists():
            info={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()}
            ram=f'{(info["MemTotal"]-info["MemAvailable"])/2**30:.2f}/{info["MemTotal"]/2**30:.2f} GiB'
        clause,args=(' WHERE scope=?',(scope.key,)) if scope else ('',())
        messages=self.store.db.execute('SELECT count(*) FROM messages'+clause,args).fetchone()[0]
        memories=self.store.db.execute('SELECT count(*) FROM memories'+clause,args).fetchone()[0]
        timing=self.store.db.execute('SELECT avg(seconds) FROM metrics'+clause,args).fetchone()[0] or 0
        size=sum(p.stat().st_size for p in self.settings.data.glob('*.sqlite3*'))
        return (f'RAM: {ram}\nCPU: carico 1m {os.getloadavg()[0]:.2f}, {os.cpu_count()} core'
                f'\nDISK: {disk.used/2**30:.1f}/{disk.total/2**30:.1f} GiB'
                f'\nDATABASE SIZE: {size/2**20:.2f} MiB\nMODEL: {self.settings.model}'
                f'\nMESSAGES: {messages}\nMEMORIES: {memories}\nRESPONSE TIME: {timing:.1f}s (media)')
