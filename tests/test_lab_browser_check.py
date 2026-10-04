"""Private/public boundaries, live input preservation and downloadable charts.

Uses a temporary database and fixture model outputs, never LLM inference.
"""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from aiohttp.test_utils import TestServer
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys,secret_file
from service import Service
from store import Store
from test_core import Model


async def main():
    from playwright.async_api import async_playwright
    (ROOT/'artifacts').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for name in ('web.html','web.css','web.js','notte.html','notte.css','notte.js',
                     'optimization.html','optimization.css','optimization.js'):
            shutil.copy2(ROOT/name,root/name)
        shutil.copytree(ROOT/'vendor',root/'vendor')
        (root/'docs').mkdir()
        for name in ('OPTIMIZATION_HISTORY.json','SSD_RUNTIME_RESULTS.json'):
            shutil.copy2(ROOT/'docs'/name,root/'docs'/name)
        settings=Settings(root=root,admins=(1,),allowed=(2,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'))
        service=Service(store,settings,keys,Engine(store,settings,Model()),Backups(store,settings));store.register(1,'Fixture');store.register(2,'Other')
        cookie,_=keys.create_session(1,True);server=TestServer(web_app(service));await server.start_server()
        service.core.inference.models=lambda: asyncio.sleep(0,result=[{'name':'qwen2.5-coder:7b','size':4683074048}])
        service.core.ssd.snapshot=lambda: {'ready':True,'models':['qwen2.5-coder:7b'],'running':False}
        async def fake_run(value):
            config=dict(value);samples=[{'backend':backend,'content':'42','status':'ok','first_token_ms':latency,'wall_ms':latency+100,'tokens_per_second':rate,'model':config['model']} for backend,latency,rate in [('normal',200,4),('optimized',100,5)]]
            store.execute('INSERT INTO core_lab_runs(config,status,result,created) VALUES(?,?,?,?)',(json.dumps(config),'ok',json.dumps({'samples':samples,'same_text':True,'same_tokens':None,'conditions':'Fixture timings, not a hardware benchmark.'}),1))
        service.core.test_lab.run=fake_run
        errors=[]
        try:
            async with async_playwright() as p:
                browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
                await context.add_cookies([{'name':'session','value':cookie,'url':str(server.make_url('/'))}]);page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(str(server.make_url('/notte')));await page.locator('#streamState').filter(has_text='In diretta').wait_for();await page.locator('#tab-lab').click();await page.locator('#labModel option').first.wait_for(state='attached')
                await page.locator('#labPrompt').fill('PRIVATE_UNPUBLISHED_MARKER');await page.locator('#labRun').click();await page.locator('#labRuns article').first.wait_for();assert await page.locator('#labRuns svg').count()==2
                assert await page.locator('#labPrompt').input_value()=='PRIVATE_UNPUBLISHED_MARKER';assert await page.locator('#labRuns').get_by_text('identità dei token non disponibile',exact=False).count()>0
                async with page.expect_download() as download: await page.get_by_role('button',name='Report con grafici').click()
                report=await download.value;path=await report.path();text=Path(path).read_text();assert '<svg' in text and 'PRIVATE_UNPUBLISHED_MARKER' in text
                await page.screenshot(path=str(ROOT/'artifacts/test-lab-desktop.png'),full_page=True)
                await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert await page.locator('#labPrompt').evaluate("e=>getComputedStyle(e).resize")=='none';await page.screenshot(path=str(ROOT/'artifacts/test-lab-mobile.png'),full_page=True)
                await page.goto(str(server.make_url('/optimization')));await page.locator('#language').select_option('it');await page.locator('[data-view=benchmarks]').click();await page.locator('#publicChart svg').wait_for();assert 'PRIVATE_UNPUBLISHED_MARKER' not in await page.content()
                await page.locator('#language').select_option('en');assert await page.get_by_role('heading',name='The measurements, including regressions.').count()==1
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth');await page.screenshot(path=str(ROOT/'artifacts/optimization-mobile.png'),full_page=True)
                public=await page.request.get(str(server.make_url('/optimization/data')));assert 'PRIVATE_UNPUBLISHED_MARKER' not in await public.text()
                await context.clear_cookies();private=await page.request.get(str(server.make_url('/api/notte/lab')));assert private.status==403
                assert not errors,errors;await browser.close()
        finally: await server.close();store.close()
    print('PASS: Test Lab, live input, native-friendly endpoints, private/public boundary, report SVG, IT/EN and mobile layout; fixture only.')

if __name__=='__main__':asyncio.run(main())
