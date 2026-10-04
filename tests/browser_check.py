"""Optional browser verification. Uses only a temporary DB and synthetic users.

Run with: .venv/bin/python tests/browser_check.py
Requires Playwright and its Chromium browser on the verification machine only.
"""
import asyncio
import calendar
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys,secret_file
from service import Service
from store import Store,Scope
from usage import ROME


class TestResponse:
    status=200
    def __init__(self,delay=0): self.delay=delay
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def json(self):
        await asyncio.sleep(self.delay)
        return {'message':{'content':json.dumps({'reply':'Possiamo partire da quello che ti pesa oggi. Cosa vorresti mettere a fuoco?',
            'used_memory_ids':[],'personal_claims':[]})},'prompt_eval_count':40,'eval_count':25}


class TestModel:
    delay=0
    def post(self,*args,**kwargs): return TestResponse(self.delay)


async def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for name in ('web.html','web.css','web.js','portal-motion.js'): shutil.copy2(ROOT/name,root/name)
        settings=Settings(root=root,admins=(1,),allowed=(2,))
        store=Store(settings.data/'alba.sqlite3')
        keys=Keys(store,secret_file(settings.data/'auth.key'))
        service=Service(store,settings,keys,Engine(store,settings,TestModel()),Backups(store,settings))
        store.register(1,'Andrea'); store.register(2,'Giulia')
        username,password=keys.set_web_password(1,1,'admin')
        mid=store.add_message(Scope('user',2),2,'user','Mi chiamo Giulia')
        store.add_memory(Scope('user',2),'Mi chiamo Giulia','personal',[mid])
        for index in range(75): store.add_message(Scope('user',1),1,'user','Nota personale di prova '+str(index))
        now=datetime.now(ROME); first=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        store.set_setting('token_tracking_since',first.timestamp())
        for day in range(1,now.day+1):
            if day%3==0 or day==now.day:
                store.record_tokens(Scope('user',1),1,'test','ollama',day*57,day*23,
                    timestamp=first.replace(day=day,hour=10).timestamp())
        store.record_tokens(Scope('user',2),2,'test','ollama',800,200,
            timestamp=now.replace(hour=9).timestamp())
        server=TestServer(web_app(service)); await server.start_server()
        artifacts=ROOT/'artifacts'; artifacts.mkdir(exist_ok=True)
        errors=[]
        try:
            async with async_playwright() as p:
                browser=await p.chromium.launch()
                context=await browser.new_context(viewport={'width':1440,'height':1100},locale='it-IT',color_scheme='light')
                page=await context.new_page()
                page.on('pageerror',lambda error: errors.append(str(error)))
                page.on('console',lambda message: errors.append(message.text) if message.type=='error' and '403' not in message.text else None)
                await page.goto(str(server.make_url('/')))
                await page.locator('#username').fill(username)
                await page.locator('#password').fill(password)
                await page.locator('#loginButton').click()
                await page.locator('#dashboard').wait_for(state='visible')
                await page.locator('#systemBar').wait_for(state='visible')
                assert await page.locator('.telegram-badge').is_visible()
                samples=[]
                page.on('response',lambda response:samples.append(response.url) if '/api/status' in response.url else None)
                await page.wait_for_timeout(4200); assert len(samples)>=2
                await page.wait_for_function("() => document.querySelectorAll('.day').length > 0")
                assert await page.locator('.day').count()==calendar.monthrange(now.year,now.month)[1]
                assert await page.locator('#scopeControl').is_visible()
                assert await page.locator('#accountRole').inner_text()=='Amministratore'
                assert await page.locator('#usageScope').input_value()=='bot'
                await page.locator('#loadOlder').wait_for(state='visible')
                assert await page.locator('#messages .bubble').count()==50
                await page.locator('#messages').evaluate('(el) => el.scrollTop = 0')
                anchor=page.locator('#messages .bubble').first
                anchor_id=await anchor.get_attribute('data-message-id'); original_top=(await anchor.bounding_box())['y']
                await page.locator('#loadOlder').click()
                await page.wait_for_function('() => document.querySelectorAll("#messages .bubble").length === 75')
                anchor=page.locator('[data-message-id="'+anchor_id+'"]')
                assert abs((await anchor.bounding_box())['y']-original_top)<2
                assert await page.locator('#messages .bubble').first.inner_text()=='Nota personale di prova 0'
                assert 'Inizio' in await page.locator('#historyStatus').inner_text()
                top=await page.locator('#messages').evaluate('(el) => el.scrollTop')
                store.add_message(Scope('user',1),1,'user','Messaggio Telegram mentre leggo lo storico')
                await page.evaluate('() => syncHistory()')
                assert await page.locator('#messages .bubble').count()==76
                assert abs(await page.locator('#messages').evaluate('(el) => el.scrollTop')-top)<2
                await page.wait_for_timeout(600)
                await page.screenshot(path=str(artifacts/'ui-light.png'),full_page=True)
                today=page.locator('.day.today')
                await today.hover()
                assert await page.locator('#dayTooltip').is_visible()
                assert 'Ingresso' in await page.locator('#dayTooltip').inner_text()
                await today.click()
                assert await today.get_attribute('aria-pressed')=='true'
                assert len(await page.locator('#dayDetail .day-metrics strong').all_text_contents())==3
                await page.locator('#usageScope').select_option('self')
                await page.wait_for_function("() => document.querySelector('#dayDetail .day-metrics strong').textContent === new Intl.NumberFormat('it-IT').format("+str(now.day*80)+")")
                await page.locator('#prevMonth').click()
                await page.wait_for_function("() => document.querySelectorAll('.day.untracked').length > 0")
                await page.locator('.day.untracked').first.click()
                assert 'non registrati' in await page.locator('#dayDetail').inner_text()
                await page.locator('#nextMonth').click()
                await page.locator('.day.today').wait_for()
                await page.locator('#message').fill('Vorrei riflettere su una scelta.')
                await page.locator('#chatForm').evaluate('(form) => form.requestSubmit()')
                await page.wait_for_function("() => document.querySelector('#send').disabled === false")
                assert 'Cosa vorresti' in await page.locator('.bubble.assistant').last.inner_text()
                await page.locator('#themeToggle').click()
                assert await page.evaluate('document.documentElement.dataset.theme')=='dark'
                await page.wait_for_timeout(400)
                await page.screenshot(path=str(artifacts/'ui-dark.png'),full_page=True)
                await page.reload(); await page.locator('#dashboard').wait_for(state='visible')
                assert await page.evaluate('document.documentElement.dataset.theme')=='dark'
                original=await page.locator('#snake1').get_attribute('d')
                await page.locator('#albaSymbol').hover(); await page.wait_for_timeout(180)
                animated=await page.locator('#snake1').get_attribute('d')
                assert animated != original
                await page.mouse.move(1000,1050); await page.wait_for_timeout(500)
                assert await page.locator('#snake1').get_attribute('d')==original
                await page.locator('#motionSettings summary').click()
                for mode in ('snakes','orbit','vortex','wave','braid','bounce','spark','breathe'):
                    await page.locator('#iconAnimation').select_option(mode)
                    await page.wait_for_timeout(160)
                    assert await page.locator('#albaSymbol').get_attribute('data-animation')==mode
                    assert await page.locator('#snake1').get_attribute('d')!=original
                await page.locator('#motionEnabled').uncheck()
                assert await page.locator('#snake1').get_attribute('d')==original
                await page.locator('#motionEnabled').check()
                await page.locator('#mascotButton').click(); first=await page.locator('#companion').get_attribute('data-state')
                await page.locator('#mascotButton').click(); second=await page.locator('#companion').get_attribute('data-state')
                assert first!=second
                await page.locator('#adminTab').click()
                await page.locator('.admin-row').first.wait_for()
                await page.locator('#authorizeId').fill('999')
                try:
                    await page.locator('#authorizeForm button').click(timeout=10000)
                except Exception:
                    await page.screenshot(path=str(artifacts/'admin-failure.png'),full_page=True)
                    print(await page.evaluate('''() => ({active:document.activeElement.id,scrollY,animations:document.getAnimations().map(a=>({target:a.effect.target.className,name:a.animationName,playState:a.playState})),button:document.querySelector('#authorizeForm button').getBoundingClientRect().toJSON()})'''),flush=True)
                    raise
                await page.wait_for_function('() => document.querySelector("#adminMessage").textContent.includes("autorizzato")')
                assert store.allowed(999)
                await page.locator('.admin-row').filter(has_text='999').get_by_text('Revoca',exact=True).click()
                await page.wait_for_function('() => document.querySelector("#adminMessage").textContent.includes("disabilitato")')
                assert not store.allowed(999)
                consent=keys.issue(2,2,'memory_read');await page.evaluate('(token)=>api("/api/admin/memory-access",{user_id:"2",token})',consent)
                await page.locator('.admin-row').filter(has_text='Giulia').get_by_text('Memorie',exact=True).click()
                await page.locator('#memoryDialog').wait_for(state='visible')
                assert 'Mi chiamo Giulia' in await page.locator('#memoryList').inner_text()
                await page.locator('#closeMemory').click()
                quota_form=page.locator('#adminUsers .admin-row').filter(has_text='Giulia').locator('form')
                await quota_form.locator('input').fill('2000'); await quota_form.locator('button').click()
                await page.wait_for_function('() => document.querySelector("#adminMessage").textContent.includes("Limite mensile aggiornato")')
                assert store.rows('SELECT token_limit FROM user_limits WHERE user_id=2')[0]['token_limit']==2000
                await page.locator('#breakMinutes').fill('25'); await page.locator('#breakSettingsForm button').click()
                await page.wait_for_function('() => document.querySelector("#adminMessage").textContent.includes("pausa aggiornato")')
                await page.locator('#privacyOwner').fill('Gestore di test'); await page.locator('#privacyContact').fill('privacy@example.test'); await page.locator('#privacySettingsForm button').click()
                await page.wait_for_function('() => document.querySelector("#adminMessage").textContent.includes("Recapiti")')
                await page.locator('#pauseBot').click()
                await page.wait_for_function('() => document.querySelector("#botState").textContent === "In pausa"')
                await page.locator('#pauseBot').click()
                await page.wait_for_function('() => document.querySelector("#botState").textContent === "Attivo"')
                await page.locator('#automaticAccess').check()
                await page.wait_for_function('() => document.querySelector("#adminMessage").textContent.includes("automatico attivato")')
                await page.locator('#nightTime').fill('22:30')
                await page.locator('#memoryScheduleForm button[type=submit]').click()
                await page.wait_for_function('() => document.querySelector("#adminMessage").textContent.includes("22:30")')
                await page.locator('#memoryFlush').click()
                await page.wait_for_function('() => document.querySelector("#adminMessage").textContent.includes("aggiornati")')
                assert await page.locator('#diskUsed').get_attribute('stroke-dasharray')!='0 100'
                await page.wait_for_timeout(700)
                await page.screenshot(path=str(artifacts/'ui-admin.png'),full_page=True)
                await page.locator('#conversationTab').click()
                await page.locator('#mascotButton').scroll_into_view_if_needed()
                rect=await page.locator('#mascotButton').bounding_box()
                await page.mouse.move(rect['x']+rect['width']/2,rect['y']+rect['height']/2); await page.mouse.down(); await page.mouse.move(40,320,steps=12); await page.mouse.up()
                assert await page.locator('#companion').evaluate('(el) => el.classList.contains("mascot-floating")')
                assert await page.evaluate('() => { const a=document.querySelector("#companion").getBoundingClientRect(), b=document.querySelector("#chat").getBoundingClientRect(); return !(a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top); }')
                service.engine.session.delay=20
                await service.engine.lock.acquire()
                await page.locator('#message').fill('Vorrei prendermi una pausa.')
                await page.locator('#chatForm').evaluate('(form) => form.requestSubmit()')
                await page.locator('#stop').wait_for(state='visible')
                await page.wait_for_function('() => document.querySelector("#thinkingLabel").textContent.includes("in coda")')
                assert 'trascorsi' in await page.locator('#thinkingElapsed').inner_text()
                service.engine.lock.release()
                await page.wait_for_function('() => document.querySelector("#thinkingLabel").textContent.includes("preparando")')
                await page.locator('#stop').click()
                await page.locator('.bubble.cancelled').wait_for()
                assert await page.locator('#send').is_enabled()
                assert not service.engine.lock.locked()
                await context.close()
                mobile=await browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,locale='it-IT',color_scheme='dark',reduced_motion='reduce')
                page=await mobile.new_page(); page.on('pageerror',lambda error:errors.append(str(error)))
                await page.goto(str(server.make_url('/')))
                token=keys.issue(2,2,'web')
                await page.goto(str(server.make_url('/'))+'#web_key='+token)
                try: await page.locator('#dashboard').wait_for(state='visible',timeout=10000)
                except Exception:
                    print('Link login failed:',errors,await page.locator('#error').inner_text(),await page.locator('#keyTab').get_attribute('aria-selected'),flush=True)
                    raise
                await page.locator('.day.today').wait_for()
                assert await page.evaluate('location.hash')==''
                assert token not in page.url
                assert not await page.locator('#scopeControl').is_visible()
                assert await page.locator('.telegram-badge').is_visible()
                total=await page.locator('#totalTokens').inner_text()
                formatted=await page.evaluate("new Intl.NumberFormat('it-IT').format(1000)")
                assert total==formatted,(total,formatted)
                await page.locator('.day.today').tap()
                assert formatted in await page.locator('#dayDetail').inner_text()
                assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                before=await page.locator('#snake1').get_attribute('d')
                await page.locator('#albaSymbol').tap(); await page.wait_for_timeout(150)
                assert await page.locator('#snake1').get_attribute('d')==before
                await page.screenshot(path=str(artifacts/'ui-mobile.png'),full_page=True)
                from runtime_features import touch_activity
                touch_activity(store,2); store.execute('UPDATE user_activity SET started=?,last_seen=? WHERE user_id=2',(time.time()-1600,time.time()))
                await page.evaluate('() => refreshStatus()'); await page.locator('#breakDialog').wait_for(state='visible')
                await page.locator('#continueChat').click()
                service.capacity.leases.clear(); service.capacity.waiting.clear()
                for uid in range(10,15): service.capacity.enter(uid)
                await page.evaluate('() => { presenceTime=0; return refreshStatus(); }')
                assert await page.locator('#capacityNotice').is_visible(); assert not await page.locator('#send').is_enabled()
                service.capacity.leave(10)
                await page.evaluate('() => { presenceTime=0; return refreshStatus(); }')
                assert not await page.locator('#capacityNotice').is_visible(); assert await page.locator('#send').is_enabled()
                mid=store.add_message(Scope('user',2),2,'user','Messaggio arrivato da Telegram')
                await page.evaluate('() => syncHistory()')
                assert 'Messaggio arrivato da Telegram' in await page.locator('#messages').inner_text()
                await page.locator('#logout').click(); await page.locator('#login').wait_for(state='visible')
                for path,article in (('/privacy','#privacyArticle'),('/cookies','#cookieArticle'),('/policy','#termsArticle')):
                    await page.goto(str(server.make_url(path))); await page.locator(article).wait_for(state='visible')
                    assert not await page.locator('#login').is_visible()
                    assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                await page.goto(str(server.make_url('/privacy')))
                await page.wait_for_function('() => document.querySelector(".policy-owner").textContent === "Gestore di test"')
                await browser.close()
        finally:
            await server.close(); store.close()
        assert not errors,errors
    print('Browser OK: accesso da link monouso senza copia, password, permessi, calendario, chat/Stop, coda e tempo di attesa, storico completo senza spostare la lettura, animazioni e trascinamento Albi, risorse ogni 2s, limiti token, pause, cinque posti/attesa, storico Telegram unificato, privacy/cookie/policy, admin, memorie, torta disco, temi, mobile, logout.')


if __name__=='__main__': asyncio.run(main())
