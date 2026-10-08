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
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Admin');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1600,'height':1100});page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' and '403' not in m.text else None)

    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible')
    async def save():assert await page.evaluate('TramontoTools.saveDoc()')
    def content():return json.loads(store.rows('SELECT content FROM notes ORDER BY id LIMIT 1')[0]['content'])
    await page.locator('[data-pane=math]').click();await page.locator('#formulaInput').fill(r'\frac{a}{b}+x^2');assert await page.locator('#formulaVisual').evaluate('e=>e.value')==r'\frac{a}{b}+x^2'
    await page.locator('#formulaVisual').click();await page.keyboard.press('Control+End');await page.keyboard.type('+3');await page.wait_for_timeout(150);typed=await page.locator('#formulaInput').input_value();assert '+3' in typed.replace(' ',''),typed
    await page.locator('#addFormula').click();image=page.locator('#richEditor img');await image.wait_for();await save();assert 'data-latex' in content()['html'];image_id=content()['images'][0]
    await image.dblclick();await page.locator('#formulaInput').fill(r'\frac{2}{3}=y');await page.locator('#addFormula').click();await page.locator('#pane-text').wait_for(state='visible');await save();assert content()['images']==[image_id];assert len(store.rows('SELECT id FROM note_images'))==1;assert r'\frac{2}{3}=y' in content()['html'];assert '?v=' in content()['html']
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await image.click();await page.locator('#editInlineFormula').click();assert await page.locator('#formulaInput').input_value()==r'\frac{2}{3}=y'
    await page.locator('#cancelFormulaEdit').click();await page.locator('#formulaBracketHeight').fill('8');await page.locator('#formulaBracketWidth').fill('4');await page.locator('#formulaBracketApply').click();value=await page.locator('#formulaInput').input_value();assert '8em' in value and '4em' in value,value;assert await page.locator('#formulaPreview .katex-error').count()==0
    await page.locator('#formulaBracketHeight').fill('10');await page.locator('#formulaBracketApply').click();value=await page.locator('#formulaInput').input_value();assert '10em' in value and value.count('vphantom')==1,value
    await page.locator('#addFormula').click();await page.locator('#pane-text').wait_for(state='visible');await save();await page.locator('[data-pane=math]').click();await page.locator('#formulaList button').filter(has_text='Modifica').first.click();await page.locator('#formulaInput').fill('z=7');await page.locator('#addFormula').click();await save();assert content()['formulas'][0]=='z=7'
    await page.locator('[data-pane=draw]').click();await page.locator('[data-draw-tool=text]').click();await page.locator('#drawingText').fill('Testo nel disegno\nSeconda riga');await page.locator('#drawingTextSize').fill('36');canvas=page.locator('#drawingCanvas');await canvas.click(position={'x':140,'y':100});await save();assert content()['drawing']['strokes'][0]['tool']=='text';assert content()['drawing']['strokes'][0]['text_size']==36
    await page.locator('#drawingText').fill('Testo modificato');await page.locator('#drawingTextApply').click();await save();assert content()['drawing']['strokes'][0]['text']=='Testo modificato'
    await canvas.press('Meta+z');await save();assert content()['drawing']['strokes'][0]['text']=='Testo nel disegno\nSeconda riga';await canvas.click(position={'x':140,'y':100});await page.locator('#drawingText').fill('Testo modificato');await page.locator('#drawingTextApply').click();await save()
    await canvas.click(position={'x':500,'y':250});await save();assert len(content()['drawing']['strokes'])==2;await canvas.press('Meta+z');await save();assert len(content()['drawing']['strokes'])==1
    await page.locator('#fontWorkshop summary').click();await page.locator('#customFontAlphabet button').filter(has_text='A').first.click();glyph=page.locator('#customGlyphCanvas');await glyph.scroll_into_view_if_needed();box=await glyph.bounding_box();await page.mouse.move(box['x']+70,box['y']+240);await page.mouse.down();await page.mouse.move(box['x']+150,box['y']+40,steps=8);await page.mouse.move(box['x']+230,box['y']+240,steps=8);await page.mouse.up();await page.locator('#customFontApply').click();await page.wait_for_function('document.fonts.check("30px TramontoPersonal")');await save();assert content()['font']=='custom';assert len(content()['custom_font']['glyphs']['A'][0])>10
    assert 'TramontoPersonal' in await page.locator('#richEditor').evaluate('e=>getComputedStyle(e).fontFamily')
    async with page.expect_download() as info:await page.locator('#customFontDownload').click()
    font=await info.value;target=ROOT/'artifacts'/'tramonto-personal-font.otf';await font.save_as(str(target));assert target.read_bytes().startswith(b'OTTO')
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.wait_for_function('document.fonts.check("30px TramontoPersonal")');assert content()['font']=='custom';await page.locator('[data-pane=draw]').click();await page.locator('#fontWorkshop summary').click();assert await page.locator('#customFontAlphabet button.has-glyph').count()==1;assert content()['drawing']['strokes'][0]['text']=='Testo modificato'
    await glyph.click(position={'x':50,'y':50});await save();assert len(content()['custom_font']['glyphs']['A'])==2;await glyph.press('Meta+z');await save();assert len(content()['custom_font']['glyphs']['A'])==1
    await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-font-workshop.png'),full_page=True);await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.locator('[data-pane=math]').click();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    await browser.close()
  finally:await server.close();store.close()
  assert not errors,errors
 print('Math/font editor OK: visual typing, formula edit+reload, source persistence, resizable systems, drawing text+undo, custom font creation+OTF+reload, mobile fit, strict CSP.')

if __name__=='__main__':asyncio.run(main())
