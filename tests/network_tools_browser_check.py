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

async def main():
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder)
  for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js','tramonto-math.js','tramonto-study.js','tramonto-tools.js'):shutil.copy2(ROOT/name,root/name)
  shutil.copytree(ROOT/'vendor',root/'vendor');settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Tools test');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible')
    # Supplied point charts survive reload and can become notebook images.
    await page.locator('[data-pane=math]').click();await page.evaluate('TramontoStudy.openTool("graph")');await page.locator('#chartTitle').fill('Measured data');await page.locator('#chartKind').select_option('bar');await page.locator('#chartPoints').fill('0; 1\n1; 3\n2; -1');await page.locator('#buildDataChart').click();assert await page.locator('#dataChartSvg rect').count()==4
    await page.locator('#insertDataChart').click();await page.wait_for_function('()=>document.querySelector("#richEditor img")!==null');await page.locator('[data-pane=text]').click()
    await page.locator('#richEditor img').click();await page.locator('#inlineImageWidth').fill('150');await page.locator('#inlineImageWidth').dispatch_event('change');await page.locator('#inlineImageLayout').select_option('free');image=page.locator('#richEditor img');box=await image.bounding_box();await page.mouse.move(box['x']+40,box['y']+20);await page.mouse.down();await page.mouse.move(box['x']+100,box['y']+65);await page.mouse.up();assert float(await image.get_attribute('data-x'))>40;assert float(await image.get_attribute('data-y'))>20
    assert await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.evaluate('doc.content.chart.points.length')==3;assert float(await page.locator('#richEditor img').get_attribute('data-x'))>40
    assert await page.evaluate('TramontoWorkspace.preparePrint()');assert await page.locator('#printDocument img').evaluate('e=>getComputedStyle(e).position')=='absolute';await page.evaluate('TramontoWorkspace.cleanupPrint()')
    # Both physical interfaces are chosen explicitly; cable mode remains selected.
    await page.locator('[data-pane=network]').click();await page.wait_for_function('()=>document.querySelector("#networkModel option")!==null')
    net={'nodes':[{'id':'PC1','type':'pc','name':'PC1','x':150,'y':200,'ip':'192.168.1.2/24','gateway':'','vlan':1,'interfaces':[],'enabled':True},{'id':'SW1','type':'switch','model':'switch24','name':'SW1','x':500,'y':200,'ip':'','gateway':'','vlan':1,'interfaces':[],'enabled':True},{'id':'PC2','type':'pc','name':'PC2','x':850,'y':200,'ip':'192.168.1.3/24','gateway':'','vlan':1,'interfaces':[],'enabled':True}],'links':[]}
    await page.evaluate('(n)=>{doc.content.network=n;document.querySelector("#networkUndo").click();}',net)
    # Render via the existing pane reload hook.
    await page.evaluate('changed()');assert await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=network]').click();await page.locator('#networkWire').click()
    async def connect(a,ap,b,bp):
     await page.locator('[data-net-id="'+a+'"]').click();await page.locator('#networkPortDialog').wait_for(state='visible');await page.locator('#networkPortDialog button').filter(has_text=ap).first.click();await page.locator('[data-net-id="'+b+'"]').click();await page.locator('#networkPortDialog button').filter(has_text=bp).first.click()
    await connect('PC1','Ethernet0','SW1','FastEthernet0/1');assert await page.locator('#networkWire').get_attribute('aria-pressed')=='true';await connect('PC2','Ethernet0','SW1','FastEthernet0/2')
    links=await page.evaluate('doc.content.network.links');assert links[0]['to_port']=='FastEthernet0/1';assert links[1]['to_port']=='FastEthernet0/2';assert await page.evaluate('TramontoLab.trace("PC1","PC2")')==['PC1','SW1','PC2']
    await page.locator('#networkSelect').click();await page.locator('[data-net-id=SW1]').click();await page.locator('#networkDeviceCli').fill('hostname SwitchLab\ninterface FastEthernet0/1\n no shutdown');await page.locator('#networkForm button').click();assert await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=network]').click();await page.locator('[data-net-id=SW1]').click();assert 'hostname SwitchLab' in await page.locator('#networkDeviceCli').input_value()
    await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;await browser.close()
  finally:await server.close();store.close()
 print('Notebook tools OK: chart/save/reload, freely dragged image/print, physical ports, repeated cable tool, ping and persistent device CLI, mobile.')

if __name__=='__main__':asyncio.run(main())
