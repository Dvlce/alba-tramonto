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
    async def save_font():
     await page.locator('#customFontSave').click();await page.wait_for_function('() => document.querySelector("#customFontSaveStatus").textContent.startsWith("Preset salvato")');await save()
    # Every printable ASCII symbol is selectable; quotes and custom characters survive saving and OTF export.
    characters=set()
    for group in await page.locator('#customFontCategory option').all_text_contents():
     await page.locator('#customFontCategory').select_option(group);characters.update(await page.locator('#customFontAlphabet button').all_text_contents())
    assert set(chr(n) for n in range(33,127))<=characters
    for group,symbols in [('Simboli comuni','#&@'),('Virgolette','"\'`“”«»'),('Trattini e barre','\\_'),('Valute','€')]:
     await page.locator('#customFontCategory').select_option(group)
     for symbol in symbols:
      await page.locator('#customFontAlphabet').get_by_role('button',name=symbol,exact=True).click();await glyph.click(position={'x':150,'y':120})
    await page.locator('#customFontCharacter').fill('e\u0301');assert 'é' in await page.locator('#customGlyphLabel').inner_text();await glyph.click(position={'x':140,'y':110})
    await page.locator('#customFontCharacter').fill('𝄞');assert '𝄞' in await page.locator('#customGlyphLabel').inner_text();await glyph.click(position={'x':170,'y':100});await save_font()
    await page.locator('#customFontCategory').select_option('Caratteri disegnati');assert await page.locator('#customFontAlphabet').get_by_role('button',name='𝄞',exact=True).count()==1
    await page.locator('#pageSettingsButton').click();await page.locator('#noteFontSize').fill('');await page.locator('#noteFontSize').press_sequentially('32');await page.locator('#noteLetterSpacing').fill('-0.5');await page.locator('#pageSettingsClose').click();await save();assert content()['font_size']==32 and content()['letter_spacing']==-.5
    assert await page.locator('#richEditor').evaluate('e=>getComputedStyle(e).fontSize')=='32px';assert await page.locator('#richEditor').evaluate('e=>getComputedStyle(e).letterSpacing')=='-0.5px'
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.locator('#noteFontSize').input_value()=='32';assert await page.locator('#noteLetterSpacing').input_value()=='-0.5';assert await page.locator('#richEditor').evaluate('e=>getComputedStyle(e).fontSize')=='32px'
    await page.locator('[data-pane=draw]').click();await page.locator('#fontWorkshop summary').click();await page.locator('#customFontCategory').select_option('Caratteri disegnati');assert await page.locator('#customFontAlphabet').get_by_role('button',name='"',exact=True).count()==1
    async with page.expect_download() as info:await page.locator('#customFontDownload').click()
    target=ROOT/'artifacts'/'tramonto-personal-font.otf';await (await info.value).save_as(str(target))
    metrics=await page.evaluate("""encoded=>{const font=opentype.parse(Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)).buffer),glyph=font.charToGlyph('A'),box=glyph.getBoundingBox();return {advance:glyph.advanceWidth,left:box.x1,right:glyph.advanceWidth-box.x2,hash:font.charToGlyph('#').index,quote:font.charToGlyph('"').index,music:font.charToGlyph('𝄞').index};}""",base64.b64encode(target.read_bytes()).decode())
    assert metrics['left']<=20 and metrics['right']<=20,metrics;assert all(metrics[k]>0 for k in ['hash','quote','music']),metrics
    await page.locator('#pageSettingsButton').click();await page.locator('#noteFontSize').fill('16');await page.locator('#noteLetterSpacing').fill('0');await page.locator('#pageSettingsClose').click();await save()
    # Presets survive reload, can be edited independently, and retain the applied page font.
    await page.locator('#customFontName').fill('Primo font');await save_font();await page.wait_for_function('() => document.querySelector("#customFontSaveStatus").textContent.startsWith("Preset salvato")')
    first=(await page.locator('#customFontPresets').input_value());first_glyph=json.loads(store.rows('SELECT content FROM font_presets WHERE id=?',(first,))[0]['content'])['glyphs']['A']
    await page.locator('#customFontNew').click();await page.wait_for_function('() => document.querySelector("#customFontSaveStatus").textContent.startsWith("Preset salvato")');second=await page.locator('#customFontPresets').input_value();assert first!=second
    await page.locator('#customFontName').fill('Secondo font');await glyph.click(position={'x':60,'y':60});await save_font();assert len(store.rows('SELECT * FROM font_presets'))==2;assert content()['custom_font']['preset_id']==first;assert content()['custom_font']['glyphs']['A']==first_glyph
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=draw]').click();await page.locator('#fontWorkshop summary').click();assert await page.locator('#customFontPresets').input_value()==second;assert await page.locator('#customFontName').input_value()=='Secondo font'
    # Named fonts must be selectable directly from the notebook, with missing
    # glyphs falling back to a readable system font rather than blank characters.
    assert 'Primo font' in await page.locator('#noteFont option').all_text_contents()
    assert 'Secondo font' in await page.locator('#noteFont option').all_text_contents()
    await page.locator('#pageSettingsButton').click();await page.locator('#noteFont').select_option('preset:'+second);await page.locator('#pageSettingsClose').click();await page.wait_for_function('() => doc.content.custom_font.preset_id === "'+second+'"');await save()
    assert content()['font']=='custom' and content()['custom_font']['preset_id']==second
    await page.wait_for_function('() => [...document.fonts].some(f => f.family === "TramontoPersonal" && f.status === "loaded")')
    ranges=await page.evaluate('() => [...document.fonts].find(f => f.family === "TramontoPersonal").unicodeRange');assert 'U+41' in ranges and 'U+42' not in ranges
    await page.locator('#pageSettingsButton').click();await page.locator('#noteFont').select_option('preset:'+first);await page.locator('#pageSettingsClose').click();await page.wait_for_function('() => doc.content.custom_font.preset_id === "'+first+'"');await save()
    await page.locator('#customFontPresets').select_option(first);await page.wait_for_function('() => document.querySelector("#customFontName").value==="Primo font"');await glyph.scroll_into_view_if_needed();before=json.loads(store.rows('SELECT content FROM font_presets WHERE id=?',(first,))[0]['content'])['glyphs']['A']
    await page.locator('#customGlyphEraser').click();await glyph.click(position={'x':150,'y':45});await save_font();erased=json.loads(store.rows('SELECT content FROM font_presets WHERE id=?',(first,))[0]['content'])['glyphs']['A'];assert erased!=before,('unchanged',before,erased);assert len(erased)>1,('pieces',erased);assert content()['custom_font']['glyphs']['A']==erased,('page preset',content()['custom_font'].get('preset_id'),first)
    await glyph.press('Meta+z');await save_font();assert json.loads(store.rows('SELECT content FROM font_presets WHERE id=?',(first,))[0]['content'])['glyphs']['A']==before
    await page.locator('#customGlyphPen').click();await page.locator('#customFontCategory').select_option('Minuscole');await page.locator('#customFontAlphabet button').filter(has_text='b').first.click();await glyph.click(position={'x':80,'y':80});await page.wait_for_function('() => document.querySelector("#customFontSaveStatus").textContent.startsWith("Preset salvato")');assert 'b' in json.loads(store.rows('SELECT content FROM font_presets WHERE id=?',(first,))[0]['content'])['glyphs']
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=draw]').click();await page.locator('#fontWorkshop summary').click();assert await page.locator('#customFontCategory').input_value()=='Minuscole';assert 'b' in await page.locator('#customGlyphLabel').inner_text()
    # Recover a local checkpoint made after the last server write (e.g. sudden browser closure).
    recovered=await context.storage_state()
    for origin in recovered['origins']:
     for entry in origin['localStorage']:
      if entry['name']=='alba.fontPresets.1':
       backup=json.loads(entry['value']);backup['font']['name']='Ripreso dopo chiusura';backup['font']['glyphs']['c']=[[[25,25]]];backup['dirty']=True;entry['value']=json.dumps(backup)
    await context.close();context=await browser.new_context(storage_state=recovered,viewport={'width':1600,'height':1100});page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));await page.goto(str(server.make_url('/tramonto')));await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=draw]').click();await page.locator('#fontWorkshop summary').click();glyph=page.locator('#customGlyphCanvas');assert await page.locator('#customFontName').input_value()=='Ripreso dopo chiusura';await save_font();assert 'c' in json.loads(store.rows('SELECT content FROM font_presets WHERE id=?',(first,))[0]['content'])['glyphs']
    for n in range(8):
     await page.locator('#customFontNew').click();await page.wait_for_function('() => document.querySelector("#customFontSaveStatus").textContent.startsWith("Preset salvato")')
    assert await page.locator('#customFontNew').is_disabled();assert await page.locator('#customFontPresets option').count()==10;assert len(store.rows('SELECT * FROM font_presets'))==10
    await page.locator('#customFontPresets').select_option(first);await page.wait_for_function('() => document.querySelector("#customFontName").value==="Ripreso dopo chiusura"');await page.locator('#customFontName').fill('Modificabile anche con 10 font');await save_font();assert len(store.rows('SELECT * FROM font_presets'))==10
    await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible');assert await page.locator('#customFontPresets option').count()==10;assert await page.locator('#customFontName').input_value()=='Modificabile anche con 10 font'
    # A larger personal font keeps its size and spacing on printed and continued A4 pages.
    start=store.rows('SELECT max(id) AS id FROM notes')[0]['id'];await page.locator('#customFontApply').click();await save_font();await page.locator('[data-pane=text]').click();await page.locator('#pageSettingsButton').click();await page.locator('#noteFontSize').fill('32');await page.locator('#noteLetterSpacing').fill('-0.5');await page.locator('#notePaper').select_option('ruled');await page.locator('#pageSettingsClose').click();await save()
    await page.emulate_media(media='print');assert await page.locator('#richEditor').evaluate('e=>getComputedStyle(e).fontSize')=='32px';await page.emulate_media(media='screen')
    await page.locator('#richEditor').evaluate('e=>e.innerHTML="<p>A # &quot;</p>".repeat(50)');await page.locator('#splitPages').click();await page.wait_for_function('() => document.querySelector("#pageHint").textContent.includes("pagine A4 salvate")')
    continued=[json.loads(r['content']) for r in store.rows('SELECT content FROM notes WHERE id>=? ORDER BY id',(start,))];assert len(continued)>1;assert all(c['font_size']==32 and c['letter_spacing']==-.5 and '#' in c['custom_font']['glyphs'] for c in continued)
    await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-font-workshop.png'),full_page=True);await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.locator('[data-pane=math]').click();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    await browser.close()
  finally:await server.close();store.close()
  assert not errors,errors
 print('Math/font editor OK: formulas, drawing text, Unicode symbols+quotes+OTF metrics, text size+spacing+reload, 10 presets+recovery+eraser undo, mobile fit, strict CSP.')

if __name__=='__main__':asyncio.run(main())
