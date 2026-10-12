"""Component/device windows, saved values, scoped CLI and touch gestures."""
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

async def main():
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder)
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js','tramonto-math.js','tramonto-study.js','tramonto-tools.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Tools test');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible')
    await page.locator('[data-pane=circuit]').click()
    circuit={'components':[{'id':'R1','type':'resistor','label':'R1','value':'1k','x':220,'y':200,'rotation':0},{'id':'V1','type':'function','label':'V1','value':'1kHz','x':500,'y':200,'rotation':0},{'id':'S1','type':'switch','label':'S1','value':'aperto','params':{'closed':False},'x':750,'y':200,'rotation':0}],'wires':[]}
    await page.evaluate('(c)=>{doc.content.circuit=c;selectedPart=null;renderCircuit();changed();}',circuit)
    # A redraw between presses must not lose the double click or create two dialogs.
    await page.locator('[data-component-id=R1]').dblclick();await page.locator('#circuitPropertiesDialog').wait_for(state='visible');assert await page.locator('#circuitPropertiesDialog #componentForm').count()==1;await page.locator('#componentValue').fill('2.2k');await page.locator('#componentForm button').click();assert await page.evaluate('doc.content.circuit.components[0].value')=='2.2k';await page.locator('#circuitPropertiesDialogClose').click();await page.locator('#pane-circuitTools #componentForm').wait_for(state='attached')
    await page.locator('[data-component-id=R1]').dblclick();await page.locator('#componentValue').fill('invalid draft');await page.keyboard.press('Escape');await page.locator('#circuitPropertiesDialog').wait_for(state='hidden');assert await page.evaluate('doc.content.circuit.components[0].value')=='2.2k'
    await page.locator('[data-component-id=V1]').dblclick();await page.locator('#sourceFrequency').fill('2500');await page.locator('#sourceAmplitude').fill('3');await page.locator('#componentForm button').click();assert await page.evaluate('doc.content.circuit.components[1].params.frequency')==2500;await page.locator('#circuitPropertiesDialogClose').click();await page.locator('#pane-circuitTools #componentForm').wait_for(state='attached')
    await page.evaluate('TramontoLab.openCircuitProperties("R1");TramontoLab.openCircuitProperties("V1");');await page.wait_for_timeout(100);assert await page.locator('#circuitPropertiesDialog').is_visible();assert await page.locator('#circuitPropertiesDialog #componentForm').count()==1;assert 'V1' in await page.locator('#circuitPropertiesDialogTitle').inner_text();await page.locator('#circuitPropertiesDialogClose').click();await page.locator('#pane-circuitTools #componentForm').wait_for(state='attached')
    # Double click edits a switch without toggling; a later selected click still toggles.
    await page.locator('[data-component-id=S1]').dblclick();await page.locator('#circuitPropertiesDialog').wait_for(state='visible');await page.wait_for_timeout(500);assert not await page.evaluate('doc.content.circuit.components[2].params.closed');await page.locator('#circuitPropertiesDialogClose').click();await page.locator('[data-component-id=S1]').click();await page.wait_for_function('()=>doc.content.circuit.components[2].params.closed===true');assert not await page.locator('#circuitPropertiesDialog').is_visible()
    # Dragging a component remains a drag, never an edit window.
    part=page.locator('[data-component-id=R1]');box=await part.bounding_box();await page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);await page.mouse.down();await page.mouse.move(box['x']+box['width']/2+45,box['y']+box['height']/2+25,steps=5);await page.mouse.up();assert not await page.locator('#circuitPropertiesDialog').is_visible()
    assert await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.evaluate('doc.content.circuit.components[0].value')=='2.2k'
    await page.locator('[data-pane=network]').click();await page.locator('#networkExample').click();await page.locator('[data-net-id=R1]').dblclick();await page.locator('#networkPropertiesDialog').wait_for(state='visible');assert await page.locator('#networkPropertiesDialog #networkForm').count()==1
    await page.locator('#networkName').fill('LabRouter');await page.locator('#networkDeviceCli').fill('Custom device notes');await page.locator('#networkForm button').click();await page.locator('#deviceTabcli').click();assert await page.locator('#networkPropertiesDialog #networkCli').count()==1
    async def command(text):await page.locator('#networkCommand').fill(text);await page.locator('#networkCli button').click()
    await command('show running-config');assert 'Custom device notes' in await page.locator('#networkConsole').inner_text();assert 'hostname PC1' not in await page.locator('#networkConsole').inner_text()
    await command('ip address 192.168.1.254 255.255.255.0');assert await page.evaluate('doc.content.network.nodes.find(n=>n.id==="R1").ip')=='192.168.1.254/24'
    await command('hostname RouterEdited');assert await page.evaluate('doc.content.network.nodes.find(n=>n.id==="R1").name')=='RouterEdited'
    before=await page.evaluate('JSON.stringify(doc.content.network)');await command('vlan 5000');assert await page.evaluate('JSON.stringify(doc.content.network)')==before;assert '4094' in await page.locator('#networkConsole').inner_text()
    await command('shutdown');assert not await page.evaluate('doc.content.network.nodes.find(n=>n.id==="R1").enabled');await command('no shutdown');assert await page.evaluate('doc.content.network.nodes.find(n=>n.id==="R1").enabled')
    await command('ping 192.168.1.2');assert 'RouterEdited' in await page.locator('#networkResult').inner_text();assert 'PC1' in await page.locator('#networkResult').inner_text()
    await page.locator('#deviceTabports').click();assert 'GigabitEthernet0/1' in await page.locator('#devicePortsTable').inner_text();assert 'SW1' in await page.locator('#devicePortsTable').inner_text()
    await page.locator('#networkPropertiesDialogClose').click();await page.locator('#pane-networkTools #networkForm').wait_for(state='attached');assert await page.locator('#pane-network #networkCli').count()==1;assert await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.evaluate('doc.content.network.nodes.find(n=>n.id==="R1").name')=='RouterEdited'
    # Mobile double tap and keyboard opening show the same compact dialog.
    await page.set_viewport_size({'width':390,'height':844});await page.locator('[data-pane=network]').click();await page.locator('[data-net-id=PC1]').dblclick();await page.locator('#networkPropertiesDialog').wait_for(state='visible');assert await page.locator('#networkPropertiesDialog').evaluate('e=>e.scrollWidth<=e.clientWidth');assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.locator('#networkPropertiesDialogClose').click()
    await page.locator('#networkPropertiesButton').click();await page.locator('#networkPropertiesDialog').wait_for(state='visible');await page.locator('#deviceTabproperties').focus();await page.keyboard.press('ArrowRight');assert await page.locator('#deviceTabcli').get_attribute('aria-selected')=='true';await page.keyboard.press('Escape')
    assert not errors,errors;await browser.close()
  finally:await server.close();store.close()
 print('Device windows OK: double click/redraw, resistor/source edits and reload, cancel, switch click vs double click, drag, per-device CLI commands, validation, ports, mobile and keyboard tabs.')

if __name__=='__main__':asyncio.run(main())
