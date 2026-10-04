"""Functional browser checks with a disposable database; never invokes an LLM."""
import asyncio
import base64
import json
import shutil
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys,secret_file
from service import Service
from store import Store
from test_tramonto import PNG

async def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js'): shutil.copy2(ROOT/name,root/name)
        shutil.copytree(ROOT/'vendor',root/'vendor')
        settings=Settings(root=root,admins=(1,),allowed=(2,)); store=Store(settings.data/'alba.sqlite3'); keys=Keys(store,secret_file(settings.data/'auth.key'))
        service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings)); store.register(1,'Andrea'); store.register(2,'Alice')
        username,password=keys.set_web_password(1,1,'admin'); server=TestServer(web_app(service)); await server.start_server(); errors=[]
        try:
            async with async_playwright() as p:
                browser=await p.chromium.launch(); context=await browser.new_context(viewport={'width':1440,'height':1100}); page=await context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' and '409' not in msg.text and '403' not in msg.text else None)
                await page.goto(str(server.make_url('/'))); await page.locator('#username').fill(username); await page.locator('#password').fill(password); await page.locator('#loginButton').click(); await page.locator('#dashboard').wait_for(state='visible')
                assert 'albicocca' in await page.locator('#mascotButton svg').get_attribute('aria-label')
                assert await page.locator('.leaf-stem').count()==1
                await page.locator('#appearanceSettings summary').click()
                for style in ('neo','glass','classic'):
                    await page.locator('#surfaceStyle').select_option(style); assert await page.evaluate('document.documentElement.dataset.style')==style
                await page.locator('#appearanceSettings summary').click()
                await page.locator('#devicesButton').click(); await page.locator('#deviceDialog').wait_for(state='visible'); await page.wait_for_function('()=>document.querySelector("#currentRemember").checked')
                await page.locator('#deviceLabel').fill('Computer di prova'); await page.locator('#deviceForm button').click(); await page.wait_for_function('()=>document.querySelector("#deviceList").textContent.includes("Computer di prova")')
                await page.locator('#closeDevices').click()
                await page.locator('#albaSymbol').click(); await page.locator('#tramontoLink').click(); await page.wait_for_url('**/tramonto'); await page.locator('#bookList button').wait_for()
                await page.locator('#newBookName').fill('Il mio quaderno di matematica'); await page.locator('#newBookForm button').click(); await page.wait_for_function('()=>document.querySelector("#bookList .active").textContent.includes("matematica")')
                await page.locator('#newNote').click(); await page.locator('#noteEditor').wait_for(state='visible'); await page.locator('#noteTitle').fill('Funzioni e circuiti')
                await page.locator('#noteList button').first.click(); await page.locator('#richEditor').fill('Seno e coseno, appunti della lezione.'); await page.locator('#noteFont').select_option('mono'); await page.locator('#notePaper').select_option('grid'); await page.locator('#noteSubject').select_option('matematica')
                await page.wait_for_function('()=>document.querySelector("#saveStatus").textContent.startsWith("Salvato")'); await page.reload(); await page.locator('#noteEditor').wait_for(state='visible')
                assert await page.locator('#noteTitle').input_value()=='Funzioni e circuiti'; assert await page.locator('#noteFont').input_value()=='mono'; assert 'Seno e coseno' in await page.locator('#richEditor').inner_text()
                await page.locator('[data-pane=math]').click(); await page.get_by_role('button',name='Limite',exact=True).click(); assert await page.locator('#formulaPreview .katex').count()==1
                await page.locator('#addFormula').click(); await page.locator('#formulaList .katex').wait_for(state='attached'); assert await page.locator('#richEditor img').count()==1; await page.locator('[data-pane=math]').click(); assert await page.locator('#formulaList .katex').count()==1
                await page.locator('#plotGraph').click(); assert await page.locator('#plotSvg [data-curve]').count()==2
                assert abs(await page.evaluate('TramontoTools.expressionFunction("sin(x)")(Math.PI/2)')-1)<1e-10
                for expression in ('import("bad")','x=2','[1,2,3]','x.constructor','evaluate("2")'):
                    assert await page.evaluate('(value)=>{try{TramontoTools.expressionFunction(value);return false}catch(_){return true}}',expression)
                await page.locator('#estimateLimit').click(); assert 'Stima dai campioni: 1' in await page.locator('#limitResult').inner_text()
                await page.locator('#limitExpression').fill('1/x'); await page.locator('#estimateLimit').click(); assert 'non suggeriscono' in await page.locator('#limitResult').inner_text()
                await page.locator('#limitExpression').fill('sin(x)/x'); await page.locator('#estimateLimit').click()
                async with page.expect_download() as download:
                    await page.locator('#exportGraph').click()
                assert (await download.value).suggested_filename=='grafico.svg'
                await page.locator('[data-pane=draw]').click(); canvas=page.locator('#drawingCanvas'); await canvas.scroll_into_view_if_needed(); box=await canvas.bounding_box()
                await page.mouse.move(box['x']+70,box['y']+70); await page.mouse.down(); await page.mouse.move(box['x']+190,box['y']+170,steps=15); await page.mouse.up()
                await page.evaluate('TramontoTools.saveDoc()'); assert len(json.loads(store.rows('SELECT content FROM notes')[0]['content'])['drawing']['strokes'])==1
                await page.locator('#undoDrawing').click(); await page.evaluate('TramontoTools.saveDoc()'); assert not json.loads(store.rows('SELECT content FROM notes')[0]['content'])['drawing']['strokes']
                await page.mouse.move(box['x']+70,box['y']+70); await page.mouse.down(); await page.mouse.move(box['x']+190,box['y']+170,steps=15); await page.mouse.up()
                await page.locator('[data-pane=circuit]').click(); svg=page.locator('#circuitSvg'); await svg.scroll_into_view_if_needed(); box=await svg.bounding_box()
                for kind,x in (('resistor',.25),('capacitor',.6)):
                    await page.locator('[data-component='+kind+']').click(); await svg.click(position={'x':box['width']*x,'y':box['height']*.35})
                assert await page.locator('#circuitSvg [data-component-id]').count()==2
                await page.locator('#rotateCircuit').click(); await page.locator('#componentValue').fill('47 nF'); await page.locator('#componentForm button').click()
                await page.locator('#wireCircuit').click(); await page.locator('#circuitSvg [data-component-id]').first.locator('[data-port="1"]').click(); await page.locator('#circuitSvg [data-component-id]').last.locator('[data-port="0"]').click()
                assert await page.locator('#circuitSvg path[data-wire]').count()==2
                await page.evaluate('TramontoTools.saveDoc()'); circuit=json.loads(store.rows('SELECT content FROM notes')[0]['content'])['circuit']; assert len(circuit['wires'])==1; assert circuit['components'][1]['rotation']==90
                await page.locator('[data-pane=images]').click(); await page.locator('#imageInput').set_input_files({'name':'figura.png','mimeType':'image/png','buffer':PNG}); await page.locator('.image-card img').last.wait_for(); await page.wait_for_function('()=>document.querySelector("#saveStatus").textContent.startsWith("Salvato")')
                assert len(store.rows('SELECT id FROM note_images'))==2; assert await page.locator('.image-card img').last.evaluate('(image)=>image.complete && image.naturalWidth===1')
                async with page.expect_download() as download:
                    await page.locator('#exportNote').click()
                path=await (await download.value).path(); exported=json.loads(Path(path).read_text()); assert exported['format']=='tramonto-note-v1'; assert len(exported['images'])==2; assert len(exported['content']['drawing']['strokes'])==1
                await page.evaluate('window.print=()=>{window.didPrint=true}'); await page.locator('#printNote').click(); assert await page.evaluate('window.didPrint')
                for style in ('neo','glass'):
                    await page.locator('#notesStyle').select_option(style); await page.locator('#notesTheme').select_option('dark'); await page.wait_for_timeout(550); assert (await page.locator('.notes-workspace').bounding_box())['width']>950; await page.screenshot(path=str(ROOT/'artifacts'/('tramonto-'+style+'.png')),full_page=True)
                await page.reload(); await page.locator('#noteEditor').wait_for(state='visible'); assert await page.evaluate('document.documentElement.dataset.style')=='glass'; assert await page.locator('#notePaper').input_value()=='grid'; assert await page.locator('#formulaList .katex').count()==1
                await page.set_viewport_size({'width':390,'height':844}); assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'); await page.locator('[data-pane=math]').click(); assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'); await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-mobile.png'),full_page=True)
                state=await context.storage_state(); await context.close()
                remembered=await browser.new_context(storage_state=state); page=await remembered.new_page(); await page.goto(str(server.make_url('/tramonto'))); await page.locator('#noteEditor').wait_for(state='visible'); assert await page.locator('#noteTitle').input_value()=='Funzioni e circuiti'
                await remembered.close()
                user=await browser.new_context(); page=await user.new_page(); await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(2,2,'web')); await page.locator('#dashboard').wait_for(state='visible'); await page.locator('#albaSymbol').click(); assert not await page.locator('#tramontoLink').is_visible()
                response=await page.goto(str(server.make_url('/tramonto'))); assert response.status==403
                await browser.close()
        finally: await server.close(); store.close()
        assert not errors,errors
    print('Tramonto browser OK: admin permissions, portal, apricot, three styles, remembered browser, notebooks/autosave, KaTeX, sine/cosine, numeric limits, expression sandbox, drawing/undo, circuits/wires/rotation, local images, JSON/SVG/print, reload, mobile.')

if __name__=='__main__': asyncio.run(main())
