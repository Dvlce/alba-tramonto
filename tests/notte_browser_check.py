"""Desktop/mobile functional review using a temporary database and a fake local model."""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys,secret_file
from service import Service
from store import Store
from test_core import Model


async def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for name in ('web.html','web.css','web.js','notte.html','notte.css','notte.js'):
            shutil.copy2(ROOT/name,root/name)
        (root/'vendor').mkdir()
        for name in ('marked.min.js','purify.min.js'):shutil.copy2(ROOT/'vendor'/name,root/'vendor'/name)
        settings=Settings(root=root,admins=(1,),allowed=(2,))
        store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'))
        service=Service(store,settings,keys,Engine(store,settings,Model()),Backups(store,settings))
        store.register(1,'Matt');store.register(2,'Utente')
        cookie,csrf=keys.create_session(1,True)
        application=web_app(service)
        service.core.event('notes','note','<script>alert("xss")</script>\nNota **privata**.')
        server=TestServer(application);await server.start_server()
        errors=[]
        try:
            async with async_playwright() as p:
                browser=await p.chromium.launch()
                context=await browser.new_context(viewport={'width':1440,'height':1000})
                await context.add_cookies([{'name':'session','value':cookie,'url':str(server.make_url('/'))}])
                page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(str(server.make_url('/notte')))
                await page.locator('#streamState').filter(has_text='In diretta').wait_for()
                await page.locator('#chatText').fill('Una domanda sulle galassie.')
                await page.locator('#sendChat').click()
                await page.locator('#chatEvents .night-event.assistant').wait_for()
                assert await page.locator('#chatEvents strong').inner_text()=='Interessante.'
                await page.locator('#tab-memory').click()
                assert await page.locator('.connector').count()==9
                await page.locator('.connector').filter(has_text='Note interne').get_by_text('Ispeziona').click()
                await page.locator('#inspection .night-event').first.wait_for()
                assert await page.locator('#inspection script').count()==0
                await page.locator('.connector').filter(has_text='Note interne').locator('input').uncheck()
                await page.wait_for_function("() => !document.querySelectorAll('.connector input')[2].checked")
                await page.locator('#consolidate').click()
                await page.wait_for_function("() => document.querySelector('#cycles').textContent.includes('ok')")
                await page.locator('#tab-summaries').click()
                await page.locator('#summaryEvents .night-event').first.wait_for()
                await page.locator('#tab-tokens').click()
                assert int((await page.locator('#lifetimeTokens').inner_text()).replace('.',''))>0
                await page.locator('#tokenLegend button').first.click()
                assert 'token' in await page.locator('#chartDetail').inner_text()
                await page.locator('#tab-system').click()
                await page.locator('#interval').select_option('30')
                await page.get_by_role('button',name='Salva il ritmo').click()
                await page.locator('#notice').filter(has_text='Ritmo aggiornato').wait_for()
                assert service.core.config['interval']==30
                await page.locator('#toggleAutonomy').click()
                await page.locator('#toggleAutonomy').filter(has_text='Risveglia').wait_for()
                await page.locator('#tab-chat').click()
                assert await page.locator('#chatText').evaluate('(el) => getComputedStyle(el).resize')=='none'
                service.core.store.execute('INSERT INTO core_diary(topic,title,summary,sources,code,result,status,created) VALUES(?,?,?,?,?,?,?,?)',
                    ('Python','count_words','Conteggio delle parole.','["https://github.com/PyCQA/pycodestyle"]','def count_words(text): return {}','PASS: 3 casi indipendenti','verified',1))
                await page.locator('#tab-diary').click()
                await page.locator('#diaryEntries').filter(has_text='Test superati').wait_for()
                await page.locator('#diaryTopic').select_option('Python')
                assert await page.locator('#diaryEntries .diary-entry').count()==1
                await page.screenshot(path=str(ROOT/'artifacts/notte-diary.png'),full_page=True)
                await page.locator('#tab-chat').click()
                artifacts=ROOT/'artifacts';artifacts.mkdir(exist_ok=True)
                await page.screenshot(path=str(artifacts/'notte-desktop.png'),full_page=True)
                await page.set_viewport_size({'width':390,'height':844})
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await page.screenshot(path=str(artifacts/'notte-mobile.png'),full_page=True)
                await page.goto(str(server.make_url('/')))
                await page.locator('#dashboard').wait_for(state='visible')
                assert await page.locator('#notteLink').count()==1
                await browser.close()
        finally:await server.close();store.close()
        assert not errors,errors
    print('Notte browser OK: live chat, markdown/XSS, connector toggles, consolidation, summaries, tokens, settings, autonomy, desktop/mobile and Alba navigation.')


if __name__=='__main__':asyncio.run(main())
