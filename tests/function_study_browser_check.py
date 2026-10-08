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
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js','tramonto-math.js','tramonto-study.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Admin');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1600,'height':1100});page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' and '403' not in m.text else None)

    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible')
    async def save():assert await page.evaluate('TramontoTools.saveDoc()')
    def content():return json.loads(store.rows('SELECT content FROM notes ORDER BY id LIMIT 1')[0]['content'])
    expression=r'\colorbox{white}{$ y=\frac{\sqrt{x-3}}{\sqrt{x^2-1}} $}'
    await page.locator('[data-pane=math]').click();await page.locator('#formulaInput').fill(expression);await page.locator('#formulaToGraph').click()
    assert await page.locator('#studyDomain').inner_text()=='[3; +∞)'
    assert await page.locator('#studyZeros').inner_text()=='3'
    assert await page.locator('#studyQuadrants').inner_text()=='I'
    assert len(await page.locator('#plotSvg [data-curve="0"]').get_attribute('d'))>100
    assert 'NaN' not in await page.locator('#plotSvg').inner_html()
    assert await page.evaluate('Number(document.querySelector("#yMax").value)>0.3')
    await page.locator('#plotExpressions').fill(expression);await page.locator('#plotGraph').click();await save();assert content()['graph']['expressions']==['((sqrt(x-3))/(sqrt(x^2-1)))']
    await page.locator('#graphAreaFrom').fill('3');await page.locator('#graphAreaTo').fill('6');await page.locator('#graphShadeArea').check();await page.locator('#graphDerivative').check()
    assert await page.locator('#plotSvg [data-shaded-area]').count()>0
    assert await page.locator('#plotSvg [data-derivative]').count()==1
    assert '0.763' in await page.locator('#studyArea').inner_text()
    await save();assert content()['graph']['study']=={'show_area':True,'show_derivative':True,'area_from':3,'area_to':6}
    await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-function-study.png'),full_page=True)
    await page.locator('#insertGraphNotebook').click();await page.locator('#richEditor img').wait_for();await save();assert len(content()['images'])==1
    await page.locator('[data-pane=math]').click();await page.locator('#insertFunctionStudy').click();await save();assert 'Dominio reale: [3; +∞)' in content()['html'];assert 'Area geometrica' not in content()['html'] or '0.763' in content()['html']
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.locator('#richEditor img').count()==1
    await page.locator('[data-pane=math]').click();assert await page.locator('#graphShadeArea').is_checked();assert await page.locator('#graphDerivative').is_checked();assert await page.locator('#studyDomain').inner_text()=='[3; +∞)'
    # Preserve centering on root text and headings through sanitizer/reload.
    await page.locator('[data-pane=text]').click();await page.locator('#richEditor').evaluate("e=>{e.innerHTML='Titolo da centrare';e.dispatchEvent(new Event('input',{bubbles:true}));e.focus();const r=document.createRange();r.selectNodeContents(e);const s=getSelection();s.removeAllRanges();s.addRange(r);document.dispatchEvent(new Event('selectionchange'));}")
    await page.locator('[data-format=justifyCenter]').click();await save();assert 'align="center"' in content()['html'],content()['html'];assert 'text-align' not in content()['html']
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.locator('#richEditor [align=center]').evaluate('e=>getComputedStyle(e).textAlign')=='center'
    await page.locator('#richEditor').evaluate("e=>{e.innerHTML='<h2>Intestazione</h2>';e.dispatchEvent(new Event('input',{bubbles:true}));e.focus();const r=document.createRange();r.selectNodeContents(e.firstChild);const s=getSelection();s.removeAllRanges();s.addRange(r);document.dispatchEvent(new Event('selectionchange'));}")
    await page.locator('[data-format=justifyCenter]').click();await save();assert '<h2 align="center">' in content()['html']
    # Math facts, singularities and expression sandbox on actual browser mathjs.
    results=await page.evaluate(r"""()=>{const study=s=>TramontoMath.study(s,expressionFunction(s),-10,10);const a=study('x^2-4'),b=study('1/(x-0.1234)'),c=study('sqrt(-x^2)'),d=study('log(x)'),e=study('1/sin(x)');let pole=false,unsafe=0;try{TramontoMath.integrate(expressionFunction('1/(x-0.1234)'),0,1,b.allowed)}catch(_){pole=true}for(const x of ['x=3','import("x")','x.constructor','[1,2]','evaluate("x")'])try{expressionFunction(x)}catch(_){unsafe++}return {parabola:{domain:a.domain,zeros:a.zeros,signs:a.signs},pole,unsafe,singleton:c.domain,log:d.domain,unknown:e.domain,sampled:TramontoMath.sampledRoots(expressionFunction('1/(x-0.1234)'),-1,1)}}""")
    assert results['parabola']['domain']=='ℝ';assert results['parabola']['zeros']==[-2,2];assert {s['sign'] for s in results['parabola']['signs']}=={'+','−'}
    assert results['pole'] and results['unsafe']==5 and results['sampled']==[],results
    assert results['singleton']=='{0}' and results['log']=='(0; +∞)' and 'sin(x) ≠ 0' in results['unknown'],results
    # Separate each glyph and keep Greek, digits and handmade formulas after save.
    await page.locator('[data-pane=draw]').click();await page.locator('#fontWorkshop summary').click();await page.locator('#customFontCategory').select_option('Numeri');await page.locator('#customFontAlphabet button').get_by_text('7',exact=True).click()
    glyph=page.locator('#customGlyphCanvas');await glyph.click(position={'x':80,'y':70});await save();assert '7' in content()['custom_font']['glyphs']
    await page.locator('#customFontCategory').select_option('Lettere greche');await page.locator('#customFontAlphabet button').get_by_text('α',exact=True).click();await glyph.click(position={'x':100,'y':120});await save();assert {'7','α'}<=set(content()['custom_font']['glyphs'])
    await page.locator('#customFontApply').click();await page.wait_for_function('document.fonts.check("30px TramontoPersonal")')
    formula=page.locator('#handFormulaCanvas');await formula.scroll_into_view_if_needed();box=await formula.bounding_box();await page.mouse.move(box['x']+50,box['y']+80);await page.mouse.down();await page.mouse.move(box['x']+150,box['y']+140,steps=8);await page.mouse.move(box['x']+320,box['y']+60,steps=8);await page.mouse.up();await formula.click(position={'x':200,'y':60});await formula.press('Meta+z')
    await page.locator('#handFormulaName').fill('Il mio sistema');await page.locator('#handFormulaSave').click();await save();assert len(content()['custom_font']['templates'])==1;assert len(content()['custom_font']['templates'][0]['strokes'])==1
    await page.locator('#handFormulaInsertDrawing').click();await save();assert len(content()['drawing']['strokes'])==1;await page.locator('#drawingCanvas').press('Meta+z');await save();assert content()['drawing']['strokes']==[]
    await page.locator('#handFormulaInsertText').click();await page.locator('#richEditor img').wait_for();await save();assert len(content()['images'])==2
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=draw]').click();await page.locator('#fontWorkshop summary').click();assert await page.locator('#handFormulaSelect option').count()==2;await page.locator('#handFormulaSelect').select_option(label='Il mio sistema');assert await page.locator('#handFormulaSvg path').count()==1
    await page.locator('#customFontCategory').select_option('Numeri');assert await page.locator('#customFontAlphabet button.has-glyph').count()==1;await page.locator('#customFontCategory').select_option('Simboli matematici');assert await page.locator('#customFontAlphabet button').get_by_text('∫',exact=True).count()==1
    await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-hand-formulas.png'),full_page=True);await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.locator('[data-pane=math]').click();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    await browser.close()
  finally:await server.close();store.close()
  assert not errors,errors
 print('Function study OK: exact reported LaTeX, domain+sign+zeros+quadrants, area+derivative, notebook snapshots+report+reload, centering, sandbox, per-glyph font and handmade formula library+undo+reload, mobile fit.')

if __name__=='__main__':asyncio.run(main())
