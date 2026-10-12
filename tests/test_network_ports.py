import unittest
from lab import validate_network
from tramonto import content_data,rich_text

def topology():
 nodes=[dict(id='pc',type='pc',name='PC',x=100,y=100),dict(id='sw',type='switch',model='switch24',name='SW',x=500,y=100,cli='hostname SW\ninterface FastEthernet0/1\n no shutdown'),dict(id='phone',type='phone',name='Phone',x=300,y=300)]
 links=[dict(id='l',kind='ethernet',enabled=True,**{'from':'pc','to':'sw'},from_port='Ethernet0',to_port='FastEthernet0/1')]
 return {'nodes':nodes,'links':links}
class NetworkPortsTests(unittest.TestCase):
 def test_model_ports_cli_and_phone_survive(self):
  net=validate_network(topology());self.assertEqual(net['links'][0]['to_port'],'FastEthernet0/1');self.assertIn('hostname SW',net['nodes'][1]['cli']);self.assertEqual(net['nodes'][2]['type'],'phone')
 def test_incompatible_or_reused_ports_fail(self):
  for port in ('Console','FastEthernet0/99'):
   net=topology();net['links'][0]['to_port']=port
   with self.assertRaises(ValueError):validate_network(net)
  net=topology();net['links'].append(dict(id='l2',kind='ethernet',enabled=True,**{'from':'phone','to':'sw'},from_port='Switch',to_port='FastEthernet0/1'))
  with self.assertRaises(ValueError):validate_network(net)
 def test_legacy_connections_still_load(self):
  net=topology();net['links'][0].pop('from_port');net['links'][0].pop('to_port');self.assertEqual(validate_network(net)['links'][0]['kind'],'ethernet')
 def test_graph_points_and_free_image_are_bounded(self):
  chart={'kind':'bar','title':'Plot','points':[[0,1],[2,-3]]};self.assertEqual(content_data({'chart':chart})['chart'],chart)
  self.assertIn('data-x="120"',rich_text('<img src="/api/tramonto/images/1" width="100" data-layout="free" data-x="120" data-y="45">',[1]))
  self.assertNotIn('data-x',rich_text('<img src="/api/tramonto/images/1" data-layout="free" data-x="99999">',[1]))
  chart['points']=[[0,float('nan')]]
  with self.assertRaises(ValueError):content_data({'chart':chart})
