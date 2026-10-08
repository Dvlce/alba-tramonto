"""Browser regression for A4, inline images and isolated lab integration; a disposable database only."""
import asyncio,json,shutil,sys,tempfile,re,html
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.async_api import async_playwright
from aiohttp.test_utils import TestServer
from app import web_app
from config import Settings
from store import Store
from security import Keys,secret_file
from engine import Engine
from service import Service
from backups import Backups
from lab import Spice
from test_tramonto import PNG
async def main():
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder)
  for filename in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js'):shutil.copy2(ROOT/filename,root/filename)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,),allowed=(2,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Admin');store.register(2,'User');server=TestServer(web_app(service));errors=[]
  async def simulated(_self,prepared):
   await asyncio.sleep(.4);return {'engine':'test fixture','analysis':'op','x':[0],'series':[{'name':'P1','unit':'V','values':[2.5]}],'total_samples':1,'display_samples':1}
  with patch.object(Spice,'available',True),patch.object(Spice,'run',simulated):
   await server.start_server()
   try:
    async with async_playwright() as playwright:
     browser=await playwright.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(e.stack));await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('#noteTitle').fill('Quaderno principale');await page.locator('#notePaper').select_option('ruled');await page.locator('#richEditor').fill('Testo sulla prima riga');await page.evaluate('TramontoTools.saveDoc()');assert await page.locator('#a4Sheet').evaluate('e=>getComputedStyle(e).height')=='1123px';assert await page.locator('#richEditor').evaluate('e=>getComputedStyle(e).lineHeight')=='28px';assert 'A4' in await page.locator('#pageNumber').text_content()
     await page.locator('#inlineImageInput').set_input_files({'name':'foto.png','mimeType':'image/png','buffer':PNG});await page.locator('#richEditor img').wait_for();await page.locator('#richEditor img').click();await page.locator('#inlineImageWidth').fill('240');await page.locator('#inlineImageWidth').dispatch_event('change');await page.locator('#inlineImageLayout').select_option('right');await page.evaluate('TramontoTools.saveDoc()');content=json.loads(store.rows('SELECT content FROM notes ORDER BY id')[0]['content']);assert 'data-layout="right"' in content['html'];assert 'width="240"' in content['html']
     await page.locator('.insert-menu summary').click();await page.locator('#insertTable').click();assert await page.locator('#richEditor table tr').count()==4;await page.locator('#richEditor table td').first.click();await page.locator('#addTableRow').click();assert await page.locator('#richEditor table tr').count()==5
     await page.locator('.insert-menu summary').click();await page.locator('[data-pane=math]').click();await page.locator('#calcExpression').fill('x^2');await page.locator('#calculateDerivative').click();assert '2' in await page.locator('#calculusResult').text_content();await page.locator('#calculateIntegral').click();assert '0.333333' in await page.locator('#calculusResult').text_content();await page.locator('#plotGraph').click();await page.evaluate('TramontoLab.snapshot("plotSvg")');assert await page.locator('#richEditor img').count()==2
     await page.locator('[data-pane=network]').click();await page.locator('#networkExample').click();await page.locator('#networkPing').click();assert 'risposta ricevuta' in await page.locator('#networkResult').text_content();await page.locator('#subnetCalculate').click();assert '254' in await page.locator('#subnetResult').text_content();await page.locator('#networkCommand').fill('show ip interface brief');await page.locator('#networkCli button').click();assert '192.168.1.2' in await page.locator('#networkConsole').text_content();await page.evaluate('TramontoLab.snapshot("networkSvg")');assert await page.locator('#richEditor img').count()==3
     await page.locator('[data-pane=circuit]').click();await page.locator('#circuitExample').select_option('divider');await page.locator('#simulateCircuit').click();await page.wait_for_function('()=>document.querySelector("#simulationStatus").textContent.includes("completata")');assert '2.50000' in await page.locator('#simulationResult').text_content();assert await page.locator('[data-component]').count()==35
     await page.locator('[data-pane=text]').click();await page.evaluate('TramontoTools.saveDoc()');first=store.rows('SELECT id FROM notes')[0]['id'];await page.locator('#newNote').click();await page.wait_for_function('()=>doc.title!=="Quaderno principale"');await page.locator('#noteTitle').fill('Pagina lunga');await page.evaluate('()=>{const e=document.getElementById("richEditor");e.innerHTML=Array.from({length:100},(_,i)=>"<p>Riga numerata "+i+"</p>").join("");e.dispatchEvent(new InputEvent("input",{bubbles:true}));}');await page.wait_for_timeout(1600);await page.wait_for_function('()=>document.querySelector("#pageHint").textContent.includes("pagine A4 salvate")',timeout=10000);rows=store.rows('SELECT id,content FROM notes WHERE id>? ORDER BY id',(first,));assert len(rows)>=3;combined=html.unescape(re.sub('<[^>]+>','', ''.join(json.loads(row['content'])['html'] for row in rows)))
     for i in range(100):assert 'Riga numerata '+str(i) in combined
     for row in rows:
      await page.evaluate('(id)=>window.tramontoOpenPage(id)',row['id']);assert await page.locator('#richEditor').evaluate('e=>e.scrollHeight<=e.clientHeight+2')
     last=rows[-1]['id'];await page.evaluate('window.scrollTo(0,600)');await page.wait_for_timeout(1300);await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert str(last)==await page.evaluate('String(doc.id)');await page.wait_for_timeout(550);assert await page.evaluate('scrollY')>300
     await page.locator('#showCollection').click();await page.locator('.notebook-cover').first.wait_for();assert await page.locator('.notebook-cover').count()>=1;await page.locator('.notebook-cover').first.click();await page.locator('#noteEditor').wait_for(state='visible');await page.set_viewport_size({'width':390,'height':844});await page.locator('[data-pane=text]').click();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-word-mobile.png'),full_page=True);await page.set_viewport_size({'width':1440,'height':1100});await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-word.png'),full_page=True);await browser.close()
   finally:await server.close();store.close()
  assert not errors,errors
 print('Browser labs OK: A4 pagination/numbering, reading position, inline images/resize/wrap, tables, calculus, network ping/CIDR/CLI, SPICE results, snapshots, collection and mobile.')
if __name__=='__main__':asyncio.run(main())
