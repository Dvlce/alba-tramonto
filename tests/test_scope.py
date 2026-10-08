"""Differential channel topology, original-sample precision and expanded editor bounds."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lab import build_netlist,simulation_settings,validate_params
from tramonto import content_data
ROOT=Path(__file__).resolve().parents[1]

def scope_circuit():
    parts=[{'id':key,'type':kind,'x':x,'y':200,'rotation':0,'label':key,'value':value} for key,kind,x,value in [('V1','voltage',100,'5V'),('V2','voltage',350,'2V'),('GND','ground',100,''),('OSC1','scope',650,'')]]
    pairs=[('V1',1,'GND',0),('V2',1,'GND',0),('OSC1',0,'V1',0),('OSC1',1,'V2',0),('OSC1',2,'V2',0),('OSC1',3,'GND',0)]
    wires=[{'id':'w'+str(i),'from':{'component':a,'port':ap},'to':{'component':b,'port':bp}} for i,(a,ap,b,bp) in enumerate(pairs)]
    return {'components':parts,'wires':wires}

class ScopeTests(unittest.TestCase):
    def test_summer_validated_gain_and_simulator_source(self):
        c=scope_circuit();c['components'].append({'id':'SUM1','type':'summer','x':450,'y':350,'rotation':0,'label':'Somma','value':'','params':{'gainA':2,'gainB':-1}})
        for port,target,tp in ((0,'V1',0),(1,'V2',0),(2,'OSC1',0),(3,'GND',0)):
            c['wires'].append({'id':'sum'+str(port),'from':{'component':'SUM1','port':port},'to':{'component':target,'port':tp}})
        c['wires']= [w for w in c['wires'] if w['id']!='w2']
        prepared=build_netlist(content_data({'circuit':c})['circuit'],{'analysis':'op'});self.assertIn('V=2*v(n1,0)+-1*v(n2,0)',prepared['netlist'])
        c['components'][-1]['params']['gainA']=float('inf')
        with self.assertRaises(ValueError):content_data({'circuit':c})
    def test_fixed_model_and_image_controls_reject_unsafe_values(self):
        for params in ({'model':'../other.lib'},{'model':'.include /etc/passwd'},{'phase':float('inf')},{'gainC':1001},{'plusTop':'true'},{'portsBottom':1},{'key':'A;quit'}):
            with self.subTest(params=params), self.assertRaises(ValueError):validate_params(params)
        self.assertEqual(validate_params({'model':'tl081','plusTop':True,'key':'A','phase':0}),{'phase':0,'plusTop':True,'model':'tl081','key':'A'})
    def test_four_ports_persist_and_produce_two_differential_traces(self):
        c=content_data({'circuit':scope_circuit()})['circuit'];prepared=build_netlist(c,{'analysis':'tran','samples':10000})
        self.assertEqual([s['channel'] for s in prepared['traces']],['A','B']);self.assertTrue(all(s['scope_id']=='OSC1' for s in prepared['traces']));self.assertEqual(prepared['options']['samples'],10000);self.assertIn('wrdata result.dat v(',prepared['netlist'])
    def test_legacy_two_terminal_scope_keeps_a_and_does_not_measure_floating_b(self):
        c=scope_circuit();c['wires']=c['wires'][:4];prepared=build_netlist(c,{'analysis':'op'});self.assertEqual(len(prepared['traces']),1);self.assertEqual(prepared['traces'][0]['channel'],'A')
    def test_unwired_scope_does_not_create_floating_measurement_nodes(self):
        c=scope_circuit();c['wires']=c['wires'][:2];prepared=build_netlist(c,{'analysis':'op'});self.assertFalse(any('scope_id' in t for t in prepared['traces']))
    def test_grounded_channel_never_requests_nonexistent_ground_vector(self):
        prepared=build_netlist(scope_circuit(),{'analysis':'op'})
        output=next(row for row in prepared['netlist'].splitlines() if row.startswith('wrdata'))
        self.assertIn('v(n1,n2)',output);self.assertTrue(output.endswith('v(n2)'));self.assertNotIn(',0)',output)
    def test_reversed_and_ground_to_ground_channels(self):
        c=scope_circuit();c['wires'][2]['to']={'component':'GND','port':0};c['wires'][4]['to']={'component':'GND','port':0}
        output=next(row for row in build_netlist(c,{'analysis':'op'})['netlist'].splitlines() if row.startswith('wrdata'))
        self.assertIn('(-v(n2))',output);self.assertIn('(v(n1)*0)',output)
    def test_invalid_terminal_number_rejected(self):
        c=scope_circuit();c['wires'][-1]['from']['port']=4
        with self.assertRaises(ValueError):content_data({'circuit':c})
    def test_large_canvas_and_coordinates_round_trip(self):
        c=scope_circuit();c['components'][-1].update(x=12000,y=20000);c['canvas']={'width':13000,'height':21000};c['wires'][0]['points']=[{'x':11000,'y':18000}]
        self.assertEqual(content_data({'circuit':c})['circuit'],c)
    def test_canvas_is_bounded(self):
        for bounds in ({'width':50001,'height':1000},{'width':1000,'height':float('nan')},{'width':1000,'height':640,'unsafe':1}):
            c=scope_circuit();c['canvas']=bounds
            with self.assertRaises(ValueError):content_data({'circuit':c})
        with self.assertRaises(ValueError):simulation_settings({'analysis':'tran','samples':10001})
    def test_worker_retains_every_sample_and_single_sample_peak(self):
        spec=importlib.util.spec_from_file_location('scope_worker',ROOT/'spice_worker.py');worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        with tempfile.TemporaryDirectory() as folder:
            previous=Path.cwd()
            try:
                os.chdir(folder);Path('metadata.json').write_text(json.dumps([{'name':'OSC1 · A','unit':'V','scope_id':'OSC1','channel':'A'}]));Path('result.dat').write_text('time voltage\n'+''.join(f'{i/10000} {99 if i==2011 else 0}\n' for i in range(5001)))
                with patch.object(worker.resource,'setrlimit'),patch.object(worker.subprocess,'run'):
                    result=worker.main()
                self.assertEqual(len(result['x']),5001);self.assertEqual(result['series'][0]['values'][2011],99);self.assertFalse(result['downsampled']);self.assertEqual(result['series'][0]['channel'],'A')
            finally:os.chdir(previous)

if __name__=='__main__':unittest.main()
