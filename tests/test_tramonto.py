import base64
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from aiohttp.test_utils import TestClient,TestServer
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys,secret_file
from service import Service
from store import Store,Scope
from tramonto import content_data

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=')

class TramontoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); root=Path(self.tmp.name)
        for name in ('tramonto.html','tramonto.js','tramonto.css','tramonto-lab.js'): shutil.copy2(Path(__file__).resolve().parents[1]/name,root/name)
        self.settings=Settings(root=root,admins=(1,4),allowed=(2,3))
        self.store=Store(self.settings.data/'alba.sqlite3'); self.keys=Keys(self.store,secret_file(self.settings.data/'auth.key'))
        self.backups=Backups(self.store,self.settings)
        self.service=Service(self.store,self.settings,self.keys,Engine(self.store,self.settings,None),self.backups)
        for uid in (1,2,3,4): self.store.register(uid,'Persona '+str(uid))
        self.headers={}
        for uid in (1,2,3,4):
            cookie,csrf=self.keys.create_session(uid,True)
            self.headers[uid]={'Cookie':'session='+cookie,'X-CSRF-Token':csrf}
        self.client=TestClient(TestServer(web_app(self.service))); await self.client.start_server()
        response=await self.req('/notebooks','POST',{'title':'Matematica'})
        self.book=(await response.json())['id']
        response=await self.req('/notes','POST',{'notebook_id':self.book,'title':'Limiti'})
        self.note=(await response.json())['id']
    async def asyncTearDown(self):
        await self.client.close(); self.store.close(); self.tmp.cleanup()
    async def req(self,path,method='GET',body=None,uid=1,raw=False,headers=None):
        return await self.client.request(method,path if raw else '/api/tramonto'+path,json=body,headers=self.headers[uid] if headers is None else headers,allow_redirects=False)
    async def document(self,note=None,uid=1): return await (await self.req('/notes/'+str(note or self.note),uid=uid)).json()
    async def update(self,changes=None):
        value=await self.document(); value.update(changes or {}); return await self.req('/notes/'+str(self.note),'PUT',value)
    async def upload(self,data=PNG,note=None,uid=1):
        return await self.client.post('/api/tramonto/notes/'+str(note or self.note)+'/images',data=data,headers={**self.headers[uid],'Content-Type':'image/png','X-Image-Name':'foto.png'})

    async def test_01_unauthenticated_page_redirects_to_login(self):
        response=await self.req('/tramonto',raw=True,headers={}); self.assertEqual(response.status,302); self.assertEqual(response.headers['Location'],'/?next=tramonto')

    async def test_font_presets_resume_limit_and_versions(self):
        font={'name':'Calligrafia','weight':10,'glyphs':{'A':[[[20,30],[40,50]]]}}
        response=await self.req('/fonts','POST',{'font':font});self.assertEqual(response.status,201);preset=await response.json()
        font['glyphs']['B']=[[[60,70]]];font['name']='Calligrafia aggiornata'
        response=await self.req('/fonts/'+preset['id'],'PUT',{'font':font,'version':1});self.assertEqual(response.status,200)
        self.assertEqual((await self.req('/fonts/'+preset['id'],'PUT',{'font':font,'version':1})).status,409)
        saved=(await (await self.req('/fonts')).json())['fonts'];self.assertEqual(saved[0]['font'],font);self.assertEqual(saved[0]['version'],2)
        for n in range(9):self.assertEqual((await self.req('/fonts','POST',{'font':{'name':str(n),'weight':10,'glyphs':{}}})).status,201)
        self.assertEqual((await self.req('/fonts','POST',{'font':font})).status,403)
        self.assertEqual((await self.req('/fonts/'+preset['id'],'DELETE',{'version':1})).status,409)
        self.assertEqual((await self.req('/fonts/'+preset['id'],'DELETE',{'version':2})).status,200)
        self.assertEqual((await self.req('/fonts','POST',{'font':font})).status,201)

    async def test_legacy_page_fonts_recovered_once_without_changing_notes(self):
        font={'name':'Giada','weight':10,'glyphs':{'A':[[[20,30],[40,50]]]}}
        value=await self.document();value['content']['custom_font']=font;value['content']['font']='custom'
        self.assertEqual((await self.req('/notes/'+str(self.note),'PUT',value)).status,200)
        original=await self.document()
        saved=(await (await self.req('/fonts')).json())['fonts'];self.assertEqual(len(saved),1);self.assertEqual(saved[0]['font'],font)
        self.assertEqual(await self.document(),original)
        self.assertEqual((await (await self.req('/fonts',uid=4)).json())['fonts'],[])
        self.assertEqual((await self.req('/fonts/'+saved[0]['id'],'DELETE',{'version':1})).status,200)
        self.assertEqual((await (await self.req('/fonts')).json())['fonts'],[])

    async def test_font_presets_privacy_validation_and_backup(self):
        font={'name':'Privato','weight':10,'glyphs':{'A':[[[20,30],[40,50]]]},'templates':[{'id':'formula','name':'Formula','strokes':[[[12,34]]]}]}
        preset=await (await self.req('/fonts','POST',{'font':font})).json()
        self.assertEqual((await (await self.req('/fonts',uid=4)).json())['fonts'],[])
        self.assertEqual((await self.req('/fonts',uid=2)).status,403)
        for method in ('PUT','DELETE'):self.assertEqual((await self.req('/fonts/'+preset['id'],method,{'font':font,'version':1},uid=4)).status,403)
        self.assertEqual((await self.req('/fonts','POST',{'font':font},headers={'Cookie':self.headers[1]['Cookie']})).status,403)
        self.assertEqual((await self.req('/fonts','POST',{'font':{'glyphs':{'A':[[[301,0]]]}}})).status,403)
        self.assertEqual((await self.req('/fonts','POST',{'font':font,'user_id':4})).status,403)
        backup=self.backups.create('manual');destination=self.settings.data/'fonts-restored.sqlite3';self.backups.restore(backup,destination)
        restored=Store(destination)
        try:self.assertEqual(json.loads(restored.rows('SELECT content FROM font_presets')[0]['content']),font)
        finally:restored.close()
        self.store.forget_user(1);self.assertEqual(self.store.rows('SELECT * FROM font_presets'),[])
    async def test_02_user_cannot_open_page_or_assets(self):
        for path in ('/tramonto','/tramonto-assets/tramonto.js','/tramonto-assets/tramonto.css'):
            self.assertEqual((await self.req(path,uid=2,raw=True)).status,403)
    async def test_03_user_cannot_call_any_notebook_api(self):
        for method,path,body in (('GET','/notebooks',None),('POST','/notebooks',{'title':'No'}),('DELETE','/notebooks/'+str(self.book),None),('GET','/notes',None),('GET','/notes/'+str(self.note),None),('PUT','/notes/'+str(self.note),{}),('GET','/images/1',None)):
            self.assertEqual((await self.req(path,method,body,uid=2)).status,403)
    async def test_04_admin_page_and_csp(self):
        response=await self.req('/tramonto',raw=True); self.assertEqual(response.status,200)
        self.assertIn('Tramonto',await response.text()); self.assertIn("script-src 'self'",response.headers['Content-Security-Policy']); self.assertIn("style-src-attr 'unsafe-inline'",response.headers['Content-Security-Policy'])
    async def test_05_books_are_separated_between_admins(self):
        self.assertEqual((await (await self.req('/notebooks',uid=4)).json())['notebooks'],[])
        self.assertEqual((await self.req('/notes?notebook='+str(self.book),uid=4)).status,403)
    async def test_06_other_admin_cannot_read_update_delete_notes(self):
        for method in ('GET','PUT','DELETE'):
            self.assertEqual((await self.req('/notes/'+str(self.note),method,{} if method=='PUT' else None,uid=4)).status,403)
    async def test_07_forged_owner_and_query_rejected(self):
        for body in ({'title':'No','user_id':4},{'title':'No','scope':'group'},{'title':'No','owner_id':4}):
            self.assertEqual((await self.req('/notebooks','POST',body)).status,403)
        for path in ('/notebooks?user_id=4','/notes?user_id=4'):
            self.assertEqual((await self.req(path)).status,403)
    async def test_08_csrf_required_for_mutations(self):
        headers={'Cookie':self.headers[1]['Cookie']}
        response=await self.req('/notebooks','POST',{'title':'No'},headers=headers); self.assertEqual(response.status,403)
    async def test_09_save_and_search(self):
        response=await self.update({'title':'Il seno','subject':'matematica'}); self.assertEqual(response.status,200)
        values=(await (await self.req('/notes?q=seno')).json())['notes']; self.assertEqual([v['id'] for v in values],[self.note])
    async def test_10_concurrent_edits_keep_first_and_return_conflict(self):
        value=await self.document(); value['title']='Primo'; self.assertEqual((await self.req('/notes/'+str(self.note),'PUT',value)).status,200)
        value['title']='Obsoleto'; response=await self.req('/notes/'+str(self.note),'PUT',value)
        self.assertEqual(response.status,409); self.assertEqual((await response.json())['code'],'version_conflict'); self.assertEqual((await self.document())['title'],'Primo')

    async def test_page_insertion_order_numbers_and_deletion(self):
        async def create(**placement):
            response=await self.req('/notes','POST',{'notebook_id':self.book,**placement})
            self.assertEqual(response.status,201);return (await response.json())['id']
        last=await create();before=await create(before_id=self.note);middle=await create(after_id=self.note)
        listing=(await (await self.req('/notes?notebook='+str(self.book))).json())['notes']
        self.assertEqual([p['id'] for p in listing],[before,self.note,middle,last])
        self.assertEqual([p['page_number'] for p in listing],[1,2,3,4])
        self.assertEqual((await self.document(middle))['page_number'],3)
        await self.req('/notes/'+str(middle),'DELETE')
        self.assertEqual((await self.document(last))['page_number'],3)
        book=(await (await self.req('/notebooks','POST',{'title':'Altro'})).json())['id']
        response=await self.req('/notes','POST',{'notebook_id':book,'before_id':self.note})
        self.assertEqual(response.status,403)
        response=await self.req('/notes','POST',{'notebook_id':self.book,'before_id':before,'after_id':last})
        self.assertEqual(response.status,403)
        response=await self.req('/notes','POST',{'notebook_id':self.book,'after_id':True})
        self.assertEqual(response.status,403)
        self.assertEqual((await self.req('/notes','POST',{'notebook_id':self.book,'after_id':self.note},uid=4)).status,403)

    async def test_pagination_is_atomic_and_inserts_before_following_page(self):
        last=(await (await self.req('/notes','POST',{'notebook_id':self.book,'title':'Pagina seguente','content':{'html':'<p>Testo da conservare</p>'}})).json())['id']
        image=(await (await self.upload()).json())['id'];value=await self.document()
        value['content'].update(html='<p>Prima</p><p>Seconda</p>',images=[image],paper='ruled',font_size=20)
        self.assertEqual((await self.req('/notes/'+str(self.note),'PUT',value)).status,200)
        value=await self.document();pages=['<p>Prima</p>','<p><span style="background-color: #fff19c;">Seconda</span><img src="/api/tramonto/images/'+str(image)+'" width="200"></p>','<p>Terza</p>']
        response=await self.req('/notes/'+str(self.note)+'/paginate','POST',{'version':value['version']-1,'pages':pages})
        self.assertEqual(response.status,409)
        self.assertEqual(await self.document(),value)
        response=await self.req('/notes/'+str(self.note)+'/paginate','POST',{'version':value['version'],'pages':[pages[0],'<img src="/api/tramonto/images/999999">']})
        self.assertEqual(response.status,403);self.assertEqual(await self.document(),value)
        response=await self.req('/notes/'+str(self.note)+'/paginate','POST',{'version':value['version'],'pages':pages})
        self.assertEqual(response.status,200);ids=(await response.json())['ids']
        listing=(await (await self.req('/notes?notebook='+str(self.book))).json())['notes']
        self.assertEqual([p['id'] for p in listing],ids+[last]);self.assertEqual([p['page_number'] for p in listing],[1,2,3,4])
        self.assertEqual((await self.document())['content']['html'],pages[0])
        second=await self.document(ids[1]);self.assertEqual(second['content']['paper'],'ruled');self.assertEqual(second['content']['font_size'],20)
        copied=second['content']['images'][0];self.assertNotEqual(copied,image)
        self.assertEqual(await (await self.req('/images/'+str(copied))).read(),PNG)
        self.assertIn('background-color: #fff19c;',second['content']['html'])
        self.assertEqual((await self.document(last))['content']['html'],'<p>Testo da conservare</p>')
        self.assertEqual((await self.req('/notes/'+str(self.note)+'/paginate','POST',{'version':value['version'],'pages':pages},uid=4)).status,403)

    async def test_failed_image_copy_does_not_shift_or_create_pages(self):
        image=(await (await self.upload()).json())['id']
        last=(await (await self.req('/notes','POST',{'notebook_id':self.book})).json())['id']
        original=self.store.rows('SELECT id,position FROM notes ORDER BY position')
        response=await self.req('/notes','POST',{'notebook_id':self.book,'after_id':self.note,'copy_images_from':last,'content':{'html':'<img src="/api/tramonto/images/'+str(image)+'">','images':[image]}})
        self.assertEqual(response.status,403);self.assertEqual(self.store.rows('SELECT id,position FROM notes ORDER BY position'),original)

    def test_highlights_keep_only_safe_palette_backgrounds(self):
        from tramonto import rich_text
        self.assertEqual(rich_text('<span style="background-color: #fff19c;">Giallo <b>grassetto</b></span>'),'<span style="background-color: #fff19c;">Giallo <b>grassetto</b></span>')
        for style in ('background-color: #000000;','background-color: #fff19c;position:fixed','background-image:url(https://bad.test)','color:red'):
            self.assertEqual(rich_text('<span style="'+style+'" onclick="bad()">Testo</span>'),'<span>Testo</span>')

    def test_legacy_page_order_migrates_once(self):
        import sqlite3
        from store import SCHEMA
        path=Path(self.tmp.name)/'legacy.sqlite3';connection=sqlite3.connect(path)
        connection.executescript(SCHEMA.replace(',position INTEGER NOT NULL DEFAULT 0',''))
        for i in (3,9):connection.execute('INSERT INTO notes(id,user_id,notebook_id,title,subject,content,created,updated) VALUES(?,1,1,?,\'generale\',\'{}\',0,0)',(i,str(i)))
        connection.commit();connection.close();legacy=Store(path)
        self.assertEqual(legacy.rows('SELECT id,position FROM notes ORDER BY position'),[{'id':3,'position':3},{'id':9,'position':9}])
        legacy.execute('UPDATE notes SET position=1 WHERE id=9');legacy.close();legacy=Store(path)
        self.assertEqual([p['id'] for p in legacy.rows('SELECT id FROM notes ORDER BY position')],[9,3]);legacy.close()
    async def test_11_html_is_sanitized_on_server(self):
        value=await self.document(); value['content']['html']='<p onclick="alert(1)">Ciao<img src=x onerror=alert(2)></p><script>alert(3)</script><iframe src="https://bad.test"></iframe>'
        self.assertEqual((await self.req('/notes/'+str(self.note),'PUT',value)).status,200)
        html=(await self.document())['content']['html']; self.assertIn('<p>Ciao</p>',html)
        for bad in ('onclick','<img','<script','<iframe','onerror','https://'): self.assertNotIn(bad,html)
    async def test_12_font_paper_formulas_persist(self):
        value=await self.document(); value['content'].update({'font':'mono','paper':'grid','formulas':[r'\lim_{x\to 0}\frac{\sin x}{x}=1']})
        await self.req('/notes/'+str(self.note),'PUT',value); stored=(await self.document())['content']; self.assertEqual(stored['font'],'mono'); self.assertEqual(stored['paper'],'grid'); self.assertEqual(stored['formulas'],value['content']['formulas'])
    async def test_13_graph_and_limit_configuration_persist(self):
        value=await self.document(); value['content']['graph']['expressions']=['sin(x)','cos(x)','x^2']; value['content']['limit']['point']='+inf'
        await self.req('/notes/'+str(self.note),'PUT',value); self.assertEqual((await self.document())['content']['graph']['expressions'],['sin(x)','cos(x)','x^2'])
    async def test_14_drawing_strokes_persist(self):
        value=await self.document(); value['content']['drawing']['strokes']=[{'color':'#ff8844','size':3,'points':[[20,30],[50,70]]}]
        await self.req('/notes/'+str(self.note),'PUT',value); self.assertEqual((await self.document())['content']['drawing'],value['content']['drawing'])
    async def test_15_circuit_components_and_wires_persist(self):
        value=await self.document(); circuit={'components':[{'id':key,'type':'resistor','x':100*i,'y':200,'rotation':90,'label':key,'value':'10k'} for i,key in enumerate(('a','b'),1)],'wires':[{'id':'w1','from':{'component':'a','port':1},'to':{'component':'b','port':0}}]}
        value['content']['circuit']=circuit; await self.req('/notes/'+str(self.note),'PUT',value); self.assertEqual((await self.document())['content']['circuit'],circuit)
    async def test_16_png_upload_fetch_and_save(self):
        response=await self.upload(); self.assertEqual(response.status,201); image=(await response.json())['id']
        value=await self.document(); value['content']['images']=[image]; await self.req('/notes/'+str(self.note),'PUT',value)
        response=await self.req('/images/'+str(image)); self.assertEqual(await response.read(),PNG); self.assertEqual(response.headers['Content-Type'],'image/png')
    async def test_17_svg_and_html_upload_rejected(self):
        for data in (b'<svg onload="alert(1)"></svg>',b'<html>hello</html>'):
            self.assertEqual((await self.upload(data)).status,403)
    async def test_18_image_owner_isolation(self):
        image=(await (await self.upload()).json())['id']
        for uid in (2,4):
            for method in ('GET','DELETE'): self.assertEqual((await self.req('/images/'+str(image),method,uid=uid)).status,403)
            self.assertEqual((await self.upload(uid=uid)).status,403)
    async def test_19_image_cannot_be_attached_to_another_note(self):
        image=(await (await self.upload()).json())['id']; other=(await (await self.req('/notes','POST',{'notebook_id':self.book})).json())['id']
        value=await self.document(other); value['content']['images']=[image]
        self.assertEqual((await self.req('/notes/'+str(other),'PUT',value)).status,403)
    async def test_20_delete_image_updates_note_version(self):
        image=(await (await self.upload()).json())['id']; value=await self.document(); value['content']['images']=[image]; await self.req('/notes/'+str(self.note),'PUT',value)
        version=(await self.document())['version']; await self.req('/images/'+str(image),'DELETE')
        value=await self.document(); self.assertEqual(value['content']['images'],[]); self.assertEqual(value['version'],version+1)
    async def test_21_delete_notebook_cascades(self):
        await self.upload(); await self.req('/notebooks/'+str(self.book),'DELETE')
        for table in ('notebooks','notes','note_images'): self.assertEqual(self.store.rows('SELECT * FROM '+table),[])
    async def test_22_notes_are_not_ai_memories(self):
        await self.update({'title':'Il segreto del quaderno'}); self.assertEqual(self.store.profile(1),[])
        self.assertEqual(self.store.rows('SELECT * FROM memories'),[]); self.assertEqual(self.store.rows('SELECT * FROM messages'),[])
    async def test_23_forget_erases_notebooks_and_images(self):
        await self.upload(); self.store.forget_user(1)
        for table in ('notebooks','notes','note_images','web_sessions'): self.assertEqual(self.store.rows('SELECT * FROM '+table+' WHERE user_id=1'),[])
    async def test_24_encrypted_backup_restores_notes_and_images(self):
        await self.upload(); source=self.backups.create('manual'); restored=self.settings.data/'restored.sqlite3'; self.backups.restore(source,restored)
        db=Store(restored)
        try:
            self.assertEqual(db.rows('SELECT title FROM notes')[0]['title'],'Limiti'); self.assertEqual(db.rows('SELECT data FROM note_images')[0]['data'],PNG); self.assertEqual(db.rows('SELECT * FROM web_sessions'),[])
        finally: db.close()
    async def test_25_move_note_only_to_own_notebook(self):
        book=(await (await self.req('/notebooks','POST',{'title':'Privato'},uid=4)).json())['id']
        self.assertEqual((await self.update({'notebook_id':book})).status,403)
    async def test_26_rename_notebook(self):
        self.assertEqual((await self.req('/notebooks/'+str(self.book),'PATCH',{'title':'Telecom'})).status,200)
        self.assertEqual((await (await self.req('/notebooks')).json())['notebooks'][0]['title'],'Telecom')
    def test_27_invalid_graph_ranges_and_nan_rejected(self):
        for key,value in (('x_min',float('nan')),('x_max',-10),('y_min',True)):
            data=content_data({}); data['graph'][key]=value
            with self.assertRaises(ValueError): content_data(data)
    def test_28_invalid_drawing_rejected(self):
        data=content_data({}); data['drawing']['strokes']=[{'color':'#ffffff','size':3,'points':[[1001,20]]}]
        with self.assertRaises(ValueError): content_data(data)
    def test_29_malformed_types_raise_validation_error(self):
        for key in ('font','paper','graph','drawing','circuit','images'):
            data=content_data({}); data[key]=[] if key!='images' else [True]
            with self.assertRaises(ValueError): content_data(data)
    def test_30_unknown_circuit_endpoint_rejected(self):
        data=content_data({}); data['circuit']['wires']=[{'id':'a','from':{'component':'missing','port':0},'to':{'component':'missing','port':1}}]
        with self.assertRaises(ValueError): content_data(data)


    async def test_31_formula_replacement_keeps_image_id_and_checks_note_owner(self):
        image=(await (await self.upload()).json())['id']
        value=await self.document();value['content'].update(images=[image],html='<img src="/api/tramonto/images/'+str(image)+'?v=123" width="240" data-latex="x&lt;y" onerror="bad()">')
        self.assertEqual((await self.req('/notes/'+str(self.note),'PUT',value)).status,200)
        stored=await self.document();self.assertIn('data-latex="x&lt;y"',stored['content']['html']);self.assertNotIn('onerror',stored['content']['html'])
        response=await self.client.post('/api/tramonto/notes/'+str(self.note)+'/images',data=PNG,headers={**self.headers[1],'X-Replace-Image':str(image)})
        self.assertEqual(response.status,200);self.assertEqual((await response.json())['id'],image);self.assertEqual(len(self.store.rows('SELECT id FROM note_images')),1)
        other=(await (await self.req('/notes','POST',{'notebook_id':self.book})).json())['id']
        for uid,note in ((4,self.note),(1,other)):
            response=await self.client.post('/api/tramonto/notes/'+str(note)+'/images',data=PNG,headers={**self.headers[uid],'X-Replace-Image':str(image)})
            self.assertEqual(response.status,403)

    def test_32_custom_font_and_drawing_text_validation(self):
        data=content_data({});data.update(font='custom',custom_font={'name':'Font di prova','weight':10,'glyphs':{'A':[[[10,240],[150,40],[280,240]]]}})
        data['drawing']['strokes']=[{'tool':'text','color':'#123456','size':3,'points':[[10,20]],'text':'A\nseconda riga','font':'custom','text_size':32}]
        self.assertEqual(content_data(data),data)
        for bad in (float('nan'),301,True):
            broken=copy.deepcopy(data);broken['custom_font']['glyphs']['A'][0][0][0]=bad
            with self.assertRaises(ValueError):content_data(broken)

        for key,bad in (('text_size',200),('text','A'*1001),('font','bad')):
            broken=copy.deepcopy(data);broken['drawing']['strokes'][0][key]=bad
            with self.assertRaises(ValueError):content_data(broken)

    async def test_font_symbols_and_text_size_roundtrip(self):
        value=await self.document()
        symbols='#"\'`“”‘’«»\\_&@€'
        value['content'].update(font_size=32,letter_spacing=-.5,custom_font={'name':'Simboli','weight':10,'glyphs':{char:[[[40,200],[80,40]]] for char in symbols}})
        self.assertEqual((await self.req('/notes/'+str(self.note),'PUT',value)).status,200)
        saved=(await self.document())['content'];self.assertEqual(saved['font_size'],32);self.assertEqual(saved['letter_spacing'],-.5);self.assertEqual(set(saved['custom_font']['glyphs']),set(symbols))
        for key,bad in [('font_size',7),('font_size',73),('font_size',True),('letter_spacing',-3),('letter_spacing',float('nan'))]:
            broken=copy.deepcopy(saved);broken[key]=bad
            with self.assertRaises(ValueError):content_data(broken)
        saved['custom_font']['glyphs']={chr(0x400+n):[[[10,20]]] for n in range(512)}
        self.assertEqual(len(content_data(saved)['custom_font']['glyphs']),512)
        saved['custom_font']['glyphs']['#']=[[[10,20]]]
        with self.assertRaises(ValueError):content_data(saved)

    def test_33_graph_study_and_handmade_formulas_roundtrip(self):
        data=content_data({})
        data['graph']['study']={'show_area':True,'show_derivative':True,'area_from':3,'area_to':6}
        data['custom_font']={'name':'Simboli','weight':8,'glyphs':{'α':[[[40,70]]]},'templates':[{'id':'system_1','name':'Sistema','strokes':[[[0,0],[600,220]]]}]}
        self.assertEqual(content_data(data),data)
        for key,value in (('show_area',1),('area_from',float('nan')),('area_to',2)):
            broken=copy.deepcopy(data);broken['graph']['study'][key]=value
            with self.assertRaises(ValueError):content_data(broken)
        for bad in (601,float('nan'),True):
            broken=copy.deepcopy(data);broken['custom_font']['templates'][0]['strokes'][0][0][0]=bad
            with self.assertRaises(ValueError):content_data(broken)
        for mutation in ('duplicate','oversized','empty'):
            broken=copy.deepcopy(data);templates=broken['custom_font']['templates']
            if mutation=='duplicate':templates.append(templates[0])
            elif mutation=='oversized':templates[0]['strokes']=[[[1,2]]*1000]*31
            else:templates[0]['name']=''
            with self.assertRaises(ValueError):content_data(broken)
