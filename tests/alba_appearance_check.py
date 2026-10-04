"""Approved Alba skins work at login and in chat, persist and fit mobile menus."""
import asyncio,shutil,sys,tempfile
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
from browser_check import TestModel

async def main():
 (ROOT/'artifacts').mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder)
  for name in ('web.html','web.css','web.js'):shutil.copy2(ROOT/name,root/name)
  settings=Settings(root=root,admins=(1,));store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));service=Service(store,settings,keys,Engine(store,settings,TestModel()),Backups(store,settings));store.register(1,'Admin');server=TestServer(web_app(service));await server.start_server();errors=[]
  try:
   async with async_playwright() as p:
    browser=await p.chromium.launch();page=await browser.new_page(viewport={'width':1440,'height':1100},color_scheme='light');page.on('pageerror',lambda e:errors.append(e.stack));page.on('console',lambda m:errors.append(m.text) if m.type=='error' and '403' not in m.text else None)
    await page.goto(str(server.make_url('/')));await page.locator('#login').wait_for(state='visible');await page.locator('#appearanceSettings summary').click();await page.locator('#surfaceStyle').select_option('clay');await page.locator('#appearanceTheme').select_option('gray');await page.locator('#appearancePalette').select_option('graphite');await page.wait_for_timeout(300);assert await page.locator('#login').evaluate('e=>getComputedStyle(e).borderTopLeftRadius')=='26px';await page.screenshot(path=str(ROOT/'artifacts/alba-clay-login.png'),full_page=True)
    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');assert await page.locator('#surfaceStyle').input_value()=='clay';assert await page.locator('#appearanceTheme').input_value()=='gray';assert await page.locator('#appearancePalette').input_value()=='graphite'
    await page.locator('#appearanceSettings summary').click()
    for theme in ('light','dark','gray','black'):
     await page.locator('#appearanceTheme').select_option(theme)
     for palette in ('sage','graphite','ocean','violet','rose','amber'):
      await page.locator('#appearancePalette').select_option(palette)
      ratios=await page.evaluate('''()=>{const s=getComputedStyle(document.documentElement),rgb=v=>{const c=v.match(/[\\d.]+/g).slice(0,3).map(Number);return v.startsWith('color(srgb')?c.map(x=>x*255):c;},luma=c=>rgb(c).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((v,x,i)=>v+x*[.2126,.7152,.0722][i],0),color=k=>{const e=document.createElement('i');e.style.color=s.getPropertyValue(k);document.body.append(e);const c=getComputedStyle(e).color;e.remove();return c;},ratio=(a,b)=>{const x=luma(color(a)),y=luma(color(b));return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);};return[ratio('--text','--surface'),ratio('--muted','--surface'),ratio('--accent','--accent-text'),ratio('--heat3','--heat-text')];}''');assert min(ratios)>=4.5,(theme,palette,ratios)
    for skin in ('clay','cyber','brutal','scrap','surreal'):
     await page.locator('#surfaceStyle').select_option(skin);await page.set_viewport_size({'width':390,'height':844});await page.wait_for_timeout(100);assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),skin;box=await page.locator('.appearance-popover').bounding_box();assert box['x']>=0 and box['x']+box['width']<=390 and box['y']+box['height']<=844,(skin,box);await page.set_viewport_size({'width':1440,'height':1100})
    await page.locator('#surfaceStyle').select_option('cyber');await page.locator('#appearanceTheme').select_option('black');await page.locator('#appearancePalette').select_option('ocean');await page.keyboard.press('Escape');await page.wait_for_timeout(300);await page.screenshot(path=str(ROOT/'artifacts/alba-cyber-black.png'),full_page=True);await page.reload();await page.locator('#dashboard').wait_for(state='visible');assert await page.locator('#surfaceStyle').input_value()=='cyber';assert await page.locator('#appearanceTheme').input_value()=='black';assert await page.locator('#appearancePalette').input_value()=='ocean';assert await page.locator('#themeToggle').get_attribute('aria-pressed')=='true';assert await page.locator('meta[name=theme-color]').get_attribute('content')=='#000000'
    await page.locator('#themeToggle').click();assert await page.locator('#appearanceTheme').input_value()=='light';await page.locator('#themeToggle').click();assert await page.locator('#appearanceTheme').input_value()=='dark'
    await page.locator('#appearanceSettings summary').click();await page.locator('#motionSettings summary').click();await page.wait_for_timeout(100);assert not await page.locator('#appearanceSettings').evaluate('e=>e.open');await page.keyboard.press('Escape');await page.locator('#message').fill('Prova il tema nuovo');await page.locator('#send').click();await page.locator('.bubble.assistant').filter(has_text='Possiamo partire').wait_for();await page.set_viewport_size({'width':390,'height':844});await page.locator('#appearanceSettings summary').click();await page.screenshot(path=str(ROOT/'artifacts/alba-appearance-mobile.png'),full_page=True);await browser.close()
  finally:await server.close();store.close()
  assert not errors,errors
 print('Alba appearance OK: login/chat, five approved skins, 24 palette/contrast combinations, mobile menu, remembered preferences and quick theme toggle.')

if __name__=='__main__':asyncio.run(main())
