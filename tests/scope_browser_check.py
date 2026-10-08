"""Scope playback/cursor precision and expanding viewport; disposable data only."""
import asyncio
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
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
from lab import Spice
from test_scope import scope_circuit

async def main():
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder)
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js','tramonto-math.js','tramonto-study.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Scope test');server=TestServer(web_app(service));errors=[]
  async def simulation(_self,prepared):
   await asyncio.sleep(.65)
   x=[i*1e-6 for i in range(12001)];series=[]
   for metadata in prepared['traces']:
    channel=metadata.get('channel','A');values=[math.sin(2*math.pi*1000*t) if channel=='A' else .5*math.cos(2*math.pi*1000*t) for t in x]
    if channel=='A':values[2011]=9.87654321
    series.append({**metadata,'values':values})
   return {'engine':'test fixture','analysis':'tran','x':x,'series':series,'total_samples':len(x),'display_samples':len(x),'downsampled':False}
  with patch.object(Spice,'available',True),patch.object(Spice,'run',simulation):
   await server.start_server()
   try:
    async with async_playwright() as p:
     browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
     await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=circuit]').click()
     await page.evaluate('(c)=>{doc.content.circuit=c;renderCircuit();changed();}',scope_circuit());await page.evaluate('TramontoTools.saveDoc()')
     assert await page.locator('[data-component-id="OSC1"] [data-port]').count()==4
     assert 'A+' in await page.locator('[data-component-id="OSC1"]').text_content();assert 'B−' in await page.locator('[data-component-id="OSC1"]').text_content()
     await page.locator('#spiceAnalysis').select_option('tran');await page.locator('#simulateCircuit').click();assert await page.locator('#oscilloscopePanel').get_attribute('data-state')=='acquiring';await page.wait_for_function('()=>document.querySelector("#simulationStatus").textContent.includes("completata")')
     state=await page.evaluate('TramontoLab.oscilloscope.state()');assert state['playing'] and state['count']==12001,state
     await page.locator('#scopePlay').click();state=await page.evaluate('TramontoLab.oscilloscope.state()');assert not state['playing']
     await page.locator('#scopeTimeline').fill('2000');await page.locator('#scopeTimeline').dispatch_event('input');await page.locator('#scopeNext').click();assert (await page.evaluate('TramontoLab.oscilloscope.state()'))['head']==2001;await page.locator('#scopePrevious').click();assert (await page.evaluate('TramontoLab.oscilloscope.state()'))['head']==2000
     await page.locator('#scopeCursor1').fill('0.002011');await page.locator('#scopeCursor1').dispatch_event('change');await page.locator('#scopeCursor2').fill('0.002111');await page.locator('#scopeCursor2').dispatch_event('change')
     state=await page.evaluate('TramontoLab.oscilloscope.state()');assert state['cursors']==[2011,2111],state
     assert '9.87654321' in await page.locator('#scopeMeasurements').text_content();assert '100 μs' in await page.locator('#scopeMeasurements').text_content();assert '10 kHz' in await page.locator('#scopeMeasurements').text_content()
     # The reference-style panel keeps exact cursor picking and adapts when its window is resized.
     assert await page.locator('.scope-scales legend').inner_text()=='Base tempi'
     assert await page.locator('.scope-channel-a legend').inner_text()=='Canale A'
     assert await page.locator('#scopeCanvas').evaluate('e=>Array.from(e.getContext("2d").getImageData(1,1,1,1).data).slice(0,3)')==[237,241,233]
     await page.locator('#scopeTimeline').fill('12000');await page.locator('#scopeTimeline').dispatch_event('input');await page.locator('#circuitOpenScope').click();await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-scope-desktop.png'),full_page=True);await page.locator('#oscilloscopePanel').evaluate('e=>e.style.width="500px"');await page.wait_for_timeout(100)
     assert await page.locator('.scope-control-rack').evaluate('e=>getComputedStyle(e).gridTemplateColumns.split(" ").length')==1
     assert await page.locator('#scopeVoltsA').evaluate('e=>getComputedStyle(e).borderRadius')=='2px'
     assert await page.locator('#oscilloscopePanel').evaluate('e=>e.scrollWidth<=e.clientWidth')
     await page.locator('#oscilloscopePanel').evaluate('e=>e.style.removeProperty("width")');await page.locator('#scopeClose').click()
     span=state['view']['span'];await page.locator('#scopeZoomIn').click();assert (await page.evaluate('TramontoLab.oscilloscope.state()'))['view']['span']==span/2;await page.locator('#scopeZoomOut').click();await page.locator('#scopeVoltsA').select_option('2');await page.locator('#scopeOffsetA').fill('1');await page.locator('#scopeOffsetA').dispatch_event('change')
     await page.locator('#scopeFit').click();await page.locator('#scopeActiveCursor').select_option('0');canvas=page.locator('#scopeCanvas');await canvas.scroll_into_view_if_needed();box=await canvas.bounding_box();await canvas.click(position={'x':62+(box['width']-84)*.5,'y':box['height']*.5});assert abs((await page.evaluate('TramontoLab.oscilloscope.state()'))['cursors'][0]-6000)<=1
     async with page.expect_download() as download:await page.locator('#downloadSpiceCsv').click()
     text=Path(await (await download.value).path()).read_text();assert len(text.splitlines())==12002;assert '9.87654321' in text
     # Scope can open as a floating instrument without losing data.
     await page.locator('#circuitOpenScope').click();assert 'scope-floating' in await page.locator('#oscilloscopePanel').get_attribute('class');await page.locator('#scopeClose').click()
     # Offscreen objects grow stored space; DOM size depends on the camera, not the extent.
     before=await page.locator('#circuitSvg').get_attribute('viewBox');await page.locator('#circuitZoomIn').click();after=await page.locator('#circuitSvg').get_attribute('viewBox');assert float(after.split()[2])<float(before.split()[2]);await page.locator('#circuitZoomOut').click()
     await page.evaluate('()=>{const p={...doc.content.circuit.components[0],id:"FAR",x:12000,y:9000};doc.content.circuit.components.push(p);growCircuitCanvas();renderCircuit();changed();}')
     assert not await page.locator('[data-component-id="FAR"]').count();await page.evaluate('TramontoTools.saveDoc()');saved=json.loads(store.rows('SELECT content FROM notes LIMIT 1')[0]['content'])['circuit'];assert saved['canvas']['width']>=13000 and saved['canvas']['height']>=9120,saved['canvas']
     await page.locator('#circuitFit').click();await page.wait_for_function('()=>document.querySelector("[data-component-id=FAR]")!==null')
     await page.locator('#circuitExpand').click();await page.wait_for_function('()=>!!document.fullscreenElement||document.getElementById("circuitWorkbench").classList.contains("expanded")');await page.locator('#circuitOpenScope').click();assert await page.locator('#circuitWorkbench #oscilloscopePanel').count()==1;await page.locator('#scopeClose').click();await page.locator('#circuitExpand').click()
     await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=circuit]').click();assert (await page.evaluate('doc.content.circuit.canvas.width'))>=13000
     # Real placement near an edge expands bounds and persists it.
     await page.evaluate('()=>{circuitCamera={x:12000,y:8500,width:1000,height:640};applyCircuitCamera();renderCircuit();}');await page.locator('[data-component=resistor]').click();svg=page.locator('#circuitSvg');await svg.scroll_into_view_if_needed();box=await svg.bounding_box();await svg.click(position={'x':box['width']*.92,'y':box['height']*.9});await page.evaluate('TramontoTools.saveDoc()');assert (await page.evaluate('doc.content.circuit.canvas.width'))>=14000
     # A sparse, large scene keeps the visible DOM small while panning.
     benchmark=await page.evaluate('()=>{const c=doc.content.circuit,parts=[];for(let i=0;i<80;i++)parts.push({id:"S"+i,type:"resistor",x:100+(i%10)*2000,y:100+Math.floor(i/10)*2000,rotation:0,label:"R"+i,value:"1k"});c.components=parts;c.wires=parts.slice(1).map((p,i)=>({id:"SW"+i,from:{component:parts[i].id,port:1},to:{component:p.id,port:0}}));circuitCamera={x:0,y:0,width:1000,height:640};growCircuitCanvas();let start=performance.now();renderCircuit();const cold=performance.now()-start;start=performance.now();for(let i=0;i<20;i++){circuitCamera.x+=10;applyCircuitCamera();renderCircuit();}return{cold,frame:(performance.now()-start)/20,visible:document.querySelectorAll("#circuitSvg [data-component-id]").length};}')
     assert benchmark['visible']<=2,benchmark;assert benchmark['frame']<100,benchmark;print('Viewport benchmark:',benchmark)
     # Restore the connected circuit for the asynchronous cancellation check.
     await page.evaluate('(c)=>{doc.content.circuit=c;circuitCamera={x:0,y:0,width:1000,height:640};applyCircuitCamera();renderCircuit();changed();}',scope_circuit());await page.evaluate('TramontoTools.saveDoc()')
     # Cancellation after switching notes must not attach old results to the new page.
     await page.locator('#simulateCircuit').click();await page.locator('#newNote').click();await page.wait_for_timeout(900);assert (await page.evaluate('TramontoLab.oscilloscope.state()'))['count']==0
     await page.set_viewport_size({'width':390,'height':844});await page.locator('[data-pane=circuit]').click();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.locator('#circuitOpenScope').click();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-scope-mobile.png'),full_page=True);await page.locator('#scopeClose').click()
     assert not errors,errors;await browser.close()
   finally:await server.close();store.close()
 print('Scope browser OK: four ports, acquisition/autoplay, exact 12,001 samples, transport, two sample cursors/Δt/ΔV, zoom/scales, CSV precision, floating/fullscreen scope, growing/culling/persisted canvas, stale-job cancellation, mobile.')

if __name__=='__main__':asyncio.run(main())
