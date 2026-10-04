import asyncio
import base64
import json
import logging
import os
import secrets
import signal
import time
import shutil
import re
from aiohttp import ClientSession, web
from config import Settings
from store import Store, Scope
from security import Keys,secret_file
from backups import Backups
from engine import Engine,RESPONSE_PROGRESS
from service import Service,Incoming
from telegram_bot import Telegram
from usage import monthly_usage,ROME
from datetime import datetime
from maintenance_tasks import periodic_memory,memory_cycle
from runtime_features import quota,break_status
from tramonto import setup_tramonto
from core.web import setup_core
from http_guard import HTTPGuard
from identity import setup_identity
from learning import record_feedback

log=logging.getLogger('alba')


def web_app(service):
    guard=HTTPGuard(service.keys,service.settings.public_url)
    login_slots=asyncio.Semaphore(2)
    jobs={}
    active_users=set()
    avatar_locks={}
    def discard_completed_job(key):
        task=jobs.pop(key)['task']
        if not task.cancelled(): task.exception()  # Consume errors even if the browser never polled.
    @web.middleware
    async def security(request,handler):
        admitted=guard.enter()
        try:
            if not admitted: raise web.HTTPTooManyRequests(headers={'Retry-After':'10'})
            if request.path.startswith('/api/') and request.path!='/api/login':
                try: request['identity']=service.keys.identify(request.cookies.get('session',''))
                except PermissionError:
                    request['session_expired']=True; raise
                if request.path.startswith('/api/tramonto/') and not service.is_admin(request['identity']['user_id']): raise PermissionError()
                if not request.path.startswith('/api/tramonto/') and request.content_length and request.content_length>20000: raise ValueError()
                if request.method!='GET':
                    if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),request['identity']['csrf']):
                        raise PermissionError('Richiesta non autorizzata.')
            await guard.check(request)
            response=await handler(request)
        except web.HTTPException as exc: response=exc
        except (PermissionError,ValueError,KeyError,json.JSONDecodeError):
            response=web.json_response({'error':'Richiesta non valida o accesso scaduto.',
                                       'code':'auth_expired' if request.get('session_expired') else 'request_denied'},status=403)
        finally:
            if admitted: guard.leave()
        if response.status<400 and request.get('identity') and service.keys.renew_session(request['identity']['digest']):
            session_cookie(response,request.cookies.get('session',''),True)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                                 'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
                                 'Strict-Transport-Security':'max-age=31536000',
                                 'Permissions-Policy':'camera=(), microphone=(), geolocation=(), payment=()',
                                 'Cross-Origin-Resource-Policy':'same-origin','Cross-Origin-Opener-Policy':'same-origin','Server':'Alba',
                                 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"})
        if request.path in ('/tramonto','/notte'): response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' blob: data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        return response
    app=web.Application(middlewares=[security],client_max_size=10*1024*1024)

    def session_cookie(response,cookie,remember):
        response.set_cookie('session',cookie,httponly=True,secure=True,samesite='Strict',
                            max_age=service.keys.REMEMBER_TTL if remember else service.keys.SESSION_TTL,path='/')

    def browser_label(request):
        ua=request.headers.get('User-Agent','')[:500]
        browser=next((name for marker,name in (('Edg/','Edge'),('Firefox/','Firefox'),('Chrome/','Chrome'),('Safari/','Safari')) if marker in ua),'Browser')
        platform=next((name for marker,name in (('Android','Android'),('iPhone','iPhone'),('iPad','iPad'),('Windows','Windows'),('Macintosh','Mac'),('Linux','Linux')) if marker in ua),'Dispositivo')
        return browser+' · '+platform

    async def index(request):
        return web.FileResponse(service.settings.root/'web.html')

    async def asset(request):
        names={'web.js','web.css','portal-motion.js'}
        name=request.match_info['name']
        if name not in names:
            raise web.HTTPNotFound()
        return web.FileResponse(service.settings.root/name)

    async def health(request):
        return web.json_response({'status':'ok'})

    async def status(request):
        uid=request['identity']['user_id']
        return web.json_response({'performance':service.performance.snapshot,'maintenance':service.maintenance,
            'quota':quota(service.store,uid),'break_notice':break_status(service.store,uid),
            'capacity':service.capacity.status(uid,active={owner for (_,owner) in service.active_responses})})

    async def presence(request):
        uid=request['identity']['user_id']; body=await request.json()
        if body.get('leave') is True:
            if not any(owner==uid for (_,owner) in service.active_responses): service.capacity.leave(uid)
        else:
            service.capacity.enter(uid,active={owner for (_,owner) in service.active_responses})
        return web.json_response(service.capacity.status(uid,active={owner for (_,owner) in service.active_responses}))

    async def policy(request):
        return web.json_response({'owner':service.store.setting('privacy_owner','Gestore Alba'),
            'contact':service.store.setting('privacy_contact','Configura il contatto nel pannello amministratore'),
            'session_hours':service.settings.session_ttl//3600,
            'telegram_url':'https://t.me/'+service.store.setting('telegram_username') if re.fullmatch(r'[A-Za-z0-9_]{5,32}',service.store.setting('telegram_username')) else '',
            'remember_days':service.keys.REMEMBER_TTL//86400,
            'retention':{'daily':service.settings.daily_retention,'weekly':service.settings.weekly_retention,'monthly':service.settings.monthly_retention}})

    async def avatar(request):
        uid=request['identity']['user_id']
        if uid<0: return web.Response(status=204)
        if request.query: raise PermissionError()
        async with avatar_locks.setdefault(uid,asyncio.Lock()):
            rows=service.store.rows('SELECT image,fetched FROM user_avatars WHERE user_id=?',(uid,))
            image=rows[0]['image'] if rows else b''
            if (not rows or time.time()-rows[0]['fetched']>86400) and service.telegram_avatar:
                try:
                    image=await service.telegram_avatar(uid)
                    service.keys.identify(request.cookies.get('session',''))
                    if not service.store.allowed(uid): raise PermissionError()
                    service.store.execute('INSERT OR REPLACE INTO user_avatars VALUES(?,?,?)',(uid,image,time.time()))
                except Exception as exc:
                    log.warning('Foto Telegram non disponibile (%s)',type(exc).__name__)
                    image=b''
        return web.Response(body=image,content_type='image/jpeg') if image else web.Response(status=204)

    async def login(request):
        body=await request.json()
        if not isinstance(body,dict): raise ValueError()
        guard.hit('login-global',60)
        guard.hit('login-account:'+service.keys.digest(str(body.get('username',body.get('token','')))[:100]),10)
        remember=body.get('remember',True)
        if type(remember) is not bool: raise ValueError()
        try:
            if 'username' in body or 'password' in body:
                if login_slots.locked(): return web.json_response({'error':'Accesso occupato, riprova tra pochi secondi.'},status=429)
                async with login_slots:
                    cookie,csrf=await service.keys.password_session(body.get('username',''),body.get('password',''),remember,browser_label(request))
            else:
                token=body.get('token','')
                if not isinstance(token,str) or len(token)>100:
                    raise PermissionError()
                cookie,csrf=service.keys.session(token,remember,browser_label(request))
        except PermissionError:
            message=('Nome utente o password non validi.' if 'username' in body or 'password' in body else
                     'La chiave web è scaduta, già usata o non valida. Richiedi una nuova /web_key al bot. La chiave /bootstrap serve soltanto in Telegram.')
            return web.json_response({'error':message},status=403)
        response=web.json_response({'csrf':csrf})
        previous=request.cookies.get('session','')
        if previous: service.store.execute('DELETE FROM web_sessions WHERE digest=?',(service.keys.digest(previous),))
        session_cookie(response,cookie,remember)
        return response

    async def me(request):
        identity=request['identity']
        return web.json_response({'user_id':identity['user_id'],'csrf':identity['csrf'],
                                 'name':service.store.user_name(identity['user_id']),
                                 'is_admin':service.is_admin(identity['user_id']),'telegram_linked':identity['user_id']>0})

    async def cancel_device_jobs(digests):
        entries=list(jobs.values())+list(getattr(service,'spice_jobs',{}).values())
        tasks=[entry['task'] for entry in entries if entry.get('session_digest',entry.get('digest')) in digests and not entry['task'].done()]
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)

    async def devices(request):
        identity=request['identity']; uid=identity['user_id']
        if request.query: raise PermissionError()
        if request.method=='GET':
            rows=service.store.rows('SELECT device_id,label,remembered,created,last_seen,expires,digest FROM web_sessions WHERE user_id=? AND expires>? ORDER BY last_seen DESC',(uid,time.time()))
            for row in rows: row['current']=row.pop('digest')==identity['digest']
            return web.json_response({'devices':rows,'remember_days':service.keys.REMEMBER_TTL//86400})
        body=await request.json()
        if not isinstance(body,dict): raise ValueError()
        action=body.get('action')
        if any(key in body for key in ('user_id','scope','digest')): raise PermissionError()
        if action=='remember':
            remember=body.get('remember'); label=body.get('label',identity['label'])
            if type(remember) is not bool or not isinstance(label,str) or not 1<=len(label.strip())<=80: raise ValueError()
            if body.get('device_id',identity['device_id'])!=identity['device_id']: raise PermissionError()
            ttl=service.keys.REMEMBER_TTL if remember else service.keys.SESSION_TTL
            service.store.execute('UPDATE web_sessions SET remembered=?,label=?,expires=?,last_seen=? WHERE digest=?',
                                  (int(remember),label.strip(),time.time()+ttl,time.time(),identity['digest']))
            service.store.audit(uid,'web_device_remember' if remember else 'web_device_short',uid)
            response=web.json_response({'ok':True}); session_cookie(response,request.cookies['session'],remember); return response
        if action in ('revoke','revoke_others'):
            if action=='revoke':
                rows=service.store.rows('SELECT digest FROM web_sessions WHERE user_id=? AND device_id=?',(uid,body.get('device_id','')))
                if not rows: raise PermissionError()
            else: rows=service.store.rows('SELECT digest FROM web_sessions WHERE user_id=? AND digest<>?',(uid,identity['digest']))
            digests={row['digest'] for row in rows}
            for digest in digests: service.store.execute('DELETE FROM web_sessions WHERE digest=?',(digest,))
            await cancel_device_jobs(digests); service.store.audit(uid,'web_device_'+action,uid)
            response=web.json_response({'ok':True,'current_revoked':identity['digest'] in digests})
            if identity['digest'] in digests: response.del_cookie('session',path='/')
            return response
        raise ValueError()

    async def usage(request):
        uid=request['identity']['user_id']
        if any(key in request.query for key in ('user_id','group_id','chat_id')):
            raise PermissionError()
        mode=request.query.get('scope','self')
        if mode not in ('self','bot') or (mode=='bot' and not service.is_admin(uid)):
            raise PermissionError()
        month=request.query.get('month',datetime.now(ROME).strftime('%Y-%m'))
        return web.json_response(monthly_usage(service.store,uid,month,all_users=mode=='bot'))

    async def history(request):
        uid=request['identity']['user_id']
        if set(request.query)-{'after','before'}: raise PermissionError()
        after=request.query.get('after')
        before=request.query.get('before')
        if (after is not None and before is not None) or any(len(request.query.getall(k))!=1 for k in request.query):
            raise ValueError()
        for cursor in (after,before):
            if cursor is not None and (not cursor.isdigit() or len(cursor)>19 or int(cursor)>=2**63): raise ValueError()
        if after is not None:
            rows=service.store.rows('SELECT * FROM messages WHERE scope=? AND id>? ORDER BY id LIMIT 100',(Scope('user',uid).key,int(after)))
            return web.json_response({'messages':rows})
        if before is not None and int(before)==0: raise ValueError()
        condition,args=(' AND id<?',(int(before),)) if before is not None else ('',())
        rows=service.store.rows('SELECT * FROM messages WHERE scope=?'+condition+' ORDER BY id DESC LIMIT 51',(Scope('user',uid).key,*args))
        has_older=len(rows)>50
        rows=list(reversed(rows[:50]))
        return web.json_response({'messages':rows,'has_older':has_older,'next_before':rows[0]['id'] if rows else None})

    async def chat(request):
        uid=request['identity']['user_id']
        body=await request.json()
        text=body.get('message','')
        if not isinstance(text,str) or not text.strip() or len(text)>3500:
            raise ValueError()
        # Explicit rejection rather than accepting a client's requested owner or group.
        if any(k in body for k in ('user_id','group_id','chat_id','scope')):
            raise PermissionError()
        if uid in active_users:
            return web.json_response({'error':'Una risposta è già in preparazione.'},status=429)
        for old in list(jobs):
            if time.time()-jobs[old]['created']>1800 and jobs[old]['task'].done():
                discard_completed_job(old)
        if len(jobs)>=100:
            completed=[key for key,entry in jobs.items() if entry['task'].done()]
            if completed: discard_completed_job(min(completed,key=lambda key:jobs[key]['created']))
        if len(jobs)>=100:
            return web.json_response({'error':'Riprova fra qualche minuto.'},status=429)
        job_id=secrets.token_urlsafe(24)
        active_users.add(uid)
        progress={'phase':'queued'}
        async def run():
            token=RESPONSE_PROGRESS.set(progress)
            try:
                result=await service.handle(Incoming(uid,service.store.user_name(uid),uid,'private',text,transport='web'))
                return {'reply':result.text,'filename':result.filename,
                        'break_notice':result.break_notice,
                        'cancelled':result.cancelled,
                        'document':base64.b64encode(result.document).decode() if result.document else None}
            finally:
                RESPONSE_PROGRESS.reset(token)
                active_users.discard(uid)
        jobs[job_id]={'user_id':uid,'session_digest':request['identity']['digest'],'created':time.time(),'started':time.monotonic(),'progress':progress,'task':asyncio.create_task(run())}
        return web.json_response({'job_id':job_id},status=202)

    async def job(request):
        entry=jobs.get(request.match_info['job_id'])
        if not entry or entry['user_id']!=request['identity']['user_id']:
            raise PermissionError()
        if not entry['task'].done():
            return web.json_response({'pending':True,'phase':entry['progress']['phase'],
                                      'elapsed_seconds':int(max(0,time.monotonic()-entry['started']))})
        if entry['task'].cancelled():
            return web.json_response({'cancelled':True,'reply':'Risposta interrotta.'})
        if entry['task'].exception():
            return web.json_response({'reply':'La richiesta non è riuscita. Riprova tra poco.'})
        return web.json_response(entry['task'].result())

    async def cancel(request):
        entry=jobs.get(request.match_info['job_id'])
        uid=request['identity']['user_id']
        if not entry or entry['user_id']!=uid:
            raise PermissionError()
        task=entry['task']
        if task.done():
            return web.json_response({'cancelled':task.cancelled()})
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        service.store.audit(uid,'response_cancel',uid)
        return web.json_response({'cancelled':True})

    def admin_identity(request):
        uid=request['identity']['user_id']
        if not service.is_admin(uid):
            service.store.audit(uid,'web_admin_denied',uid,'denied')
            raise PermissionError()
        return uid

    def telegram_id(value,group=False):
        if type(value) not in (str,int):
            raise ValueError('Inserisci un ID Telegram numerico.')
        value=str(value).strip()
        if not value.lstrip('-').isdigit():
            raise ValueError('Inserisci un ID Telegram numerico.')
        uid=int(value)
        external=not group and -2**63<uid<0 and bool(service.store.rows('SELECT 1 FROM auth_accounts WHERE user_id=?',(uid,)))
        if not external and not (-2**63<uid<0 if group else 0<uid<2**63):
            raise ValueError('ID Telegram non valido.')
        return uid

    async def admin_status(request):
        admin_identity(request)
        users=service.store.rows('SELECT id,name,authorized FROM users ORDER BY authorized DESC,created DESC LIMIT 100')
        for row in users:
            row['is_admin']=service.is_admin(row['id'])
            row['quota']=quota(service.store,row['id'])
        disk=shutil.disk_usage(service.settings.root)
        return web.json_response({'users':users,'max_users':service.settings.max_users,'max_online':service.settings.max_online,
            'authorized_count':service.store.rows('SELECT count(*) AS n FROM users WHERE authorized=1')[0]['n'],
            'groups':service.store.rows('SELECT g.*,c.title FROM groups g LEFT JOIN telegram_chats c ON c.id=g.id ORDER BY g.id LIMIT 100'),
            'logs':service.store.rows('SELECT * FROM audit_logs ORDER BY id DESC LIMIT 40'),
            'stats':service.stats(None),'paused':service.store.setting('bot_paused')=='1',
            'automatic_access':service.store.setting('automatic_web_access')=='1',
            'privacy':{'owner':service.store.setting('privacy_owner','Gestore Alba'),'contact':service.store.setting('privacy_contact','Configura il contatto nel pannello amministratore')},
            'break_minutes':int(service.store.setting('break_minutes','20')),
            'disk':{'total':disk.total,'used':disk.used,'free':disk.free},
            'memory_schedule':{'last_flush':service.store.setting('memory_flush_last'),
                               'last_night':service.store.setting('memory_night_last'),
                               'night_time':service.store.setting('memory_night_time','23:00')}})

    async def admin_memories(request):
        uid=admin_identity(request); expires=None
        if 'user_id' in request.query and 'group_id' not in request.query:
            owner=telegram_id(request.query['user_id']); scope=Scope('user',owner)
            if not service.store.rows('SELECT id FROM users WHERE id=?',(owner,)):
                raise ValueError()
            if owner!=uid:
                grants=service.store.rows('SELECT expires FROM memory_access_grants WHERE user_id=? AND admin_id=? AND expires>?',(owner,uid,time.time()))
                if not grants:
                    service.store.audit(uid,'web_memory_inspect',owner,'denied');return web.json_response({'error':'Serve il codice temporaneo dell’utente: /memory_key nella sua chat privata.','code':'memory_consent_required'},status=403)
                expires=grants[0]['expires']
            title=service.store.user_name(owner)
        elif 'group_id' in request.query and 'user_id' not in request.query:
            owner=telegram_id(request.query['group_id'],group=True); scope=Scope('group',owner)
            if not service.group_admin_check or not await service.group_admin_check(owner,uid):
                raise PermissionError()
            title='Gruppo '+str(owner)
        else:
            raise ValueError()
        service.store.audit(uid,'web_memory_inspect',owner)
        return web.json_response({'owner':title,'scope':scope.key,'expires':expires,
            'memories':service.store.memories(scope,100,historical=True),
            'summaries':service.store.rows("SELECT content,timestamp,summary_kind FROM summaries WHERE scope=? AND summary_kind IN ('conversation','consolidated') ORDER BY id DESC LIMIT 6",(scope.key,))})

    async def memory_access(request):
        uid=admin_identity(request); value=await request.json()
        if not isinstance(value,dict) or set(value)-{'user_id','token','action'}: raise ValueError()
        owner=telegram_id(value.get('user_id')); action=value.get('action','grant')
        if not service.store.allowed(owner): raise PermissionError()
        if action=='request':
            guard.hit('memory-request:'+str(uid)+':'+str(owner),1,3600)
            if owner<=0 or not service.request_memory_access: return web.json_response({'message':'Chiedi all’utente di inviare /memory_key nella sua chat privata con Alba, anche sul sito.'})
            await service.request_memory_access(owner);service.store.audit(uid,'memory_access_request',owner)
            return web.json_response({'message':'Richiesta inviata. L’utente decide se generare e consegnarti il codice.'})
        if action=='revoke':
            service.store.execute('DELETE FROM memory_access_grants WHERE user_id=? AND admin_id=?',(owner,uid));service.store.audit(uid,'admin_memory_access_revoke',owner)
            return web.json_response({'message':'Accesso temporaneo revocato.'})
        token=value.get('token')
        if action!='grant' or not isinstance(token,str) or not 1<=len(token)<=100: raise ValueError()
        service.keys.consume(uid,owner,token,('memory_read',));expires=time.time()+900
        service.store.execute('INSERT OR REPLACE INTO memory_access_grants VALUES(?,?,?,?)',(owner,uid,expires,time.time()));service.store.audit(uid,'memory_access_granted',owner)
        return web.json_response({'message':'Consultazione autorizzata per 15 minuti. Nessun permesso di esportazione.','expires':expires})

    async def admin_users(request):
        uid=admin_identity(request); body=await request.json()
        try:
            target=telegram_id(body.get('user_id'))
            action=body.get('action')
            if action=='token_limit':
                limit=body.get('token_limit')
                if type(limit)!=int or not 0<=limit<=10**12 or not service.store.rows('SELECT id FROM users WHERE id=?',(target,)):
                    raise ValueError('Inserisci un limite intero tra 0 e 1.000 miliardi; zero significa senza limite.')
                service.store.execute('INSERT OR REPLACE INTO user_limits VALUES(?,?)',(target,limit))
                service.store.audit(uid,'web_token_limit',target)
                return web.json_response({'message':'Limite mensile aggiornato.'})
            if action not in ('allow','deny','revoke_key'):
                raise ValueError('Operazione non valida.')
            result=service.admin(Incoming(uid,service.store.user_name(uid),uid,'private','',transport='web'),[action,str(target)])
            return web.json_response({'message':result.text})
        except (ValueError,PermissionError) as exc:
            return web.json_response({'error':str(exc)},status=400)

    async def admin_groups(request):
        uid=admin_identity(request); body=await request.json()
        try:
            gid=telegram_id(body.get('group_id'),group=True)
            if not service.store.rows('SELECT id FROM groups WHERE id=?',(gid,)):
                raise ValueError('Gruppo non ancora conosciuto dal bot.')
            if not service.group_admin_check or not await service.group_admin_check(gid,uid):
                raise PermissionError('Devi essere anche amministratore di questo gruppo Telegram.')
            field=body.get('field'); value=body.get('enabled')
            if field not in ('enabled','auto_mode') or type(value) is not bool:
                raise ValueError('Operazione non valida.')
            service.store.execute('UPDATE groups SET '+field+'=? WHERE id=?',(int(value),gid))
            service.store.audit(uid,'web_group_'+field,gid)
            return web.json_response({'message':'Impostazioni del gruppo aggiornate.'})
        except (ValueError,PermissionError) as exc:
            return web.json_response({'error':str(exc)},status=400)

    async def admin_action(request):
        uid=admin_identity(request); body=await request.json(); action=body.get('action')
        if action=='privacy':
            owner=body.get('owner'); contact=body.get('contact')
            if not isinstance(owner,str) or not isinstance(contact,str) or not 1<=len(owner.strip())<=150 or not 1<=len(contact.strip())<=250:
                raise ValueError()
            service.store.set_setting('privacy_owner',owner.strip()); service.store.set_setting('privacy_contact',contact.strip())
            service.store.audit(uid,'web_privacy_settings')
            return web.json_response({'message':'Recapiti della pagina privacy aggiornati.'})
        if action=='break_interval':
            minutes=body.get('minutes')
            if type(minutes)!=int or not 5<=minutes<=120: raise ValueError()
            service.store.set_setting('break_minutes',minutes); service.store.audit(uid,'web_break_interval')
            return web.json_response({'message':'Promemoria di pausa aggiornato.'})
        if action=='automatic_access':
            value=body.get('enabled')
            if type(value) is not bool:
                raise ValueError()
            service.store.set_setting('automatic_web_access','1' if value else '0')
            service.store.audit(uid,'web_automatic_access_'+('on' if value else 'off'))
            return web.json_response({'message':'Accesso automatico attivato.' if value else 'Accesso automatico disattivato.'})
        if action=='memory_schedule':
            value=body.get('night_time','')
            if not isinstance(value,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):
                raise ValueError()
            service.store.set_setting('memory_night_time',value)
            service.store.audit(uid,'web_memory_schedule')
            return web.json_response({'message':'Riordino notturno impostato alle '+value+' (ora italiana).'})
        if action=='memory_flush':
            await memory_cycle(service.store)
            service.store.audit(uid,'web_memory_flush')
            return web.json_response({'message':'Memorie e riassunti aggiornati.'})
        if action=='backup':
            path=service.backups.create('manual')
            service.store.audit(uid,'web_backup')
            return web.json_response({'message':'Backup cifrato creato: '+path.name})
        if action in ('pause','resume'):
            result=service.admin(Incoming(uid,service.store.user_name(uid),uid,'private','',transport='web'),[action])
            return web.json_response({'message':result.text})
        raise ValueError()

    async def cleanup(app):
        tasks=[entry['task'] for entry in jobs.values() if not entry['task'].done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    app.on_cleanup.append(cleanup)

    async def logout(request):
        uid=request['identity']['user_id']
        await cancel_device_jobs({request['identity']['digest']})
        if not any(owner==uid for (_,owner) in service.active_responses): service.capacity.leave(uid)
        service.store.execute('DELETE FROM web_sessions WHERE digest=?',(request['identity']['digest'],))
        response=web.json_response({'ok':True})
        response.del_cookie('session')
        return response

    app.add_routes([web.get('/',index),web.get('/privacy',index),web.get('/cookies',index),web.get('/policy',index),
                    web.get('/policy-info',policy),web.get('/health',health),web.get('/assets/{name}',asset),web.get('/api/status',status),
                    web.post('/api/login',login),web.get('/api/me',me),web.get('/api/history',history),
                    web.get('/api/devices',devices),web.post('/api/devices',devices),
                    web.post('/api/presence',presence),
                    web.get('/api/avatar',avatar),
                    web.get('/api/usage',usage),
                    web.get('/api/admin',admin_status),web.post('/api/admin/memory-access',memory_access),web.get('/api/admin/memories',admin_memories),
                    web.post('/api/admin/users',admin_users),
                    web.post('/api/admin/groups',admin_groups),web.post('/api/admin/action',admin_action),
                    web.post('/api/chat',chat),web.get('/api/jobs/{job_id}',job),
                    web.post('/api/jobs/{job_id}/cancel',cancel),web.post('/api/logout',logout)])
    async def android_download(request):
        target=service.settings.root/'dist/alba-albi.apk'
        if not target.is_file(): raise web.HTTPNotFound()
        return web.FileResponse(target,headers={'Content-Type':'application/vnd.android.package-archive','Content-Disposition':'attachment; filename=alba-albi.apk'})
    app.router.add_get('/download/alba-albi.apk',android_download)
    async def feedback(request):
        uid=request['identity']['user_id']; value=await request.json()
        if not isinstance(value,dict) or set(value)-{'label','message_id'} or type(value.get('message_id')) is not int: raise ValueError()
        record_feedback(service.store,uid,value.get('label'),value['message_id'])
        return web.json_response({'ok':True})
    app.router.add_post('/api/feedback',feedback)
    setup_tramonto(app,service)
    setup_core(app,service)
    setup_identity(app,service,session_cookie,guard)
    return app


async def main():
    os.umask(0o077)
    settings=Settings.from_env()
    store=Store(settings.data/'alba.sqlite3')
    keys=Keys(store,secret_file(settings.data/'auth.key'))
    backups=Backups(store,settings)
    async with ClientSession(trust_env=False) as session:
        engine=Engine(store,settings,session)
        service=Service(store,settings,keys,engine,backups)
        if not settings.admins and not store.setting('bootstrap_admin') and not store.setting('bootstrap_digest'):
            token=secrets.token_urlsafe(32)
            store.set_setting('bootstrap_digest',keys.digest(token))
            path=settings.data/'bootstrap.txt'
            path.write_text(token+'\n')
            os.chmod(path,0o600)
            log.info('Chiave iniziale salvata in data/bootstrap.txt (nessun segreto nei log).')
        runner=web.AppRunner(web_app(service),access_log=None)
        await runner.setup()
        # Only loopback. Funnel/reverse proxy serves the authenticated interface with HTTPS.
        await web.TCPSite(runner,'127.0.0.1',settings.web_port).start()
        tasks=[]
        async def periodic_backup():
            while True:
                try:
                    backups.scheduled()
                except Exception as exc:
                    log.error('Backup non riuscito (%s)',type(exc).__name__)
                await asyncio.sleep(3600)
        tasks.append(asyncio.create_task(periodic_backup()))
        tasks.append(asyncio.create_task(service.performance.run()))
        tasks.append(asyncio.create_task(periodic_memory(store,service)))
        tasks.append(asyncio.create_task(service.core.run()))
        if settings.bot_token:
            telegram=Telegram(service,session,settings.bot_token)
            async def maintenance_notice():
                now=time.time()
                if now-float(store.setting('maintenance_notice_last','0'))<3600: return
                store.set_setting('maintenance_notice_last',now)
                for row in store.rows('SELECT a.user_id FROM user_activity a JOIN users u ON u.id=a.user_id WHERE u.authorized=1 AND a.last_seen>?',(now-300,)):
                    await telegram.api('sendMessage',{'chat_id':row['user_id'],'text':service.maintenance['message']})
            service.maintenance_notify=maintenance_notice
            tasks.append(asyncio.create_task(telegram.run()))
        stop=asyncio.Event()
        loop=asyncio.get_running_loop()
        for sig in (signal.SIGTERM,signal.SIGINT):
            loop.add_signal_handler(sig,stop.set)
        log.info('Alba avviata, modello=%s, web=127.0.0.1:%s',settings.model,settings.web_port)
        waiter=asyncio.create_task(stop.wait())
        done,_=await asyncio.wait([waiter,*tasks],return_when=asyncio.FIRST_COMPLETED)
        failed=False
        for task in done:
            if task is not waiter and not task.cancelled() and task.exception():
                failed=True
                log.error('Un servizio essenziale è terminato (%s)',type(task.exception()).__name__)
        for task in [waiter,*tasks]:
            task.cancel()
        await asyncio.gather(waiter,*tasks,return_exceptions=True)
        await runner.cleanup()
    store.close()
    if failed:
        raise RuntimeError('Un servizio essenziale è terminato; systemd riavvierà Alba.') from None


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(main())
