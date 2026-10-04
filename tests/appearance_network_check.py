"""Real gestures, topology edits, subnet planning, theme contrast and print regressions."""
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
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Admin');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1600,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('#richEditor').fill('Prova temi e laboratori');await page.evaluate('TramontoTools.saveDoc()')
    for theme in ('light','dark','gray','black'):
     await page.locator('#notesTheme').select_option(theme)
     for palette in ('sage','graphite','ocean','violet','rose','amber'):
      await page.locator('#notesPalette').select_option(palette)
      ratios=await page.evaluate('''()=>{const s=getComputedStyle(document.documentElement),rgb=v=>v.match(/[\\d.]+/g).slice(0,3).map(Number),luma=c=>rgb(c).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((v,x,i)=>v+x*[.2126,.7152,.0722][i],0),color=k=>{const e=document.createElement('i');e.style.color=s.getPropertyValue(k);document.body.append(e);const c=getComputedStyle(e).color;e.remove();return c;},ratio=(a,b)=>{const x=luma(color(a)),y=luma(color(b));return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);};return[ratio('--text','--surface'),ratio('--muted','--surface'),ratio('--accent','--accent-text')];}''')
      assert min(ratios)>=4.5,(theme,palette,ratios)
    await page.locator('#notesTheme').select_option('gray');await page.locator('#notesPalette').select_option('graphite')
    for skin in ('clay','cyber','brutal','scrap','surreal'):
     await page.locator('#notesStyle').select_option(skin);await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),skin
     await page.set_viewport_size({'width':1600,'height':1100});await page.emulate_media(media='print');pdf=await page.pdf(prefer_css_page_size=True,print_background=True);assert len(re.findall(rb'/Type\s*/Page\b',pdf))==1,skin;assert await page.locator('#a4Sheet').evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)';await page.emulate_media(media='screen')
    (ROOT/'artifacts').mkdir(exist_ok=True);await page.screenshot(path=str(ROOT/'artifacts/tramonto-surreal-gray.png'),full_page=True);await page.locator('#notesStyle').select_option('cyber');await page.locator('#notesTheme').select_option('black');await page.locator('#notesPalette').select_option('ocean');await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.locator('#notesStyle').input_value()=='cyber';assert await page.locator('#notesTheme').input_value()=='black';assert await page.locator('#notesPalette').input_value()=='ocean';await page.screenshot(path=str(ROOT/'artifacts/tramonto-cyber-black.png'),full_page=True)
    await page.locator('[data-pane=network]').click();await page.locator('#networkExample').click();assert await page.locator('#networkPalette svg').count()==9;assert await page.locator('#networkSvg [data-net-id] svg').count()==4
    await page.locator('#networkSelect').click();await page.locator('[data-net-id=PC1]').click();await page.locator('[data-net-id=PC2]').click(modifiers=['Shift']);assert '2 oggetti' in await page.locator('#networkSelectionStatus').inner_text()
    before=await page.locator('[data-net-id=PC1]').get_attribute('transform');other=await page.locator('[data-net-id=PC2]').get_attribute('transform');box=await page.locator('[data-net-id=PC1]').bounding_box();await page.mouse.move(box['x']+20,box['y']+20);await page.mouse.down();await page.mouse.move(box['x']+50,box['y']+50,steps=5);await page.mouse.up();assert before!=await page.locator('[data-net-id=PC1]').get_attribute('transform');assert other!=await page.locator('[data-net-id=PC2]').get_attribute('transform')
    await page.locator('#networkCommand').fill('show ip interface brief');await page.locator('#networkCommand').press('Delete');assert await page.locator('#networkSvg [data-net-id]').count()==4
    await page.locator('#networkSvg').focus();await page.keyboard.press('Delete');assert await page.locator('#networkSvg [data-net-id]').count()==2;assert await page.locator('#networkSvg [data-link-id]').count()==1;await page.locator('#networkUndo').click();assert await page.locator('#networkSvg [data-net-id]').count()==4
    # Holding two objects selects both, without a modifier key or toolbar mode.
    await page.locator('#networkSelect').click()
    for ident in ('PC1','PC2'):
     box=await page.locator('[data-net-id='+ident+']').bounding_box();await page.mouse.move(box['x']+20,box['y']+20);await page.mouse.down();await page.wait_for_timeout(500);await page.mouse.up()
    assert '2 oggetti' in await page.locator('#networkSelectionStatus').inner_text();await page.keyboard.press('Backspace');assert await page.locator('#networkSvg [data-net-id]').count()==2;await page.locator('#networkUndo').click()
    # Area selection includes the three LAN objects, keeping the router outside.
    await page.locator('#networkSelect').click();await page.locator('#networkSvg').scroll_into_view_if_needed();box=await page.locator('#networkSvg').bounding_box();sx=box['width']/1000;sy=box['height']/640;await page.mouse.move(box['x']+80*sx,box['y']+220*sy);await page.mouse.down();await page.mouse.move(box['x']+900*sx,box['y']+400*sy,steps=8);await page.mouse.up();assert '3 oggetti' in await page.locator('#networkSelectionStatus').inner_text();await page.keyboard.press('Escape')
    # Real Chromium touch events exercise long press rather than only mouse hold.
    await page.locator('#networkSelect').click();session=await page.context.new_cdp_session(page)
    for ident in ('PC1','PC2'):
     await page.locator('[data-net-id='+ident+']').scroll_into_view_if_needed();box=await page.locator('[data-net-id='+ident+']').bounding_box();await session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':box['x']+20,'y':box['y']+20}]});await page.wait_for_timeout(500);await session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    assert '2 oggetti' in await page.locator('#networkSelectionStatus').inner_text();await session.detach();await page.keyboard.press('Escape')
    await page.locator('#networkPalette').get_by_role('button',name='PC',exact=True).click();await page.locator('[data-net-id=PC1]').click();await page.locator('[data-net-id=PC2]').click(modifiers=['Shift']);assert '2 oggetti' in await page.locator('#networkSelectionStatus').inner_text();await page.keyboard.press('Escape')
    await page.locator('#networkSelect').click();await page.locator('[data-net-id=PC1]').click();await page.get_by_role('button',name='Duplica selezione',exact=True).click();assert await page.locator('#networkSvg [data-net-id]').count()==5;await page.locator('#networkUndo').click()
    await page.get_by_role('button',name='Controlla topologia',exact=True).click();assert 'Nessun problema' in await page.locator('#networkReport').inner_text();await page.locator('#pingSource').select_option('PC1');await page.locator('#pingTarget').select_option('PC2');await page.get_by_role('button',name='Traceroute simulato',exact=True).click();assert 'SW1' in await page.locator('#networkReport').inner_text()
    await page.locator('#subnetSplit').click();assert await page.locator('#subnetPlan tr').count()==5;await page.locator('#vlsmCalculate').click();assert '192.168.10.64/27' in await page.locator('#subnetPlan').inner_text();await page.locator('#vlsmHosts').fill('250, 250');await page.locator('#vlsmCalculate').click();assert 'non entrano' in await page.locator('#subnetPlanMessage').inner_text();assert await page.locator('#subnetPlan tr').count()==0
    await page.locator('#vlsmHosts').fill('50,20,10');await page.locator('#vlsmCalculate').click();await page.locator('#subnetInsert').click();assert '192.168.10.64/27' in await page.locator('#richEditor').inner_text()
    # Circuit selection removes attached wires in the same undo operation.
    await page.locator('[data-pane=circuit]').click();await page.locator('#circuitExample').select_option('divider');await page.locator('#selectCircuit').click();await page.locator('[data-component-id=V1]').click();await page.locator('[data-component-id=R1]').click(modifiers=['Shift']);assert '2 oggetti' in await page.locator('#circuitSelectionStatus').inner_text();await page.keyboard.press('Delete');assert await page.locator('#circuitSvg [data-component-id]').count()==3;await page.locator('#undoCircuit').click();assert await page.locator('#circuitSvg [data-component-id]').count()==5
    await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=network]').click();assert await page.locator('#networkSvg [data-net-id]').count()==4;await browser.close()
  finally:await server.close();store.close()
  assert not errors,errors
 print('Appearance/network OK: 24 contrast combinations, all five skins on mobile/A4, saved preferences, multiselection/drag/Delete/hold/undo, local icons, diagnostics, traceroute and VLSM.')

if __name__=='__main__':asyncio.run(main())
