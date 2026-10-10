"""Exercise overflow at the caret, ordered page controls, and persistent highlighting."""
import asyncio
import shutil
import sys
import tempfile
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
    browser=await p.chromium.launch();context=await browser.new_context(viewport={'width':1600,'height':1100});page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto(str(server.make_url('/'))+'#web_key='+keys.issue(1,1,'web'));await page.locator('#dashboard').wait_for(state='visible');await page.goto(str(server.make_url('/tramonto')));await page.locator('#newNote').click();await page.locator('#noteEditor').wait_for(state='visible')
    first=await page.evaluate('doc.id')
    sentinel=await page.evaluate("async()=>{const p=await api('/api/tramonto/notes','POST',{notebook_id:bookId,title:'Pagina già esistente',content:{html:'<p>CONTENUTO FINALE</p>'}});return p.id;}")
    await page.evaluate("()=>{const e=$('richEditor');e.innerHTML=Array.from({length:34},(_,i)=>'<p>Riga '+(i+1)+'</p>').join('');changed();e.focus();const r=document.createRange();r.selectNodeContents(e.lastChild);r.collapse(false);getSelection().removeAllRanges();getSelection().addRange(r);}")
    assert await page.locator('#richEditor').evaluate('e=>e.scrollHeight<=e.clientHeight+2')
    await page.locator('#richEditor').press('Enter');await page.keyboard.type('SCRITTO NELLA PAGINA DOPO')
    await page.wait_for_function('(id)=>doc.id!==id&&!opening&&!document.querySelector("#noteEditor").inert',arg=first)
    listing=await page.evaluate("async()=>(await api('/api/tramonto/notes?notebook='+bookId)).notes")
    assert [p['id'] for p in listing]==[first,await page.evaluate('doc.id'),sentinel],listing
    assert await page.evaluate('doc.page_number')==2
    assert 'SCRITTO NELLA PAGINA DOPO' in await page.locator('#richEditor').inner_text()
    assert await page.locator('#richEditor').evaluate('e=>e.scrollHeight<=e.clientHeight+2')
    print('Typing overflow: continuation inserted between existing pages.')

    # Inserting several pages into the middle keeps the caret at the pasted text,
    # even when old text continues onto another page after it.
    await page.evaluate('(id)=>tramontoOpenPage(id)',first)
    await page.evaluate("()=>{const e=$('richEditor');e.innerHTML=Array.from({length:30},(_,i)=>'<p>ORIGINALE '+(i+1)+'</p>').join('');changed();e.focus();const r=document.createRange();r.selectNodeContents(e.children[4]);r.collapse(false);getSelection().removeAllRanges();getSelection().addRange(r);const data=new DataTransfer();data.setData('text/html',Array.from({length:90},(_,i)=>'<p>INCOLLATO '+(i+1)+'</p>').join(''));e.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));}")
    await page.wait_for_function('(id)=>doc.id!==id&&!opening&&!document.querySelector("#noteEditor").inert',arg=first)
    current=await page.evaluate('doc.id');listing=await page.evaluate("async()=>(await api('/api/tramonto/notes?notebook='+bookId)).notes")
    assert listing[-1]['id']==sentinel
    assert listing.index(next(p for p in listing if p['id']==current))<len(listing)-3,listing
    await page.keyboard.type('__CURSORE__');await page.evaluate('TramontoTools.saveDoc()')
    text=await page.evaluate("async()=>{const pages=(await api('/api/tramonto/notes?notebook='+bookId)).notes;let text='';for(const p of pages){const record=await api('/api/tramonto/notes/'+p.id);const e=document.createElement('div');e.innerHTML=record.content.html;text+=e.textContent;}return text;}")
    assert text.count('__CURSORE__')==1
    assert text.index('INCOLLATO 90')<text.index('__CURSORE__')<text.index('ORIGINALE 6'),text
    assert text.index('ORIGINALE 30')<text.index('CONTENUTO FINALE')
    print('Paste overflow: original content preserved and caret remains at insertion.')

    await page.locator('#insertPageBefore').click();await page.wait_for_function('(id)=>doc.id!==id&&!opening',arg=current)
    blank=await page.evaluate('doc.id');listing=await page.evaluate("async()=>(await api('/api/tramonto/notes?notebook='+bookId)).notes")
    assert listing[await page.evaluate('doc.page_number')]['id']==current
    await page.locator('#richEditor').fill('Testo evidenziato e normale');await page.locator('#richEditor').press('ControlOrMeta+a');await page.locator('#textHighlightColor').select_option('#bce8b5');await page.locator('#textHighlight').click();await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible')
    assert await page.evaluate('doc.id')==blank
    assert await page.locator('#richEditor span[style]').count()>0
    assert await page.locator('#richEditor span[style]').first.evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(188, 232, 181)'
    await page.evaluate("()=>{const e=$('richEditor');e.focus();const t=e.querySelector('span').firstChild,r=document.createRange();r.setStart(t,6);r.setEnd(t,17);getSelection().removeAllRanges();getSelection().addRange(r);}")
    await page.locator('#removeTextHighlight').click();await page.evaluate('TramontoTools.saveDoc()');await page.reload();await page.locator('#noteEditor').wait_for(state='visible')
    colors=await page.locator('#richEditor').evaluate("e=>{const w=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);let t,result=[];while(t=w.nextNode())result.push([t.textContent,getComputedStyle(t.parentElement).backgroundColor]);return result;}")
    assert any('evidenziato' in text and color=='rgba(0, 0, 0, 0)' for text,color in colors),colors
    assert any(color=='rgb(188, 232, 181)' for _,color in colors),colors
    await page.set_viewport_size({'width':390,'height':844});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.set_viewport_size({'width':1600,'height':1100})
    print('Highlighter: color and partial removal survive reload; mobile width fits.')
    await page.locator('.page-more summary').click();page.once('dialog',lambda dialog:dialog.accept());await page.locator('#deleteNote').click();await page.wait_for_function('(id)=>doc&&doc.id!==id&&!opening',arg=blank);assert await page.evaluate('doc.id')==current
    await page.locator('#insertPageAfter').click();await page.wait_for_function('(id)=>doc.id!==id&&!opening',arg=current)
    after=await page.evaluate('doc.id');listing=await page.evaluate("async()=>(await api('/api/tramonto/notes?notebook='+bookId)).notes")
    assert listing[next(i for i,p in enumerate(listing) if p['id']==current)+1]['id']==after
    await page.locator('.page-more summary').click();page.once('dialog',lambda dialog:dialog.accept());await page.locator('#deleteNote').click();await page.wait_for_function('(id)=>doc&&doc.id!==id&&!opening',arg=after)
    assert not errors,errors
    await browser.close()
  finally:await server.close();store.close()
 print('Notebook pages OK: typing, paste, caret, page insertion/deletion, highlighting and reload.')

if __name__=='__main__':asyncio.run(main())
