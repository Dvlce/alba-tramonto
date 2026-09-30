"""Optional, verified OAuth/SMS accounts. Identity linking always requires an authenticated owner."""
import base64
import hashlib
import json
import os
import re
import secrets
import time
from urllib.parse import urlencode
from aiohttp import ClientSession,ClientTimeout,BasicAuth,web
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROVIDERS={
 'google':{'title':'Google / Gmail','authorize':'https://accounts.google.com/o/oauth2/v2/auth','token':'https://oauth2.googleapis.com/token','user':'https://openidconnect.googleapis.com/v1/userinfo','scope':'openid email profile'},
 'github':{'title':'GitHub','authorize':'https://github.com/login/oauth/authorize','token':'https://github.com/login/oauth/access_token','user':'https://api.github.com/user','scope':'read:user user:email'},
 'discord':{'title':'Discord','authorize':'https://discord.com/oauth2/authorize','token':'https://discord.com/api/oauth2/token','user':'https://discord.com/api/users/@me','scope':'identify email'}}

class Identity:
    def __init__(self,service): self.service=service; self.store=service.store; self.keys=service.keys; self.cipher=AESGCM(service.keys.pepper)
    def encrypt(self,value):
        nonce=os.urandom(12); return nonce+self.cipher.encrypt(nonce,json.dumps(value).encode(),b'Alba identity v1')
    def decrypt(self,value): return json.loads(self.cipher.decrypt(value[:12],value[12:],b'Alba identity v1'))
    def config(self,provider):
        rows=self.store.rows('SELECT payload FROM identity_settings WHERE provider=?',(provider,)); return self.decrypt(rows[0]['payload']) if rows else {}
    def configured(self,provider):
        value=self.config(provider); return bool(value.get('enabled') and value.get('client_id') and value.get('client_secret') and (provider!='phone' or value.get('service_sid')))
    def callback(self,provider): return self.service.settings.public_url+'/auth/'+provider+'/callback'
    def save_config(self,provider,value):
        if provider not in (*PROVIDERS,'phone') or not isinstance(value,dict): raise ValueError('Provider non valido.')
        current=self.config(provider)
        for field in ('client_id','client_secret','service_sid'):
            if field in value:
                text=value[field]
                if not isinstance(text,str) or len(text)>2000: raise ValueError('Credenziale troppo lunga.')
                if text.strip(): current[field]=text.strip()
        if type(value.get('enabled')) is not bool: raise ValueError('Seleziona se attivare il provider.')
        current['enabled']=value['enabled']
        if provider=='phone' and current['enabled']:
            if not re.fullmatch(r'AC[0-9a-fA-F]{32}',current.get('client_id','')) or not re.fullmatch(r'VA[0-9a-fA-F]{32}',current.get('service_sid','')): raise ValueError('Servono Account SID AC… e Verify Service SID VA… di Twilio.')
        if current['enabled'] and (not current.get('client_id') or not current.get('client_secret')): raise ValueError('Inserisci ID e segreto prima di attivare.')
        self.store.execute('INSERT OR REPLACE INTO identity_settings VALUES(?,?)',(provider,self.encrypt(current)))
    def flow(self,kind,payload):
        self.store.execute('DELETE FROM auth_flows WHERE expires<?',(time.time(),))
        if self.store.rows('SELECT count(*) AS n FROM auth_flows')[0]['n']>=100: raise ValueError('Troppi accessi in corso: attendi alcuni minuti.')
        token=secrets.token_urlsafe(32)
        self.store.execute('INSERT INTO auth_flows(digest,kind,expires,payload,user_id) VALUES(?,?,?,?,?)',(self.keys.digest(token),kind,time.time()+600,self.encrypt(payload),payload.get('uid')))
        return token
    def read_flow(self,token,kind,consume=False):
        if not isinstance(token,str) or len(token)>100: raise PermissionError()
        digest=self.keys.digest(token); rows=self.store.rows('SELECT * FROM auth_flows WHERE digest=? AND kind=? AND expires>?',(digest,kind,time.time()))
        if not rows or rows[0]['attempts']>=5: raise PermissionError('Verifica scaduta o troppi tentativi.')
        row=rows[0]; value=self.decrypt(row['payload'])
        if consume: self.store.execute('DELETE FROM auth_flows WHERE digest=?',(digest,))
        return row,value
    def target(self,request,value):
        mode=value.get('mode','login')
        if mode not in ('login','link'): raise ValueError()
        if mode=='login': return {}
        identity=self.keys.identify(request.cookies.get('session',''))
        if not secrets.compare_digest(request.headers.get('X-Session-CSRF',''),identity['csrf']): raise PermissionError()
        return {'uid':identity['user_id'],'session_digest':identity['digest']}
    def assign(self,provider,profile,target):
        subject=profile['subject']
        if not isinstance(subject,str) or not 1<=len(subject)<=256: raise PermissionError('Identità non verificata.')
        existing=self.store.rows('SELECT user_id FROM auth_accounts WHERE provider=? AND subject=?',(provider,subject))
        uid=target.get('uid')
        if uid is not None:
            session=self.store.rows('SELECT 1 FROM web_sessions WHERE digest=? AND user_id=? AND expires>?',(target.get('session_digest'),uid,time.time()))
            if not session or not self.store.allowed(uid): raise PermissionError('Accedi di nuovo prima di collegare un account.')
            if existing and existing[0]['user_id']!=uid: raise PermissionError('Questo account è già collegato a un’altra persona.')
        elif existing: uid=existing[0]['user_id']
        else:
            if self.store.rows('SELECT count(*) AS n FROM users')[0]['n']>=100: raise ValueError('Richieste di registrazione temporaneamente complete.')
            minimum=self.store.rows('SELECT min(id) AS n FROM users')[0]['n']; uid=min(-1000000000,(minimum or 0)-1)
            self.store.register(uid,str(profile.get('name','Utente'))[:80])
        self.store.execute('INSERT OR IGNORE INTO auth_accounts VALUES(?,?,?,?,?)',(provider,subject,uid,str(profile.get('email',''))[:254],time.time()))
        if target.get('uid') is None and not self.store.allowed(uid) and self.store.setting('automatic_web_access')=='1' and not self.store.rows('SELECT 1 FROM access_blocks WHERE user_id=?',(uid,)):
            try: self.store.authorize(uid,self.service.settings.max_users)
            except ValueError: pass
        self.store.audit(uid,'identity_link_'+provider,uid)
        if not self.store.allowed(uid): raise PermissionError('Registrazione ricevuta; l’amministratore deve autorizzare il tuo account.')
        return uid
    async def http(self,method,url,**kwargs):
        async with ClientSession(timeout=ClientTimeout(total=15)) as session:
            async with session.request(method,url,allow_redirects=False,**kwargs) as response:
                if response.status not in (200,201): raise PermissionError('Il servizio non ha completato la verifica.')
                return await response.json()
    async def exchange(self,provider,code,payload):
        config=self.config(provider); spec=PROVIDERS[provider]
        data={'client_id':config['client_id'],'client_secret':config['client_secret'],'code':code,'grant_type':'authorization_code','redirect_uri':self.callback(provider)}
        if provider=='google': data['code_verifier']=payload['verifier']
        token=await self.http('POST',spec['token'],data=data,headers={'Accept':'application/json','User-Agent':'AlbaLocal/1.0'})
        access=token.get('access_token')
        if not isinstance(access,str) or not access: raise PermissionError()
        headers={'Authorization':'Bearer '+access,'Accept':'application/json','User-Agent':'AlbaLocal/1.0'}
        profile=await self.http('GET',spec['user'],headers=headers)
        if provider=='google':
            if profile.get('email_verified') is not True: raise PermissionError('Email Google non verificata.')
            return {'subject':profile.get('sub'),'email':profile.get('email',''),'name':profile.get('name','Utente Google')}
        if provider=='github':
            emails=await self.http('GET','https://api.github.com/user/emails',headers=headers)
            verified=sorted([value for value in emails if value.get('verified') is True],key=lambda value:not value.get('primary'))
            if not verified: raise PermissionError('Verifica prima la tua email GitHub.')
            return {'subject':str(profile['id']),'email':verified[0]['email'],'name':profile.get('name') or profile.get('login','Utente GitHub')}
        if profile.get('verified') is not True: raise PermissionError('Verifica prima la tua email Discord.')
        return {'subject':str(profile['id']),'email':profile.get('email',''),'name':profile.get('global_name') or profile.get('username','Utente Discord')}
    async def sms(self,action,phone,code=None):
        config=self.config('phone'); suffix='Verifications' if action=='start' else 'VerificationCheck'; data={'To':phone}
        data.update({'Channel':'sms'} if action=='start' else {'Code':code})
        return await self.http('POST','https://verify.twilio.com/v2/Services/'+config['service_sid']+'/'+suffix,data=data,auth=BasicAuth(config['client_id'],config['client_secret']))

def setup_identity(app,service,session_cookie,guard):
    manager=Identity(service); service.identity=manager
    def csrf(request):
        cookie=request.cookies.get('auth_csrf',''); parts=cookie.split('.')
        if len(parts)!=3 or not parts[1].isdigit() or float(parts[1])<time.time() or not secrets.compare_digest(parts[2],service.keys.digest('auth:'+parts[0]+':'+parts[1])) or not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),parts[0]): raise PermissionError()
    async def providers(request):
        nonce=secrets.token_urlsafe(24); expires=str(int(time.time()+3600)); cookie=nonce+'.'+expires+'.'+service.keys.digest('auth:'+nonce+':'+expires)
        response=web.json_response({'providers':[{'id':name,'title':spec['title'],'enabled':manager.configured(name)} for name,spec in PROVIDERS.items()],
                                   'phone_enabled':manager.configured('phone'),'csrf':nonce,'registration_limit':service.settings.max_users})
        response.set_cookie('auth_csrf',cookie,secure=True,httponly=True,samesite='Strict',max_age=3600,path='/'); return response
    async def begin(request):
        csrf(request); value=await request.json(); provider=request.match_info['provider']
        if not isinstance(value,dict) or provider not in PROVIDERS or not manager.configured(provider): raise ValueError('Accesso non ancora configurato dall’amministratore.')
        if value.get('privacy_accepted') is not True: raise ValueError('Leggi e accetta privacy e regole per accedere.')
        guard.hit('oauth-start',40); target=manager.target(request,value); verifier=secrets.token_urlsafe(48); target.update(verifier=verifier,remember=value.get('remember',True))
        if type(target['remember']) is not bool: raise ValueError()
        state=manager.flow(provider,target); spec=PROVIDERS[provider]; config=manager.config(provider)
        params={'client_id':config['client_id'],'redirect_uri':manager.callback(provider),'response_type':'code','scope':spec['scope'],'state':state}
        if provider=='google': params.update(code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),code_challenge_method='S256')
        response=web.json_response({'url':spec['authorize']+'?'+urlencode(params)})
        response.set_cookie('oauth_state',state,secure=True,httponly=True,samesite='Lax',max_age=600,path='/auth/'); return response
    async def callback(request):
        provider=request.match_info['provider']; state=request.query.get('state',''); cookie=request.cookies.get('oauth_state','')
        response=None
        try:
            if provider not in PROVIDERS or not manager.configured(provider) or not state or not secrets.compare_digest(state,cookie): raise PermissionError()
            _,target=manager.read_flow(state,provider,consume=True); code=request.query.get('code','')
            if not 1<=len(code)<=2048: raise PermissionError()
            profile=await manager.exchange(provider,code,target); uid=manager.assign(provider,profile,target)
            token,_=service.keys.create_session(uid,target['remember'],PROVIDERS[provider]['title']+' · Browser')
            response=web.HTTPFound('/'); session_cookie(response,token,target['remember']); service.store.audit(uid,'identity_login_'+provider,uid)
        except Exception:
            response=web.HTTPFound('/?auth_error=verification_failed')
        response.del_cookie('oauth_state',path='/auth/'); return response
    async def phone_start(request):
        csrf(request); value=await request.json()
        if not isinstance(value,dict) or not manager.configured('phone'): raise ValueError('Accesso SMS non ancora configurato.')
        phone=value.get('phone','')
        if not isinstance(phone,str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}',phone) or value.get('privacy_accepted') is not True: raise ValueError('Inserisci un numero internazionale, per esempio +39…, e accetta le informative.')
        target=manager.target(request,value); target.update(phone=phone,remember=value.get('remember',True))
        if type(target['remember']) is not bool: raise ValueError()
        digest=service.keys.digest('phone:'+phone); now=time.time(); day=time.strftime('%Y-%m-%d',time.gmtime())
        last=float(service.store.setting('sms_last_'+digest,'0')); count=int(service.store.setting('sms_count_'+day,'0')); own=int(service.store.setting('sms_'+day+'_'+digest,'0'))
        if now-last<60 or count>=20 or own>=3: return web.json_response({'error':'Limite SMS raggiunto. Attendi oppure usa un altro metodo di accesso.'},status=429)
        service.store.set_setting('sms_last_'+digest,now); service.store.set_setting('sms_count_'+day,count+1); service.store.set_setting('sms_'+day+'_'+digest,own+1)
        await manager.sms('start',phone); token=manager.flow('phone',target)
        response=web.json_response({'ok':True,'message':'Codice inviato. Scade tra dieci minuti.'}); response.set_cookie('phone_flow',token,secure=True,httponly=True,samesite='Strict',max_age=600,path='/auth/'); return response
    async def phone_check(request):
        csrf(request); value=await request.json(); code=value.get('code','') if isinstance(value,dict) else ''
        if not isinstance(code,str) or not re.fullmatch(r'[0-9]{4,10}',code) or not manager.configured('phone'): raise ValueError('Codice non valido.')
        token=request.cookies.get('phone_flow',''); row,target=manager.read_flow(token,'phone')
        service.store.execute('UPDATE auth_flows SET attempts=attempts+1 WHERE digest=?',(row['digest'],))
        result=await manager.sms('check',target['phone'],code)
        if result.get('status')!='approved': raise PermissionError('Codice non corretto.')
        manager.read_flow(token,'phone',consume=True)
        uid=manager.assign('phone',{'subject':service.keys.digest('phone:'+target['phone']),'name':'Utente · '+target['phone'][-4:]},target)
        cookie,session_csrf=service.keys.create_session(uid,target['remember'],'Telefono · Browser'); response=web.json_response({'ok':True,'csrf':session_csrf}); session_cookie(response,cookie,target['remember']); response.del_cookie('phone_flow',path='/auth/'); return response
    async def accounts(request):
        uid=request['identity']['user_id']; rows=service.store.rows('SELECT provider,email,created FROM auth_accounts WHERE user_id=?',(uid,))
        return web.json_response({'accounts':rows,'telegram_linked':uid>0})
    async def settings(request):
        uid=request['identity']['user_id']
        if not service.is_admin(uid): raise PermissionError()
        if request.method=='POST':
            value=await request.json()
            if not isinstance(value,dict): raise ValueError()
            manager.save_config(value.get('provider'),value); service.store.audit(uid,'identity_provider_config',uid)
            return web.json_response({'ok':True,'message':'Configurazione salvata. I segreti sono cifrati sul server.'})
        providers=[]
        for name in (*PROVIDERS,'phone'):
            config=manager.config(name); providers.append({'id':name,'title':PROVIDERS.get(name,{'title':'Telefono · Twilio Verify'})['title'],
                'enabled':manager.configured(name),'client_id':config.get('client_id',''),'service_sid':config.get('service_sid',''),'has_secret':bool(config.get('client_secret')),
                'callback':manager.callback(name) if name!='phone' else ''})
        return web.json_response({'providers':providers})
    app.add_routes([web.get('/auth/providers',providers),web.post('/auth/{provider}/start',begin),web.get('/auth/{provider}/callback',callback),
        web.post('/auth/phone/send',phone_start),web.post('/auth/phone/check',phone_check),web.get('/api/accounts',accounts),
        web.get('/api/admin/identity',settings),web.post('/api/admin/identity',settings)])
