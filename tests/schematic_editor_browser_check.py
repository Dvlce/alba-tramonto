"""Real pointer gestures and API round trips for Tramonto's visual editors."""
import asyncio
import json
import shutil
import sys
import tempfile
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
from lab import build_netlist

async def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for name in ('web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto-font.js','tramonto-math.js','tramonto-study.js'):shutil.copy2(ROOT/name,root/name)
        shutil.copytree(ROOT/'vendor',root/'vendor')
        settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,None),Backups(store,settings));store.register(1,'Editor test')
        server=TestServer(web_app(service));await server.start_server();errors=[]
        def saved():return json.loads(store.rows('SELECT content FROM notes ORDER BY id LIMIT 1')[0]['content'])
        try:
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#bookList button').first.click();await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible')
                await page.locator('[data-pane=circuit]').click();svg=page.locator('#circuitSvg')
                assert await page.locator('[data-component] svg').count()==await page.locator('[data-component]').count()
                await page.locator('#componentSearch').fill('oscillo');assert await page.locator('[data-component]:visible').count()==1;await page.locator('#componentSearch').fill('');await page.locator('#componentCategory').select_option('logic');assert await page.locator('[data-component]:visible').count()==7;await page.locator('#componentCategory').select_option('all')
                assert await svg.get_attribute('data-schematic-style')=='technical';await page.locator('#schematicStyle').select_option('tramonto');assert await svg.get_attribute('data-schematic-style')=='tramonto';await page.locator('#schematicStyle').select_option('technical')
                async def click_point(x,y):
                    await svg.scroll_into_view_if_needed();box=await svg.bounding_box();await svg.click(position={'x':x*box['width']/1000,'y':y*box['height']/640})
                async def place(kind,x,y):await page.locator('[data-component='+kind+']').click();await click_point(x,y)
                async def save():assert await page.evaluate('TramontoTools.saveDoc()')
                await place('resistor',180,180);await place('capacitor',780,360);await place('inductor',480,180);await page.locator('#selectCircuit').click()
                # Automatic wiring from select mode; explicit corners persist through reload.
                await page.locator('#circuitSvg [data-component-id]').nth(0).locator('[data-port="1"]').click()
                await svg.scroll_into_view_if_needed();box=await svg.bounding_box();await page.mouse.move(box['x']+350*box['width']/1000,box['y']+180*box['height']/640)
                assert await page.locator('[data-wire-preview]').count()>0
                await click_point(350,180);await click_point(350,460);await click_point(690,460)
                await page.locator('#circuitSvg [data-component-id]').nth(1).locator('[data-port="0"]').click();await save();w=saved()['circuit']['wires'][0];assert len(w['points'])==3,w
                assert await page.locator('[data-wire-preview]').count()==0
                wire=page.locator('#circuitSvg path[data-wire]').first
                route=await wire.get_attribute('d');coords=await wire.evaluate('p=>Array.from(p.getAttribute("d").matchAll(/[ML]([\\d.-]+) ([\\d.-]+)/g),m=>[+m[1],+m[2]])')
                assert all(abs(a[0]-b[0])<.01 or abs(a[1]-b[1])<.01 for a,b in zip(coords,coords[1:])),coords
                await click_point(350,300);await page.locator('#wireColor').fill('#e62b45');await page.locator('#wireColor').dispatch_event('change');await save();assert saved()['circuit']['wires'][0]['color']=='#e62b45'
                # Escape cancels a draft without adding a wire; Backspace removes only a corner.
                await page.locator('#circuitSvg [data-component-id]').nth(2).locator('[data-port="1"]').click();await click_point(600,180);await svg.press('Backspace');assert await page.locator('circle[data-wire-preview]').count()==0;await svg.press('Escape');await save();assert len(saved()['circuit']['wires'])==1
                await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=circuit]').click();assert (await page.locator('#circuitSvg path[data-wire]').first.get_attribute('d'))==route
                assert await page.locator('#circuitSvg path[data-wire]').first.get_attribute('stroke')=='#e62b45'
                # Branch onto a wire: real junction topology, one-step undo.
                await page.locator('#circuitSvg [data-component-id]').nth(2).locator('[data-port="1"]').click();await click_point(350,300);await save();c=saved()['circuit'];assert len(c['wires'])==3;assert c['components'][-1]['type']=='junction';await page.locator('#undoCircuit').click();await save();assert len(saved()['circuit']['wires'])==1
                # Moving a connected group translates bends once; a single endpoint changes only its adjacent bend.
                baseline=saved()['circuit'];ids=[baseline['components'][i]['id'] for i in (0,1)];original=baseline['wires'][0]
                async def drag_part(dx,dy):
                    await svg.scroll_into_view_if_needed();box=await svg.bounding_box();scale=box['width']/1000
                    await page.mouse.move(box['x']+180*scale,box['y']+180*scale);await page.mouse.down();await page.mouse.move(box['x']+(180+dx)*scale,box['y']+(180+dy)*scale,steps=8);await page.mouse.up();await save()
                await page.evaluate('(ids)=>TramontoLab.circuitSelection.select(ids.map(id=>"c:"+id))',ids);await drag_part(100,80)
                moved=saved()['circuit']['wires'][0];assert moved['from']==original['from'] and moved['to']==original['to'];assert moved['color']==original['color'];assert moved['points']==[{'x':p['x']+100,'y':p['y']+80} for p in original['points']],moved
                coords=await wire.evaluate('p=>Array.from(p.getAttribute("d").matchAll(/[ML]([\\d.-]+) ([\\d.-]+)/g),m=>[+m[1],+m[2]])');assert all(abs(a[0]-b[0])<.01 or abs(a[1]-b[1])<.01 for a,b in zip(coords,coords[1:])),coords
                await page.locator('#undoCircuit').click();await save();assert saved()['circuit']==baseline
                await page.evaluate('(id)=>TramontoLab.circuitSelection.select(["c:"+id])',ids[0]);await drag_part(0,60);moved=saved()['circuit']['wires'][0];assert moved['points'][0]['y']==original['points'][0]['y']+60;assert moved['points'][1:]==original['points'][1:];assert moved['from']==original['from'] and moved['to']==original['to'];await page.locator('#undoCircuit').click();await save()
                # The new summing block has visible ports and editable gains which round trip through the API.
                await place('summer',650,170);await page.locator('#selectCircuit').click();await page.locator('[data-component-id]').last.click(position={'x':35,'y':30});assert await page.locator('#summerParams').is_visible();await page.locator('#summerGainA').fill('2');await page.locator('#summerGainB').fill('-1');await page.locator('#componentForm button').first.click();await save();assert saved()['circuit']['components'][-1]['params']=={'gainA':2,'gainB':-1}
                # Templates use valid simulator topology and include a probe and ground.
                page.on('dialog',lambda d:asyncio.create_task(d.accept()))
                for kind in ('wien','phase','colpitts','peak','image_tl081','rc_reference'):
                    await page.locator('#circuitExample').select_option(kind);await save();c=saved()['circuit'];assert any(p['type'] in ('probe','scope') for p in c['components']);build_netlist(c,{'analysis':'tran','stop':.02,'samples':500})
                    if kind=='peak':
                        assert await svg.locator('[data-component-id="OSC1"] [data-port]').count()==4;assert await svg.locator('[data-component-id="U1"] text').count()==5;assert '2 Vpk' in await svg.text_content();await svg.scroll_into_view_if_needed();await svg.screenshot(path=str(ROOT/'artifacts'/'tramonto-reference-schematic.png'));(ROOT/'artifacts'/'tramonto-reference-circuit.json').write_text(json.dumps(c));(ROOT/'artifacts'/'tramonto-reference-schematic.svg').write_text(await svg.evaluate('e=>e.outerHTML'))
                    if kind=='image_tl081':
                        parts={p['id']:p for p in c['components']};assert parts['A1']['type']=='summer3';assert not any(p['type']=='resistor' for p in c['components']);assert [(parts[n]['params']['amplitude'],parts[n]['params']['frequency']) for n in ('V1','V2','V6')]==[(2,1500),(5,10000),(.5,670)];assert all(parts[n]['params']['model']=='tl081' for n in ('U1','U2'))
                        assert await svg.locator('[data-component-id="XSC1"] [data-port]').count()==4
                        assert await svg.locator('[data-component-id="U1"] [data-port="1"]').get_attribute('cy')=='-12'
                        assert next(w for w in c['wires'] if w['id']=='u1_feedback')['from']['component']=='JOUT1'
                        await svg.scroll_into_view_if_needed();await svg.screenshot(path=str(ROOT/'artifacts/tramonto-image-schematic.png'));(ROOT/'artifacts/tramonto-image-circuit.json').write_text(json.dumps(c));(ROOT/'artifacts/tramonto-image-schematic.svg').write_text(await svg.evaluate('e=>e.outerHTML'))
                        assert await page.locator('#circuitFit').inner_text()=='Centra progetto'
                        note_id=store.rows('SELECT id FROM notes ORDER BY id LIMIT 1')[0]['id']
                        await page.evaluate('(id)=>localStorage.setItem("alba.circuitViewport."+id,JSON.stringify({x:30000,y:30000,width:1200,height:500}))',note_id);await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=circuit]').click();assert await svg.locator('[data-component-id]').count()==0;await page.locator('#circuitFit').click();await page.wait_for_function('()=>document.querySelectorAll("#circuitSvg [data-component-id]").length===28');await save();assert saved()['circuit']==c
                        await svg.press('a');await save();assert next(p for p in saved()['circuit']['components'] if p['id']=='S1')['params']['closed'];await page.locator('#undoCircuit').click();await save();assert not next(p for p in saved()['circuit']['components'] if p['id']=='S1')['params']['closed']
                    if kind=='rc_reference':
                        parts={p['id']:p for p in c['components']};assert parts['V1']['params']=={'frequency':100,'amplitude':.1,'offset':0,'phase':0,'wave':'sine'};assert parts['R1']['value']=='15 kΩ' and parts['C1']['value']=='100 nF';assert all(w['color']=='#161b23' for w in c['wires'])
                        prepared=build_netlist(c,{'analysis':'tran','stop':.05,'samples':5000});assert [t['channel'] for t in prepared['traces']]==['A','B'];assert '100 mVpk' in await svg.text_content()
                        await svg.scroll_into_view_if_needed();await svg.screenshot(path=str(ROOT/'artifacts/tramonto-rc-reference-schematic.png'));(ROOT/'artifacts/tramonto-rc-reference-circuit.json').write_text(json.dumps(c));(ROOT/'artifacts/tramonto-rc-reference-schematic.svg').write_text(await svg.evaluate('e=>e.outerHTML'))
                        await page.reload();await page.locator('#noteEditor').wait_for(state='visible');await page.locator('[data-pane=circuit]').click();assert await svg.locator('[data-component-id="XSC1"] [data-port]').count()==4;assert saved()['circuit']==c
                await page.locator('[data-pane=draw]').click();canvas=page.locator('#drawingCanvas')
                for tool in ('pencil','marker','highlighter','line','arrow','double-arrow','rectangle','ellipse','triangle','diamond'):
                    await page.locator('[data-draw-tool='+tool+']').click();await canvas.scroll_into_view_if_needed();box=await canvas.bounding_box();await page.mouse.move(box['x']+100*box['width']/1000,box['y']+100*box['height']/640);await page.mouse.down();await page.mouse.move(box['x']+300*box['width']/1000,box['y']+250*box['height']/640,steps=5);await page.mouse.up()
                await save();assert len(saved()['drawing']['strokes'])==10
                await page.locator('#fourierWave').select_option('triangle');await page.locator('#drawFourier').click();await save();before=saved()['drawing']['strokes'];assert len(before)>10;await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert saved()['drawing']['strokes']==before
                await page.locator('[data-pane=text]').click()
                for font in ('book','classic','humanist','geometric','slab','hand','script','typewriter'):
                    await page.locator('#noteFont').select_option(font);await save();assert saved()['font']==font
                # Unicode shortcuts, searchable math symbols and genuinely nested exponents.
                editor=page.locator('#richEditor');await editor.fill('');await editor.press_sequentially('V <= 5 >= 2 ~= 3 != 4 +- 1 -> x ');assert 'V ≤ 5 ≥ 2 ≈ 3 ≠ 4 ± 1 → x' in await editor.inner_text()
                await editor.press_sequentially(r'\gamma \beta \Omega \micro \nano ');assert 'γ β Ω μ n' in await editor.inner_text()
                await editor.fill('x');await editor.press('End');await page.locator('#textSuperscript').click();await page.keyboard.type('2');await page.locator('#textSuperscript').click();await page.keyboard.type('3');assert await editor.locator('sup sup').count()==1
                await page.locator('#textScriptOut').click();await page.keyboard.type('4');await page.locator('#textBaseline').click();await page.keyboard.type(' + y');await page.locator('#textSubscript').click();await page.keyboard.type('n');await page.locator('#textBaseline').click()
                before=await page.locator('#a4Frame').bounding_box();await page.locator('#textMathSymbols summary').click();after=await page.locator('#a4Frame').bounding_box();assert abs(before['y']-after['y'])<1 and abs(before['height']-after['height'])<1
                dock=await page.locator('#pane-textTools').bounding_box();assert dock['x']>=after['x']+after['width'];await page.locator('#textSymbolSearch').fill('freccia su');await page.locator('[data-math-symbol="↑"]').click();await page.locator('#textSymbolSearch').fill('ohm');await page.locator('[data-math-symbol="Ω"]').first.click();await save();html=saved()['html'];assert '<sup>' in html and '<sup>3</sup>' in html and '<sub>' in html and '↑' in html and 'Ω' in html,html
                await page.reload();await page.locator('#noteEditor').wait_for(state='visible');assert await page.locator('#richEditor sup sup').count()==1
                assert await page.evaluate("async()=>{await document.fonts.load('16px \"Tramonto Hand\"');return document.fonts.check('16px \"Tramonto Hand\"')}")
                await page.locator('.portal-transition').wait_for(state='detached');await page.set_viewport_size({'width':390,'height':844});await page.locator('[data-pane=circuit]').click();assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');before=await svg.evaluate('e=>({y:e.getBoundingClientRect().top+scrollY,width:e.clientWidth,height:e.clientHeight})');await page.locator('#pane-circuit>.tool-dock-toggle').click();assert await page.locator('#pane-circuitTools').is_visible();after=await svg.evaluate('e=>({y:e.getBoundingClientRect().top+scrollY,width:e.clientWidth,height:e.clientHeight})');assert before==after,(before,after);await page.locator('#componentSearch').fill('sommatore');await page.locator('[data-component=summer]').click();assert not await page.locator('#pane-circuitTools').is_visible();await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-schematic-mobile.png'),full_page=True)
                await page.set_viewport_size({'width':1440,'height':1100});await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-schematic-tools.png'),full_page=True)
                await page.locator('[data-pane=draw]').click();await page.screenshot(path=str(ROOT/'artifacts'/'tramonto-drawing-tools.png'),full_page=True)
                await browser.close()
        finally:await server.close();store.close()
        assert not errors,errors
    print('Visual editors OK: math symbols/shortcuts/nested exponents/local fonts, icons/search/categories, automatic wires/corners/preview/orthogonality, colour+reload, cancel/backspace, branches+undo, oscillator netlists, brushes+shapes/Fourier persistence, eight fonts, mobile fit.')

if __name__=='__main__':asyncio.run(main())
