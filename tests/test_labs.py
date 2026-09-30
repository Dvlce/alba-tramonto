import asyncio
import copy
import math
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
import test_tramonto as fixtures
PNG=fixtures.PNG
from tramonto import content_data
from lab import Spice,PORTS,build_netlist,component_value,simulation_settings,validate_network,validate_params
from learning import record_feedback,feedback_instruction
from store import Scope

def divider():
    def part(id,type,value):return {'id':id,'type':type,'value':value,'label':id,'x':100,'y':100,'rotation':0}
    def wire(a,ap,b,bp):return {'id':a+str(ap)+b+str(bp),'from':{'component':a,'port':ap},'to':{'component':b,'port':bp}}
    return {'components':[part('V','voltage','5V'),part('R1','resistor','1k'),part('R2','resistor','1k'),part('G','ground','')],
            'wires':[wire('V',0,'R1',0),wire('R1',1,'R2',0),wire('R2',1,'G',0),wire('V',1,'G',0)]}

class LabValidation(unittest.TestCase):
    def test_01_si_values(self):
        for source,expected in [('1 kΩ',1000),('10 µF',.00001),('2M',2000000),('1 mH',.001),('3,3 V',3.3)]:self.assertAlmostEqual(component_value(source,1),expected)
    def test_02_netlist_injection_rejected(self):
        for value in ['1\n.include /etc/passwd','system ls','nan','inf','1;quit','1k .control','1e999']:
            with self.subTest(value=value),self.assertRaises(ValueError):component_value(value,1)
    def test_03_no_user_label_in_netlist(self):
        data=divider();data['components'][0]['label']='.include SECRET';result=build_netlist(data,{'analysis':'op'});self.assertNotIn('SECRET',result['netlist'])
    def test_04_ground_required(self):
        data=divider();data['components']=data['components'][:-1];data['wires']=data['wires'][:2]
        with self.assertRaises(ValueError):build_netlist(data,{'analysis':'op'})
    def test_05_numeric_limits(self):
        for params in [{'frequency':math.inf},{'amplitude':-1},{'closed':1},{'wave':'shell'},{'path':'secret'},{'duty':1}]:
            with self.assertRaises(ValueError):validate_params(params)
    def test_06_analyses(self):
        for name in ('op','tran','ac','dc'):self.assertEqual(build_netlist(divider(),{'analysis':name})['options']['analysis'],name)
    def test_07_limit_samples_and_time(self):
        for options in [{'analysis':'tran','stop':101},{'analysis':'tran','samples':2001},{'analysis':'dc','dc_start':5,'dc_end':0},{'analysis':'ac','start':100,'end':1},{'analysis':['op']},{'netlist':'code'}]:
            with self.assertRaises(ValueError):simulation_settings(options)
    def test_08_every_device_can_be_saved(self):
        for kind in PORTS:
            doc=content_data({});doc['circuit']['components']=[{'id':'P','type':kind,'value':'','label':'P','x':100,'y':100,'rotation':0}];self.assertEqual(content_data(doc)['circuit']['components'][0]['type'],kind)
    def test_09_network_invalid_values(self):
        sample={'id':'a','type':'pc','x':100,'y':100,'name':'PC','ip':'10.0.0.1/24','gateway':'','vlan':1,'enabled':True,'interfaces':[]}
        for key,value in [('ip','999.0.0.1/24'),('vlan',4095),('enabled',1),('type','shell'),('id',{}),('interfaces',['bad'])]:
            data=copy.deepcopy(sample);data[key]=value
            with self.assertRaises(ValueError):validate_network({'nodes':[data],'links':[]})
    def test_10_function_waveform(self):
        data=divider();data['components'][0].update(type='function',value='1kHz',params={'wave':'square','frequency':1000,'amplitude':2,'offset':1,'duty':.5});self.assertIn('PULSE(',build_netlist(data,{'analysis':'tran'})['netlist'])

class LabAPI(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.TramontoTests.asyncSetUp;asyncTearDown=fixtures.TramontoTests.asyncTearDown;req=fixtures.TramontoTests.req;document=fixtures.TramontoTests.document;update=fixtures.TramontoTests.update;upload=fixtures.TramontoTests.upload
    async def test_11_workspace_owner_only(self):
        self.assertEqual((await self.req('/workspace','POST',{'notebook_id':self.book,'note_id':self.note,'scroll_y':1234})).status,200)
        self.assertEqual((await(await self.req('/workspace')).json())['scroll_y'],1234)
        self.assertEqual(await(await self.req('/workspace',uid=4)).json(),{})
        self.assertEqual((await self.req('/workspace','POST',{'notebook_id':self.book,'note_id':self.note,'scroll_y':1},uid=4)).status,403)
    async def test_12_pages_numbered(self):
        new=(await(await self.req('/notes','POST',{'notebook_id':self.book,'title':'Seconda'})).json())['id'];self.assertEqual((await self.document(new))['page_number'],2)
        await self.req('/notes/'+str(self.note),'DELETE');self.assertEqual((await self.document(new))['page_number'],1)
    async def test_13_stale_workspace_cleared(self):
        await self.req('/workspace','POST',{'notebook_id':self.book,'note_id':self.note,'scroll_y':50});await self.req('/notes/'+str(self.note),'DELETE');self.assertEqual(await(await self.req('/workspace')).json(),{})
    async def test_14_inline_image_saved(self):
        id=(await(await self.upload()).json())['id'];value=await self.document();value['content'].update(images=[id],html=f'<p>Prima<img src="/api/tramonto/images/{id}" width="420" data-layout="right" onerror="bad">Dopo</p>');await self.req('/notes/'+str(self.note),'PUT',value)
        html=(await self.document())['content']['html'];self.assertIn('width="420"',html);self.assertIn('data-layout="right"',html);self.assertNotIn('onerror',html)
    async def test_15_external_and_foreign_image_removed(self):
        value=await self.document();value['content']['html']='<img src="https://evil.invalid/a"><img src="/api/tramonto/images/999"><p>test</p>';await self.req('/notes/'+str(self.note),'PUT',value);self.assertEqual((await self.document())['content']['html'],'<p>test</p>')
    async def test_16_copy_image_for_pagination(self):
        id=(await(await self.upload()).json())['id'];response=await self.req('/notes','POST',{'notebook_id':self.book,'copy_images_from':self.note,'title':'Continua','content':{'images':[id],'html':f'<img src="/api/tramonto/images/{id}">'}});self.assertEqual(response.status,201);new=(await response.json())['id'];value=await self.document(new);self.assertNotEqual(value['content']['images'],[id]);self.assertIn(str(value['content']['images'][0]),value['content']['html'])
    async def test_17_foreign_copy_forbidden(self):
        id=(await(await self.upload()).json())['id'];book=(await(await self.req('/notebooks','POST',{'title':'Altro'},uid=4)).json())['id'];self.assertEqual((await self.req('/notes','POST',{'notebook_id':book,'copy_images_from':self.note,'content':{'images':[id]}},uid=4)).status,403)
    async def test_18_labs_admin_required(self):
        for path in ('/labs','/netlist','/simulations'):
            self.assertEqual((await self.req(path,'GET' if path=='/labs' else 'POST',None if path=='/labs' else {'note_id':self.note},uid=2)).status,403)
    async def test_19_netlist_own_note(self):
        value=await self.document();value['content']['circuit']=divider();await self.req('/notes/'+str(self.note),'PUT',value);response=await self.req('/netlist','POST',{'note_id':self.note,'options':{'analysis':'op'}});self.assertEqual(response.status,200);self.assertIn('wrdata result.dat',(await response.json())['netlist']);self.assertEqual((await self.req('/netlist','POST',{'note_id':self.note},uid=4)).status,403)
    async def test_20_simulation_cancellation(self):
        value=await self.document();value['content']['circuit']=divider();await self.req('/notes/'+str(self.note),'PUT',value)
        async def run(*args):await asyncio.sleep(20)
        with patch.object(Spice,'available',True),patch.object(Spice,'run',run):
            response=await self.req('/simulations','POST',{'note_id':self.note,'options':{'analysis':'op'}});job=(await response.json())['job_id']
            self.assertEqual((await self.req('/simulations/'+job,uid=4)).status,403)
            self.assertEqual((await self.req('/simulations','POST',{'note_id':self.note})).status,429)
            self.assertTrue((await(await self.req('/simulations/'+job+'/cancel','POST',{})).json())['cancelled'])
    async def test_21_origin_rejected(self):
        response=await self.req('/notebooks','POST',{'title':'No'},headers={**self.headers[1],'Origin':'https://bad.invalid'});self.assertEqual(response.status,403)
    async def test_22_response_headers(self):
        response=await self.req('/notebooks');self.assertEqual(response.headers['Server'],'Alba');self.assertIn('max-age=',response.headers['Strict-Transport-Security']);self.assertIn("object-src 'none'",response.headers['Content-Security-Policy'])
    async def test_23_feedback_owner_only(self):
        mid=self.store.add_message(Scope('user',1),None,'assistant','Risposta');record_feedback(self.store,1,'utile',mid)
        with self.assertRaises(PermissionError):record_feedback(self.store,2,'utile',mid)
        self.assertEqual(len(self.store.rows('SELECT * FROM response_feedback')),1)
    async def test_24_feedback_adapts_style_not_facts(self):
        for n in range(2):record_feedback(self.store,1,'ripetitiva',self.store.add_message(Scope('user',1),None,'assistant','Risposta '+str(n)))
        self.assertIn('domande già poste',feedback_instruction(self.store,1));self.assertEqual(feedback_instruction(self.store,2),'');self.assertEqual(self.store.rows('SELECT * FROM memories'),[])
    async def test_25_erasure_feedback_workspace(self):
        self.store.add_message(Scope('user',1),None,'assistant','Risposta');record_feedback(self.store,1,'utile');await self.req('/workspace','POST',{'notebook_id':self.book,'note_id':self.note,'scroll_y':20});self.store.forget_user(1)
        for table in ('workspace_state','response_feedback'):self.assertEqual(self.store.rows('SELECT * FROM '+table),[])

@unittest.skipUnless(shutil.which('bwrap') and shutil.which('ngspice'),'Isolated SPICE requires Linux tools')
class ActualSpice(unittest.IsolatedAsyncioTestCase):
    async def test_26_real_divider_dc(self):
        result=await Spice(Path(__file__).resolve().parents[1]).run(build_netlist(divider(),{'analysis':'op'}));self.assertTrue(any(abs(s['values'][0]-2.5)<1e-6 for s in result['series']))
    async def test_27_real_transient(self):
        result=await Spice(Path(__file__).resolve().parents[1]).run(build_netlist(divider(),{'analysis':'tran','stop':.01,'samples':100}));self.assertGreater(len(result['x']),50);self.assertAlmostEqual(result['x'][-1],.01)
    async def test_28_real_ac(self):
        data=divider();data['components'][0]['type']='ac';data['components'][0]['value']='1kHz';result=await Spice(Path(__file__).resolve().parents[1]).run(build_netlist(data,{'analysis':'ac'}));self.assertTrue(any(abs(s['values'][0]-.5)<1e-6 for s in result['series']))
    async def test_29_real_sweep(self):
        result=await Spice(Path(__file__).resolve().parents[1]).run(build_netlist(divider(),{'analysis':'dc','dc_end':5}));self.assertTrue(any(abs(s['values'][-1]-2.5)<1e-6 for s in result['series']))
