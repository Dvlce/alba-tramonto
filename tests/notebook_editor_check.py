"""Regressions for real notebook insertion, selection, formatting, print and expired access."""
import asyncio,json,shutil,sys,tempfile
from pathlib import Path
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

async def main():
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder)
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Admin');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1600,'height':1100});page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' and '403' not in m.text else None)
    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('#noteTitle').fill('Circuiti e funzioni');await page.locator('#notePaper').select_option('ruled');await page.locator('#richEditor').fill('Funzioni e circuiti');await page.locator('[data-format=formatBlock][data-value=h2]').click();assert await page.locator('#richEditor h2').count()==1;await page.locator('#richEditor').press('End');await page.locator('#richEditor').press('Enter');await page.locator('[data-format=formatBlock][data-value=p]').click();await page.locator('#richEditor').press_sequentially('Una formula inserita nel foglio, con dimensione e disposizione modificabili.');await page.evaluate('TramontoTools.saveDoc()')
    await page.locator('[data-pane=math]').click();await page.locator('#formulaInput').fill('\\int_0^1 x^2\\,dx=\\frac{1}{3}');await page.locator('#addFormula').click();await page.locator('#richEditor img').wait_for(timeout=15000);await page.locator('.image-selection').wait_for(state='visible');assert await page.locator('#richEditor img').evaluate('e=>e.complete&&e.naturalWidth>100&&e.naturalWidth/e.naturalHeight<10');handle=page.locator('.image-resize-handle');box=await handle.bounding_box();await page.mouse.move(box['x']+12,box['y']+12);await page.mouse.down();await page.mouse.move(box['x']-48,box['y']+12,steps=8);await page.mouse.up();assert int(await page.locator('#richEditor img').get_attribute('width'))<450;await page.locator('#inlineImageWidth').fill('240');await page.locator('#inlineImageWidth').dispatch_event('change');await page.locator('#inlineImageLayout').select_option('right');await page.get_by_role('button',name='↑ Sposta sopra').click();await page.get_by_role('button',name='↓ Sposta sotto').click();await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.locator('#richEditor img').get_attribute('width')=='240';assert await page.locator('#richEditor img').get_attribute('data-layout')=='right'
    await page.locator('#richEditor img').click();await page.wait_for_timeout(500);await page.locator('#richEditor img').screenshot(path=str(ROOT/'artifacts'/'tramonto-formula-v2.png'));(ROOT/'artifacts').mkdir(exist_ok=True);await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-editor-v2.png'),full_page=True)
    await page.emulate_media(media='print');await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-print-v2.png'),full_page=True);await page.pdf(path=str(ROOT/'artifacts'/'tramonto-page-v2.pdf'),prefer_css_page_size=True,print_background=True);assert len(__import__('re').findall(rb'/Type\s*/Page\b',(ROOT/'artifacts'/'tramonto-page-v2.pdf').read_bytes()))==1;await page.emulate_media(media='screen');await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.locator('#pageZoom').select_option('100');assert await page.locator('#a4Frame').evaluate('e=>e.scrollWidth>e.clientWidth');await page.locator('#pageZoom').select_option('fit');await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-editor-mobile-v2.png'),full_page=True);await page.set_viewport_size({'width':1600,'height':1100})
    await page.locator('#richEditor').fill('Modifica da conservare senza accesso');
    async def expired(route):await route.fulfill(status=403,content_type='application/json',body=json.dumps({'error':'scaduto','code':'auth_expired'}))
    await page.route('**/api/tramonto/notes/*',expired);assert not await page.evaluate('TramontoTools.saveDoc()');assert page.url.endswith('/tramonto');assert 'Modifica da conservare' in await page.locator('#richEditor').inner_text();assert 'Esporta' in await page.locator('#notesError').inner_text();await page.unroute('**/api/tramonto/notes/*',expired);await page.evaluate('TramontoTools.saveDoc()');assert await page.locator('#notesError').inner_text()=='';await browser.close()
  finally:await server.close();store.close()
  assert not errors,errors
 print('Notebook editor OK: formula raster insertion, width/wrap persisted, PDF generated, expired access preserves edits.')

if __name__=='__main__':asyncio.run(main())
