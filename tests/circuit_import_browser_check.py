"""Real file upload, conversion review, switch gestures and legacy scope ports."""
import asyncio,json,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys,secret_file
from service import Service
from store import Store
from test_circuit_import import RC,native_xml,literal_container,connected

async def main():
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder)
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Import test');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=circuit]').click();svg=page.locator('#circuitSvg')
    async def circuit():return await page.evaluate('JSON.parse(JSON.stringify(doc.content.circuit))')
    async def save():assert await page.evaluate('TramontoTools.saveDoc()')
    baseline={'components':[{'id':'R1','type':'resistor','label':'R1','value':'1k','x':150,'y':220,'rotation':0},{'id':'C1','type':'capacitor','label':'C1','value':'1u','x':780,'y':220,'rotation':0},{'id':'OSC1','type':'scope','label':'OSC1','value':'','x':480,'y':450,'rotation':0}], 'wires':[{'id':'w1','from':{'component':'R1','port':1},'to':{'component':'C1','port':0},'color':'#3159a4','points':[{'x':350,'y':220},{'x':600,'y':220}]}]}
    await page.evaluate('(c)=>{doc.content.circuit=c;renderCircuit();changed();}',baseline);await save();baseline=await circuit()
    # Legacy scopes without portsBottom use the same bottom terminals, including palette.
    assert [await svg.locator('[data-component-id="OSC1"] [data-port="'+str(i)+'"]').get_attribute('cy') for i in range(4)]==['50']*4
    assert [await page.locator('[data-component=scope] svg circle').nth(i).get_attribute('cy') for i in range(4)]==['50']*4
    await page.locator('[data-component=switch]').click();await svg.scroll_into_view_if_needed();box=await svg.bounding_box();await svg.click(position={'x':480*box['width']/1000,'y':220*box['height']/640});c=await circuit();assert len(c['components'])==4 and len(c['wires'])==2,c
    switch=c['components'][-1];assert switch['type']=='switch' and not switch['params']['closed'];assert all(w['color']=='#3159a4' for w in c['wires']);assert connected(c,('R1',1),(switch['id'],0)) and connected(c,('C1',0),(switch['id'],1));assert not connected(c,('R1',1),('C1',0))
    await svg.locator('[data-component-id="'+switch['id']+'"]').dblclick();assert (await circuit())['components'][-1]['params']['closed'],('toggle',await circuit());await page.locator('#undoCircuit').click();assert not (await circuit())['components'][-1]['params']['closed'],('undo_toggle',await circuit());await page.locator('#undoCircuit').click();assert await circuit()==baseline,('undo_insert',await circuit(),baseline)
    await svg.locator('[data-component-id="OSC1"]').dblclick();assert await page.locator('#oscilloscopePanel').is_visible();await page.locator('#scopeClose').click()
    # Upload converts, but review is atomic until the user applies it.
    before=await circuit();await page.locator('#circuitImportFile').set_input_files({'name':'Filtro.cir','mimeType':'text/plain','buffer':RC});await page.locator('#circuitImportPreview').wait_for(state='visible');assert await circuit()==before;assert 'Netlist SPICE' in await page.locator('#circuitImportSummary').inner_text()
    dock=await page.locator('#pane-circuitTools').bounding_box();stage=await svg.bounding_box();assert dock['x']>=stage['x']+stage['width']-1
    await page.locator('#applyCircuitImport').click();await save();c=await circuit();assert any(p['id']=='V1' for p in c['components']);await page.locator('#undoCircuit').click();assert await circuit()==baseline,('undo_insert',await circuit(),baseline)
    await page.locator('#circuitImportFile').set_input_files({'name':'Bad.cir','mimeType':'text/plain','buffer':RC.replace(b'R1 in out 15k',b'B1 out 0 V=sin(time)')});await page.wait_for_function('()=>document.querySelector("#circuitImportStatus").textContent.includes("B1")');assert await circuit()==baseline,('undo_insert',await circuit(),baseline);assert not await page.locator('#circuitImportPreview').is_visible()
    await page.locator('#circuitImportFile').set_input_files({'name':'Native.ms14','mimeType':'application/octet-stream','buffer':literal_container(native_xml())});await page.locator('#circuitImportPreview').wait_for(state='visible');assert 'Multisim nativo' in await page.locator('#circuitImportSummary').inner_text();await page.locator('#applyCircuitImport').click();await save();native=await circuit();assert connected(native,('XSC1',0),('V1',0));assert connected(native,('XSC1',1),('V1',1));assert connected(native,('XSC1',2),('C1',0));assert connected(native,('XSC1',3),('C1',1))
    await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=circuit]').click();assert await circuit()==native;await page.locator('#circuitFit').click()
    await page.locator('.portal-transition').wait_for(state='detached');await page.screenshot(path=str(ROOT/'artifacts/tramonto-import-desktop.png'),full_page=True)
    await page.set_viewport_size({'width':390,'height':844});await page.locator('#pane-circuit>.tool-dock-toggle').click();await page.locator('#pane-circuitTools').wait_for(state='visible');assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.locator('#importCircuit').scroll_into_view_if_needed();await page.screenshot(path=str(ROOT/'artifacts/tramonto-import-mobile.png'))
    assert not errors,errors;await browser.close()
  finally:await server.close();store.close()
 print('Import UI OK: native binary and SPICE files, atomic preview/errors, right dock/mobile, legacy bottom ports, switch in series + double click + two-step undo, reload and fit.')

if __name__=='__main__':asyncio.run(main())
