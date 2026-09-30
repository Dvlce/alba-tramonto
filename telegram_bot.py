"""Telegram Bot API client: no dependency on a large bot framework."""
import asyncio
import json
import logging
from dataclasses import asdict
from aiohttp import FormData, ClientError
from service import Incoming

log = logging.getLogger('alba.telegram')


def utf16_entity(text,entity):
    raw=text.encode('utf-16-le')
    return raw[entity['offset']*2:(entity['offset']+entity['length'])*2].decode('utf-16-le')


def normalize(message,bot):
    user=message.get('from',{})
    if not user or user.get('is_bot') or message.get('forward_origin') or not message.get('text'):
        return None
    chat=message['chat']
    text=message['text']
    if text.startswith('/'):
        first=text.split()[0]
        if '@' in first and first.split('@',1)[1].casefold()!=bot['username'].casefold():
            return None
    mentions=[]
    mention=False
    for entity in message.get('entities',[]):
        value=utf16_entity(text,entity)
        if entity['type']=='mention':
            mentions.append(value)
            mention |= value.casefold()=='@'+bot['username'].casefold()
        if entity['type']=='text_mention':
            mentions.append(str(entity['user']['id']))
            mention |= entity['user']['id']==bot['id']
    reply=message.get('reply_to_message',{})
    return Incoming(uid=user['id'],name=user.get('first_name') or user.get('username') or str(user['id']),
                    chat_id=chat['id'],kind=chat['type'],text=text,message_id=message['message_id'],
                    reply_id=reply.get('message_id'),reply_to_bot=reply.get('from',{}).get('id')==bot['id'],
                    mention_bot=mention,mentions=tuple(mentions),thread_id=message.get('message_thread_id',0))


class Telegram:
    def __init__(self,service,session,token):
        self.service,self.session=service,session
        self.base='https://api.telegram.org/bot'+token+'/'
        self.bot=None
        self.queue=asyncio.Queue(maxsize=30)
        self.locks={}
        service.group_admin_check=self.group_admin
        service.telegram_avatar=self.profile_photo
        service.request_memory_access=self.memory_request
        service.store.db.executescript('''CREATE TABLE IF NOT EXISTS pending_updates(
          update_id INTEGER PRIMARY KEY, payload TEXT NOT NULL);''')

    async def api(self,method,payload=None,form=None):
        for _ in range(3):
            async with self.session.post(self.base+method,json=payload if form is None else None,
                                         data=form,timeout=45) as response:
                data=await response.json()
            if data.get('ok'):
                return data.get('result')
            if data.get('error_code')==429:
                await asyncio.sleep(min(30,data.get('parameters',{}).get('retry_after',2)))
                continue
            # Bot API errors can contain user input. Log only a numeric code.
            raise ValueError('Telegram API status '+str(data.get('error_code','unknown')))
        raise ValueError('Telegram rate limited')

    async def group_admin(self,chat,uid):
        result=await self.api('getChatMember',{'chat_id':chat,'user_id':uid})
        return result['status'] in ('creator','administrator')

    async def memory_request(self,uid):
        await self.api('sendMessage',{'chat_id':uid,'text':'L’amministratore chiede di consultare le tue memorie e i riassunti privati per 15 minuti. Se desideri autorizzarlo, invia /memory_key qui e consegnagli il codice. Puoi rifiutare e continuare a usare Alba. Per revocare un consenso già dato: /memory_key revoke.'})

    async def profile_photo(self,uid):
        data=await self.api('getUserProfilePhotos',{'user_id':uid,'limit':1})
        if not data.get('photos'): return b''
        photo=data['photos'][0][0]
        if photo.get('file_size',0)>1024*1024: return b''
        file=await self.api('getFile',{'file_id':photo['file_id']})
        path=file['file_path']
        if not isinstance(path,str) or '..' in path or not path.startswith('photos/'): return b''
        async with self.session.get(self.base.replace('/bot','/file/bot')+path,timeout=15) as response:
            if response.status!=200: return b''
            chunks=[]; size=0
            async for chunk in response.content.iter_chunked(65536):
                size+=len(chunk)
                if size>1024*1024: return b''
                chunks.append(chunk)
            image=b''.join(chunks)
        return image if len(image)<=1024*1024 and image.startswith(b'\xff\xd8\xff') else b''

    async def deliver(self,event,result):
        common={'chat_id':event.chat_id}
        if event.thread_id:
            common['message_thread_id']=event.thread_id
        if result.document:
            form=FormData()
            form.add_field('chat_id',str(event.chat_id))
            form.add_field('document',result.document,filename=result.filename,content_type='application/octet-stream')
            form.add_field('protect_content','true')
            await self.api('sendDocument',form=form)
        elif result.text:
            text=result.text
            if result.break_notice:
                text+='\n\n☕ '+result.break_notice['message']
            for i in range(0,len(text),3800):
                payload={**common,'text':text[i:i+3800],'link_preview_options':{'is_disabled':True}}
                if result.login_url and i==0:
                    payload['reply_markup']={'inline_keyboard':[[{'text':'Entra nel sito ↗','url':result.login_url}]]}
                if event.message_id:
                    payload['reply_parameters']={'message_id':event.message_id,'allow_sending_without_reply':True}
                if event.text.startswith(('/export_key','/web_key','/web_password','/admin generate_test_key')):
                    payload['protect_content']=True
                await self.api('sendMessage',payload)

    async def process(self,event,update_id=None):
        if event.text.strip().split()[0].split('@',1)[0].lower()=='/stop':
            await self.deliver(event,await self.service.handle(event))
            return
        lock=self.locks.setdefault(event.scope.key,asyncio.Lock())
        async with lock:
            if update_id is not None and not self.service.store.rows('SELECT update_id FROM pending_updates WHERE update_id=?',(update_id,)):
                return
            result=await self.service.handle(event)
            if not result.cancelled:
                await self.deliver(event,result)

    async def worker(self):
        while True:
            update_id,event=await self.queue.get()
            try:
                await self.process(event,update_id)
            except Exception as exc:
                log.error('Elaborazione fallita (%s), update=%s',type(exc).__name__,update_id)
            finally:
                self.service.store.execute('DELETE FROM pending_updates WHERE update_id=?',(update_id,))
                self.queue.task_done()

    async def configure_bot(self):
        updates=[]
        if self.bot.get('first_name')!='Alba':
            updates.append(('setMyName',{'name':'Alba'}))
        if self.service.store.setting('telegram_identity_configured')!='1':
            updates.extend([('setMyDescription',{'description':'Un’assistente locale per riflessione personale, relazioni e problemi quotidiani. Memoria privata e di gruppo separata. /start per cominciare.'}),
                ('setMyShortDescription',{'short_description':'Alba · Uno spazio per parlarne. Assistente locale con memoria, senza diagnosi cliniche.'})])
        configured=True
        for method,payload in updates:
            try: await self.api(method,payload)
            except (ClientError,asyncio.TimeoutError,ValueError) as exc:
                configured=False
                log.warning('Aggiornamento opzionale Telegram rinviato: %s (%s)',method,type(exc).__name__)
        if configured:
            self.service.store.set_setting('telegram_identity_configured',1)
        commands=['start','help','profile','memory','timeline','search','stats','export','export_key',
                  'export_personality','export_prompt','forget','backup','web_key','web_password','stop','group','admin','privacy','cookies','policy']
        if self.service.store.setting('telegram_commands_version')!='wellbeing-20260930':
            try:
                await self.api('setMyCommands',{'commands':[{'command':c,'description':c.replace('_',' ')} for c in commands]})
                self.service.store.set_setting('telegram_commands_version','wellbeing-20260930')
            except (ClientError,asyncio.TimeoutError,ValueError) as exc:
                log.warning('Elenco comandi Telegram rinviato (%s)',type(exc).__name__)
        try: await self.api('deleteWebhook',{'drop_pending_updates':False})
        except (ClientError,asyncio.TimeoutError,ValueError) as exc:
            log.warning('Configurazione webhook Telegram rinviata (%s)',type(exc).__name__)

    async def run(self):
        while self.bot is None:
            try: self.bot=await self.api('getMe')
            except (ClientError,asyncio.TimeoutError,ValueError) as exc:
                log.warning('Connessione Telegram da riprovare (%s)',type(exc).__name__)
                await asyncio.sleep(5)
        self.service.store.set_setting('telegram_username',self.bot['username'])
        await self.configure_bot()
        log.info('Telegram connesso: @%s',self.bot['username'])
        workers=[asyncio.create_task(self.worker()) for _ in range(3)]
        try:
            for row in self.service.store.rows('SELECT * FROM pending_updates ORDER BY update_id'):
                await self.queue.put((row['update_id'],Incoming(**json.loads(row['payload']))))
            offset=int(self.service.store.setting('telegram_offset','0'))
            while True:
                try:
                    updates=await self.api('getUpdates',{'offset':offset,'timeout':30,'limit':20,
                                           'allowed_updates':['message']})
                    for update in updates:
                        event=normalize(update.get('message',{}),self.bot)
                        if event:
                            if event.text.startswith('/'):
                                # Do not persist commands: they may contain export/recovery secrets.
                                await self.process(event)
                            else:
                                self.service.store.execute('INSERT OR IGNORE INTO pending_updates VALUES(?,?)',
                                                          (update['update_id'],json.dumps(asdict(event),ensure_ascii=False)))
                                await self.queue.put((update['update_id'],event))
                        offset=update['update_id']+1
                        self.service.store.set_setting('telegram_offset',offset)
                except (ClientError,asyncio.TimeoutError,ValueError) as exc:
                    log.warning('Connessione Telegram da riprovare (%s)',type(exc).__name__)
                    await asyncio.sleep(5)
        finally:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers,return_exceptions=True)
