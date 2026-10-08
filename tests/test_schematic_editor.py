"""Persistence and bounds for routed wires, brushes and mathematical text."""
import copy
import unittest
from tramonto import content_data
from lab import build_netlist

class EditorDataTests(unittest.TestCase):
    def document(self):
        d=content_data({})
        d['circuit']={'components':[{'id':id,'type':kind,'x':x,'y':160,'rotation':0,'label':id,'value':value} for id,kind,x,value in [('V1','voltage',100,'5V'),('R1','resistor',400,'1k'),('GND','ground',100,''),('J1','junction',250,'')]],'wires':[{'id':'a','from':{'component':'V1','port':0},'to':{'component':'J1','port':0},'color':'#dc8a50','points':[{'x':170,'y':160},{'x':170,'y':260}]},{'id':'b','from':{'component':'J1','port':0},'to':{'component':'R1','port':0}},{'id':'c','from':{'component':'V1','port':1},'to':{'component':'GND','port':0}},{'id':'d','from':{'component':'R1','port':1},'to':{'component':'GND','port':0}}]}
        return d
    def test_route_colour_and_nested_math_round_trip(self):
        d=self.document();d['html']='<p>x<sup>2<sup>3</sup></sup> + y<sub>n</sub> ≤ Ω μ γ ↑</p>'
        for font in ('book','classic','humanist','geometric','slab','hand','script','typewriter'):
            d['font']=font;self.assertEqual(content_data(d),d)
    def test_legacy_strokes_and_wires_keep_their_format(self):
        d=self.document();d['drawing']['strokes']=[{'color':'#dc8a50','size':3,'points':[[10,20],[30,40]]}];self.assertEqual(content_data(d),d)
    def test_all_brushes_shapes_round_trip(self):
        d=self.document()
        for tool in ('pen','pencil','marker','highlighter','line','arrow','double-arrow','rectangle','ellipse','triangle','diamond'):
            d['drawing']['strokes']=[{'tool':tool,'fill':True,'dash':False,'color':'#123456','size':30,'points':[[10,20],[30,40]]}];self.assertEqual(content_data(d),d)
    def test_invalid_route_and_colour_rejected(self):
        for bad in (['x'],[{'x':1,'y':float('nan')}],[{'x':50001,'y':0}],[{'x':2}],[{'x':1,'y':2,'unsafe':'extra'}],[{'x':1,'y':2}]*101):
            d=self.document();d['circuit']['wires'][0]['points']=bad
            with self.assertRaises(ValueError):content_data(d)
        for colour in ('red','#fff','url(javascript:bad)',None):
            d=self.document();d['circuit']['wires'][0]['color']=colour
            with self.assertRaises(ValueError):content_data(d)
    def test_invalid_tools_do_not_enter_saved_data(self):
        for extra in ({'tool':'bad'},{'fill':'true'},{'dash':1}):
            d=self.document();d['drawing']['strokes']=[{'color':'#123456','size':3,'points':[[0,0]],**extra}]
            with self.assertRaises(ValueError):content_data(d)
    def test_junction_has_same_electrical_node_as_original_wire(self):
        d=self.document();split=build_netlist(content_data(d)['circuit'],{'analysis':'op'})
        original=copy.deepcopy(d['circuit']);original['components']=original['components'][:-1];original['wires']=original['wires'][2:];original['wires'].insert(0,{'id':'direct','from':{'component':'V1','port':0},'to':{'component':'R1','port':0}})
        direct=build_netlist(original,{'analysis':'op'});self.assertEqual(split,direct)

if __name__=='__main__':unittest.main()
