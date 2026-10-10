"""Regressions for real notebook insertion, selection, formatting, print and expired access."""
import asyncio,base64,json,shutil,sys,tempfile
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
    browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1600,'height':1100});page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' and '403' not in m.text else None)

    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible')
    async def save():assert await page.evaluate('TramontoTools.saveDoc()')
    def content():return json.loads(store.rows('SELECT content FROM notes ORDER BY id LIMIT 1')[0]['content'])
    await page.locator('[data-pane=draw]').click();await page.locator('#fontWorkshop summary').click()
    glyph=page.locator('#customGlyphCanvas')
    for char in ['x','2','α','+']:
     await page.locator('#customFontCharacter').fill(char);await glyph.scroll_into_view_if_needed();box=await glyph.bounding_box()
     await page.mouse.move(box['x']+70,box['y']+220);await page.mouse.down();await page.mouse.move(box['x']+130,box['y']+70,steps=8);await page.mouse.move(box['x']+200,box['y']+220,steps=8);await page.mouse.up()
    await page.locator('#customFontApply').click();await page.evaluate('TramontoFont.ready()');await save()
    await page.locator('[data-pane=math]').click();await page.locator('#formulaInput').fill(r'\frac{x^2+\alpha}{B}+\sqrt{x}')
    async def fonts():
     return await page.locator('#formulaPreview').evaluate("""e=>[...e.querySelectorAll('.katex-html span')].filter(s=>!s.children.length&&s.textContent.trim()).map(s=>({text:s.textContent,font:getComputedStyle(s).fontFamily,style:getComputedStyle(s).fontStyle}))""")
    styles=await fonts();assert all('TramontoPersonal' in s['font'] for s in styles if s['text'] in ['x','2','α','+']),styles
    assert all('TramontoPersonal' not in s['font'] for s in styles if s['text']=='B'),styles
    assert await page.locator('#formulaPreview .frac-line').count()==1;assert await page.locator('#formulaPreview svg').count()>0
    await page.locator('#pageSettingsButton').click();await page.locator('#noteFont').select_option('serif');await page.locator('#pageSettingsClose').click();assert all('TramontoPersonal' not in s['font'] for s in await fonts())
    await page.locator('#addFormula').click();await save();standard=await page.locator('#richEditor img').get_attribute('src');standard_bytes=store.rows('SELECT data FROM note_images ORDER BY id LIMIT 1')[0]['data']
    await page.locator('[data-pane=math]').click();await page.locator('#pageSettingsButton').click();await page.locator('#noteFont').select_option('custom');await page.locator('#pageSettingsClose').click();await page.locator('#formulaApplyHandwriting').click()
    await page.wait_for_function('()=>document.querySelector("#formulaEditStatus").textContent.includes("1 / 1 formule aggiornate")')
    assert standard_bytes!=store.rows('SELECT data FROM note_images ORDER BY id LIMIT 1')[0]['data']
    await page.locator('[data-pane=text]').click();await page.locator('#richEditor img').dblclick();await page.evaluate('TramontoFont.ready()')
    # Record the real offscreen snapshot's styles, while still rendering and uploading its PNG.
    await page.evaluate("""()=>{const render=window.html2canvas;window.html2canvas=async(host,options)=>{window.capturedMath=[...host.querySelectorAll('.katex-html span')].filter(s=>!s.children.length&&s.textContent==='x').map(s=>getComputedStyle(s).fontFamily);return render(host,options)}}""")
    await page.locator('#addFormula').click();await page.locator('#pane-text').wait_for(state='visible');await save();assert await page.evaluate('capturedMath') and all('TramontoPersonal' in s for s in await page.evaluate('capturedMath'))
    personal=await page.locator('#richEditor img').get_attribute('src');personal_bytes=store.rows('SELECT data FROM note_images ORDER BY id LIMIT 1')[0]['data'];assert standard_bytes!=personal_bytes,(standard,personal,len(standard_bytes),standard_bytes[:80],await fonts())
    assert len(content()['images'])==1 and 'data-latex' in content()['html']
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.evaluate('TramontoFont.ready()');await page.locator('[data-pane=math]').click()
    assert await page.locator('#formulaList span').filter(has_text='x').count()>0
    assert await page.locator('#formulaList .katex-html').evaluate("""e=>[...e.querySelectorAll('span')].filter(s=>!s.children.length&&s.textContent==='x').every(s=>getComputedStyle(s).fontFamily.includes('TramontoPersonal'))""")
    await page.locator('#formulaList button').filter(has_text='Modifica').first.click();assert any('TramontoPersonal' in s['font'] for s in await fonts())
    await page.wait_for_timeout(900);await page.locator('#formulaPreview').screenshot(path=str(ROOT/'artifacts'/'tramonto-handwritten-math.png'))
    await page.locator('details[data-math-tool=manual]>summary').click()
    assert await page.locator('#pane-math details[open]').count()==1
    await page.locator('#signCriticalValues').fill('-1; 2');await page.locator('#signBuildTable').click()
    for i,value in enumerate(['−','0','+','+','+']):await page.locator(f'#manualSignEditor select[data-row="0"][data-column="{i}"]').select_option(value)
    await page.locator('#signAddFactor').click()
    await page.locator('#manualSignEditor td:first-child input').nth(0).fill('x + 1')
    await page.locator('#manualSignEditor td:first-child input').nth(1).fill('x − 2')
    await page.locator('#manualSignEditor td:first-child select').nth(1).select_option('denominator')
    for i,value in enumerate(['−','−','−','0','+']):await page.locator(f'#manualSignEditor select[data-row="1"][data-column="{i}"]').select_option(value)
    assert await page.locator('#manualSignResult td').all_text_contents()==['+','0','−','×','+']
    await page.locator('#manualSignEditor td:first-child select').nth(1).select_option('factor')
    assert await page.locator('#manualSignResult td').all_text_contents()==['+','0','−','0','+']
    await page.locator('#manualSignEditor td:first-child select').nth(1).select_option('denominator')
    await page.locator('#signCriticalValues').fill('2; -1');await page.locator('#signBuildTable').click();assert 'ordine crescente' in await page.locator('#manualSignMessage').inner_text()
    await page.locator('#signCriticalValues').fill('x; 2');await page.locator('#signBuildTable').click();assert 'senza x' in await page.locator('#manualSignMessage').inner_text()
    await page.locator('#signCriticalValues').fill('-1; 2');await page.locator('#signBuildTable').click()
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.evaluate('TramontoFont.ready()');await page.locator('[data-pane=math]').click();await page.locator('details[data-math-tool=manual]>summary').click()
    assert await page.locator('#manualSignResult td').all_text_contents()==['+','0','−','×','+']
    await page.evaluate("""()=>{const embed=TramontoFont.embedSvgFont;TramontoFont.embedSvgFont=svg=>{embed(svg);window.embeddedHandwriting=svg.querySelector('style')?.textContent.includes('data:font/otf;base64,')}}""")
    await page.locator('#insertManualSign').click();await page.locator('#pane-text').wait_for(state='visible');await save();assert len(content()['images'])==2
    assert await page.evaluate('embeddedHandwriting')
    chart=store.rows('SELECT data FROM note_images ORDER BY id DESC LIMIT 1')[0]['data'];assert chart.startswith(b'\x89PNG') and len(chart)>2000
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.locator('#richEditor img').count()==2
    await page.locator('[data-pane=math]').click();await page.locator('details[data-math-tool=manual]>summary').click();await page.wait_for_timeout(900)
    await page.locator('#pane-math').screenshot(path=str(ROOT/'artifacts'/'tramonto-compact-math.png'))
    await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    await page.locator('#pane-math').screenshot(path=str(ROOT/'artifacts'/'tramonto-compact-math-mobile.png'))
    await browser.close()
  finally:await server.close();store.close()
  assert not errors,errors
 print('Handwritten math OK: drawn Latin, Greek, digits, symbol fallback, fractions, roots, switching font, real PNG replacement, editing and reload, manual factors+denominator+domain exclusions+local reload+PNG insertion, compact panels and mobile fit.')

if __name__=='__main__':asyncio.run(main())
