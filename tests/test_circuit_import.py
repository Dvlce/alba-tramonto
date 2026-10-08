"""Conversion preserves terminal topology and rejects executable or partial imports."""
import copy
import struct
import time
import unittest
import xml.etree.ElementTree as ET
from lab import import_circuit,build_netlist,_dcl_explode,_spice_number,component_value
import test_tramonto as fixtures

RC=b'Filtro RC\nV1 in 0 SIN(0 .1 100)\nR1 in out 15k\nC1 out 0 100n\n.tran 10u 50m\n.end\n'

def native_xml(unsupported=False):
    root=ET.Element('MSMElectronicsWorkbench');ET.SubElement(root,'Project',Name='&ASCTest');ET.SubElement(root,'CiCircuit');elements=ET.SubElement(root,'Elements')
    for ident,name,family,ports,value in [('v','V1','AC_VOLTAGE',['vp','vn'],None),('r','R1','RESISTOR',['rp','rn'],'15000'),('c','C1','CAPACITOR',['cp','cn'],'100n'),('g','0','GROUND',['gp'],None),('s','XSC1','SCOPE',['a','b','am','ext','bm','extn'],None)]:
        item=ET.SubElement(elements,'Item',CiID=ident);comp=ET.SubElement(item,'CiComponent',LocalName='&ASC'+name);attrs=ET.SubElement(comp,'Attributes');coll=ET.SubElement(ET.SubElement(attrs,'Item'),'CiaCollString');strings=ET.SubElement(coll,'strings')
        ET.SubElement(strings,'Item',Value='&ASC'+('UNSUPPORTED' if unsupported and ident=='r' else family))
        params=ET.SubElement(ET.SubElement(attrs,'Item'),'CiaParamList');vals=ET.SubElement(params,'parameters')
        for v in (['0','.1','0','0','0','100','0','0','0','0','0','0'] if ident=='v' else ['0',value or '0','0','0','0','0']):ET.SubElement(vals,'Item',Value='&ASC'+v)
        ps=ET.SubElement(comp,'Ports')
        for pid in ports:ET.SubElement(ps,'Item',CiID=pid)
    nodes={'vp':'input','rp':'input','a':'input','rn':'output','cp':'output','b':'output','vn':'zero','cn':'zero','gp':'zero','am':'zero','bm':'zero'}
    numbers={'a':'1','b':'2','am':'4','ext':'3','bm':'5','extn':'6'}
    for pid in ['vp','vn','rp','rn','cp','cn','gp','a','b','am','ext','bm','extn']:
        item=ET.SubElement(elements,'Item',CiID=pid);port=ET.SubElement(item,'CiPort',LocalName='&ASC'+numbers.get(pid,'1'));ns=ET.SubElement(port,'Nodes')
        if pid in nodes:ET.SubElement(ns,'Item',CiID=nodes[pid])
    for node in ['input','output','zero']:
        item=ET.SubElement(elements,'Item',CiID=node);ET.SubElement(item,'CiNode',LocalName='&ASC'+('0' if node=='zero' else node))
    return ET.tostring(root)

def literal_container(xml):
    # Valid DCL binary literal stream, with the length-519 end marker.
    stream=[]
    def bits(value,n):stream.extend((value>>i)&1 for i in range(n))
    bits(0,8);bits(4,8)
    for b in xml:bits(0,1);bits(b,8)
    bits(1,1);bits(0,7);bits(255,8)
    packed=bytes(sum(stream[i+j]<<j for j in range(min(8,len(stream)-i))) for i in range(0,len(stream),8))
    return b'MSMCompressedElectronicsWorkbenchXML'+struct.pack('<II',len(xml),0)+struct.pack('<II',len(xml),len(packed))+packed

def connected(circuit,a,b):
    parent={}
    def find(x):
        parent.setdefault(x,x)
        while parent[x]!=x:x=parent[x]
        return x
    for w in circuit['wires']:
        x,y=[(w[e]['component'],w[e]['port']) for e in ['from','to']];parent[find(x)]=find(y)
    return find(a)==find(b)

class ImportTests(unittest.TestCase):
    def test_rc_electrical_values_and_topology(self):
        c=import_circuit(RC,'rc.cir')['circuit'];p={p['id']:p for p in c['components']}
        self.assertEqual(p['V1']['params']['frequency'],100);self.assertEqual(component_value(p['R1']['value'],0),15000);self.assertAlmostEqual(component_value(p['C1']['value'],0),1e-7,places=15)
        self.assertTrue(connected(c,('V1',0),('R1',0)));self.assertTrue(connected(c,('R1',1),('C1',0)));self.assertFalse(connected(c,('R1',0),('C1',0)))
        self.assertIn('SIN(0 0.1 100',build_netlist(c,{'analysis':'tran'})['netlist'])
    def test_native_binary_preserves_four_differential_ports(self):
        result=import_circuit(literal_container(native_xml()),'test.ms14');c=result['circuit'];self.assertEqual(result['format'],'Multisim nativo')
        for scope,part,port in [(0,'V1',0),(1,'V1',1),(2,'C1',0),(3,'C1',1)]:self.assertTrue(connected(c,('XSC1',scope),(part,port)))
        self.assertEqual([t['channel'] for t in build_netlist(c,{'analysis':'tran'})['traces']],['A','B'])
    def test_spice_m_is_milli_and_meg_is_mega(self):
        self.assertEqual(_spice_number('1M'),.001);self.assertEqual(_spice_number('1meg'),1e6)
    def test_no_partial_conversion(self):
        for data,name in [(RC.replace(b'R1 in out 15k',b'B1 out 0 V=sin(time)'), 'x.cir'),(native_xml(True),'x.xml')]:
            with self.assertRaisesRegex(ValueError,'Conversione interrotta'):import_circuit(data,name)
    def test_controls_entities_bounds_and_corruption(self):
        for data,name in [(RC+b'.control\nshell rm -rf /\n','x.cir'),(RC.replace(b'.end',b'.include /etc/passwd'),'x.cir'),(native_xml().replace(b'<MSMElectronicsWorkbench>',b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><MSMElectronicsWorkbench>'),'x.xml'),(literal_container(native_xml())[:-6],'x.ms14'),(b'MSMCompressedElectronicsWorkbenchXML'+struct.pack('<II',100000000,0),'x.ms14'),(b'','x.cir')]:
            with self.subTest(name=name),self.assertRaises(ValueError):import_circuit(data,name)
    def test_dcl_reference_stream_and_deadline(self):
        self.assertEqual(_dcl_explode(bytes.fromhex('00048224258f807f'),13,time.monotonic()+1),b'AIAIAIAIAIAIA')
        xml=native_xml();container=literal_container(xml);block=container[len(b'MSMCompressedElectronicsWorkbenchXML')+16:]
        with self.assertRaises(ValueError):_dcl_explode(block,len(xml),time.monotonic()-1)

class ImportAPI(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.TramontoTests.asyncSetUp;asyncTearDown=fixtures.TramontoTests.asyncTearDown;req=fixtures.TramontoTests.req;document=fixtures.TramontoTests.document
    async def send(self,data=RC,uid=1,csrf=True):
        headers={**self.headers[uid],'Content-Type':'application/octet-stream','X-Circuit-Name':'rc.cir'}
        if not csrf:headers.pop('X-CSRF-Token')
        return await self.client.post('/api/tramonto/circuit/import',headers=headers,data=data)
    async def test_access_csrf_preview_never_mutates_note(self):
        before=await self.document();self.assertEqual((await self.send(uid=2)).status,403);self.assertEqual((await self.send(csrf=False)).status,403)
        response=await self.send();self.assertEqual(response.status,200);self.assertGreater((await response.json())['wires'],0);self.assertEqual(await self.document(),before)
        response=await self.send(RC.replace(b'R1 in out 15k',b'B1 out 0 V=sin(time)'));self.assertEqual(response.status,422);self.assertIn('B1',(await response.json())['error']);self.assertEqual(await self.document(),before)

if __name__=='__main__':unittest.main()
