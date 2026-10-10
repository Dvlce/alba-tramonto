"""Real desktop/mobile layout, ruled font metrics and nondestructive notebook print."""
import asyncio,json,re,shutil,sys,tempfile
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
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js','tramonto-math.js','tramonto-study.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Admin');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':900});page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('#noteTitle').fill('Appunti ordinati');await page.locator('#richEditor').fill('Prima riga\nSeconda riga\nTerza riga');await page.locator('#pageSettingsButton').click();await page.locator('#notePaper').select_option('ruled');await page.locator('#noteFontSize').fill('24');await page.locator('#noteFontSize').dispatch_event('change');await page.locator('#pageSettingsClose').click();await page.evaluate('TramontoTools.saveDoc()');await page.wait_for_timeout(200)
    for width,height in [(1440,900),(1024,768),(390,844),(360,640)]:
     await page.set_viewport_size({'width':width,'height':height});await page.wait_for_timeout(200)
     geometry=await page.evaluate("()=>{const r=$('richEditor').getBoundingClientRect(),n=document.querySelector('.page-navigation').getBoundingClientRect();return {top:r.top,bottom:n.bottom,width:document.documentElement.scrollWidth,viewport:innerWidth,scroll:scrollY,line:getComputedStyle($('richEditor')).lineHeight,rule:getComputedStyle($('richEditor')).backgroundSize};}")
     assert geometry['top']<310,geometry
     assert geometry['bottom']<=height,geometry
     assert geometry['width']<=width,geometry
     assert geometry['scroll']==0,geometry
     assert geometry['line']=='42px' and geometry['rule']=='100% 42px',geometry
     await page.screenshot(path=str(ROOT/'artifacts'/f'tramonto-workspace-{width}.png'))
    await page.locator('#writingFocus').click();assert await page.locator('#richEditor').evaluate('e=>e.getBoundingClientRect().width')>250;assert await page.locator('#richEditor').evaluate('e=>e.getBoundingClientRect().top')<100;await page.keyboard.press('Escape')
    await page.set_viewport_size({'width':1440,'height':900});first=await page.evaluate('doc.id');await page.locator('#insertPageAfter').click();await page.wait_for_function('(id)=>doc.id!==id&&!opening',arg=first);await page.locator('#noteTitle').fill('Seconda pagina');await page.locator('#richEditor').fill('CONTENUTO DELLA SECONDA PAGINA');await page.evaluate('TramontoTools.saveDoc()');await page.locator('#pageJump').select_option(str(first));await page.wait_for_function('(id)=>doc.id===id&&!opening',arg=first)
    before=await page.evaluate("async()=>{const list=(await api('/api/tramonto/notes?notebook='+bookId)).notes;let out=[];for(const n of list)out.push(await api('/api/tramonto/notes/'+n.id));return out;}")
    await page.locator('#printNote').click();await page.locator('#printScope').select_option('notebook');await page.locator('#printStyle').select_option('study');await page.locator('#printPaper').select_option('ruled');await page.locator('#printTitle').uncheck();assert await page.evaluate('TramontoWorkspace.preparePrint()');assert await page.locator('#printDocument .printed-page').count()==2;assert await page.locator('#printDocument .sheet-title').count()==0
    await page.locator('#printSettingsClose').click();await page.evaluate("document.body.classList.add('printing-snapshot')");await page.emulate_media(media='print');pdf=await page.pdf(path=str(ROOT/'artifacts'/'tramonto-quaderno-studio.pdf'),prefer_css_page_size=True,print_background=True);assert len(re.findall(rb'/Type\s*/Page\b',pdf))==2;await page.emulate_media(media='screen');await page.evaluate('TramontoWorkspace.cleanupPrint()')
    after=await page.evaluate("async()=>{const list=(await api('/api/tramonto/notes?notebook='+bookId)).notes;let out=[];for(const n of list)out.push(await api('/api/tramonto/notes/'+n.id));return out;}");assert before==after,'Printing modified saved notebook'
    # Saving another edit must not pull the reader back to the top of a page.
    await page.evaluate("document.querySelector('.editor-desk').scrollTop=300");await page.locator('#noteTitle').fill('Titolo aggiornato');await page.evaluate('TramontoTools.saveDoc()');assert await page.evaluate("document.querySelector('.editor-desk').scrollTop")>200;await page.wait_for_timeout(800);position=await page.evaluate("async()=>(await api('/api/tramonto/workspace')).scroll_y");assert position>200;await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.wait_for_timeout(500);assert await page.evaluate("document.querySelector('.editor-desk').scrollTop")>200
    await page.evaluate("async()=>api('/api/tramonto/notes','POST',{notebook_id:bookId,title:'Pagina densa',content:{font:'serif',font_size:8,paper:'plain',html:'<p>'+('parola '.repeat(850))+'FINE_STAMPA</p>'}})")
    await page.locator('#printNote').click();await page.locator('#printScope').select_option('notebook');await page.locator('#printStyle').select_option('study');assert await page.evaluate('TramontoWorkspace.preparePrint()');assert await page.locator('#printDocument .printed-page').count()>3;assert 'FINE_STAMPA' in await page.locator('#printDocument').text_content();await page.locator('#printSettingsClose').click();await page.evaluate('TramontoWorkspace.cleanupPrint()')
    await page.emulate_media(reduced_motion='reduce');assert await page.locator('#a4Frame').evaluate('e=>getComputedStyle(e).animationName')=='none';assert not errors,errors;await browser.close()
  finally:await server.close();store.close()
 print('Workspace OK: 4 viewport sizes, immediately visible writing, page navigation, ruled font metrics, focus, two-page PDF, preserved data and scroll.')

if __name__=='__main__':asyncio.run(main())
