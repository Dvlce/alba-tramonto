"""Real selection formatting, persistence/undo/print and transparent formula pixels."""
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
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js','tramonto-math.js','tramonto-study.js','tramonto-tools.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Admin');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1440,'height':1000});page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible')
    await page.evaluate('''() => {const e=$('richEditor');e.innerHTML='<p>Prima <strong><mark style="background-color:#fff19c">testo scelto</mark></strong> dopo.</p><p>Seconda riga.</p>';e.dispatchEvent(new Event('input',{bubbles:true}));const r=document.createRange();r.selectNodeContents(e.querySelector('mark'));getSelection().removeAllRanges();getSelection().addRange(r);e.focus();}''')
    await page.locator('#selectionFontSize').fill('32');await page.locator('#applySelectionFontSize').click()
    assert await page.locator('#richEditor mark span').evaluate('e=>getComputedStyle(e).fontSize')=='32px'
    assert await page.locator('#richEditor strong').inner_text()=='testo scelto'
    assert await page.locator('#richEditor').evaluate('e=>getComputedStyle(e).fontSize')=='16px'
    assert await page.evaluate('getSelection().toString()')=='testo scelto'
    await page.evaluate('document.execCommand("undo")');assert await page.locator('#richEditor mark [style*="font-size"]').count()==0
    await page.evaluate('document.execCommand("redo")');assert await page.locator('#richEditor mark span').evaluate('e=>getComputedStyle(e).fontSize')=='32px'
    await page.locator('#pageSettingsButton').click();await page.locator('#noteFontSize').fill('20');await page.locator('#pageSettingsClose').click()
    assert await page.locator('#richEditor').evaluate('e=>getComputedStyle(e).fontSize')=='20px'
    assert await page.locator('#richEditor mark span').evaluate('e=>getComputedStyle(e).fontSize')=='32px'
    assert await page.evaluate('TramontoTools.saveDoc()')
    content=json.loads(store.rows('SELECT content FROM notes ORDER BY id LIMIT 1')[0]['content'])
    assert content['font_size']==20 and 'font-size: 32px;' in content['html'] and 'background-color: #fff19c;' in content['html']
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.locator('#richEditor mark span').evaluate('e=>getComputedStyle(e).fontSize')=='32px'
    await page.evaluate('''() => {const e=$('richEditor'),r=document.createRange();r.setStart(e.firstChild.firstChild,2);r.setEnd(e.lastChild.firstChild,7);getSelection().removeAllRanges();getSelection().addRange(r);e.focus();}''')
    await page.locator('#selectionFontSize').fill('24');await page.locator('#applySelectionFontSize').click()
    assert await page.locator('#richEditor').evaluate('e=>e.querySelectorAll("p").length')==2
    assert await page.locator('#richEditor mark span').evaluate('e=>getComputedStyle(e).fontSize')=='24px'
    assert await page.locator('#richEditor strong').inner_text()=='testo scelto'
    assert await page.evaluate('doc.content.font_size')==20
    before=await page.locator('#richEditor').inner_html()
    await page.evaluate('''() => {const r=document.createRange();r.selectNodeContents($('richEditor'));r.collapse(false);getSelection().removeAllRanges();getSelection().addRange(r);}''')
    await page.locator('#applySelectionFontSize').click();assert 'Seleziona prima' in await page.locator('#selectionFontSizeStatus').inner_text();assert await page.locator('#richEditor').inner_html()==before
    assert await page.evaluate('TramontoTools.saveDoc()')
    await page.locator('#printNote').click();assert await page.evaluate('TramontoWorkspace.preparePrint()')
    assert await page.locator('#printDocument .rich-editor [style*="font-size: 24px"]').count()>0
    await page.evaluate("TramontoWorkspace.cleanupPrint();document.querySelector('#printSettings').close()")
    await page.locator('[data-pane=math]').click();await page.locator('#formulaInput').fill(r'\frac{x^2}{3}=y');await page.locator('#addFormula').click();await page.locator('#richEditor img').wait_for(timeout=15000)
    async def pixels(index):
     return await page.locator('#richEditor img').nth(index).evaluate('''async img => {await img.decode();const c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;const ctx=c.getContext('2d');ctx.drawImage(img,0,0);const p=ctx.getImageData(0,0,c.width,c.height).data;return {corners:[p[3],p[(c.width-1)*4+3],p[(c.width*(c.height-1))*4+3],p[p.length-1]],ink:p.some((v,i)=>i%4===3&&v>0)};}''')
    result=await pixels(0);assert result['corners']==[0,0,0,0] and result['ink'],result
    await page.locator('#richEditor img').dblclick();await page.locator('#formulaInput').fill(r'\sqrt{x}=y');await page.locator('#addFormula').click();await page.locator('#pane-text').wait_for(state='visible');assert (await pixels(0))['corners']==[0,0,0,0]
    assert await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert (await pixels(0))['corners']==[0,0,0,0]
    await page.locator('[data-pane=draw]').click();await page.locator('#fontWorkshop summary').click();canvas=page.locator('#handFormulaCanvas');await canvas.scroll_into_view_if_needed();box=await canvas.bounding_box();await page.mouse.move(box['x']+50,box['y']+50);await page.mouse.down();await page.mouse.move(box['x']+170,box['y']+100,steps=12);await page.mouse.up();await page.locator('#handFormulaInsertText').click();await page.wait_for_function("() => document.querySelectorAll('#richEditor img').length===2");assert (await pixels(1))['corners']==[0,0,0,0]
    await page.locator('[data-pane=text]').click();await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert await page.locator('#selectionFontSize').is_visible()
    assert await page.evaluate('TramontoTools.saveDoc()');await browser.close()
  finally:await server.close();store.close()
  assert not errors,errors
 print('Text size and formulas OK: selected ranges, highlight/bold, undo/redo, persistence, print, mobile, transparent generated/edited/handwritten PNGs.')

if __name__=='__main__':asyncio.run(main())
