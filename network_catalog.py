"""Public didactic hardware catalog; physical ports are data, never commands."""
def ports(prefix,count,kind='ethernet'):
    return [{'id':prefix+str(i),'kind':kind} for i in range(1,count+1)]

NETWORK_MODELS={
    'router2':{'type':'router','name':'Router · 2 Gigabit + seriale','ports':ports('GigabitEthernet0/',2)+ports('Serial0/',2,'serial')+[{'id':'Console','kind':'console'}]},
    'router4':{'type':'router','name':'Router · 4 Gigabit + 2 SFP','ports':ports('GigabitEthernet0/',4)+ports('SFP0/',2,'fiber')+[{'id':'Console','kind':'console'}]},
    'switch8':{'type':'switch','name':'Switch · 8 Ethernet','ports':ports('FastEthernet0/',8)+[{'id':'Console','kind':'console'}]},
    'switch24':{'type':'switch','name':'Switch · 24 Ethernet + 2 SFP','ports':ports('FastEthernet0/',24)+ports('SFP0/',2,'fiber')+[{'id':'Console','kind':'console'}]},
    'switch48':{'type':'switch','name':'Switch · 48 Gigabit + 4 SFP','ports':ports('GigabitEthernet1/',48)+ports('SFP1/',4,'fiber')+[{'id':'Console','kind':'console'}]},
    'pc':{'type':'pc','name':'PC','ports':[{'id':'Ethernet0','kind':'ethernet'},{'id':'RS232','kind':'console'}]},
    'laptop':{'type':'laptop','name':'Laptop','ports':[{'id':'Ethernet0','kind':'ethernet'},{'id':'Wireless0','kind':'wifi'},{'id':'RS232','kind':'console'}]},
    'server':{'type':'server','name':'Server · 2 Ethernet','ports':ports('Ethernet',2)},
    'phone':{'type':'phone','name':'Telefono IP','ports':[{'id':'Switch','kind':'ethernet'},{'id':'PC','kind':'ethernet'}]},
    'printer':{'type':'printer','name':'Stampante di rete','ports':[{'id':'Ethernet0','kind':'ethernet'},{'id':'Wireless0','kind':'wifi'}]},
    'accesspoint':{'type':'accesspoint','name':'Access point','ports':[{'id':'Ethernet0','kind':'ethernet'},{'id':'Wireless0','kind':'wifi'}]},
    'firewall':{'type':'firewall','name':'Firewall · 4 Gigabit','ports':ports('GigabitEthernet0/',4)+[{'id':'Console','kind':'console'}]},
    'cloud':{'type':'cloud','name':'Cloud / WAN','ports':ports('Ethernet',4)+ports('Serial',2,'serial')+ports('Fiber',2,'fiber')},
}
DEFAULT_MODELS={v['type']:k for k,v in reversed(list(NETWORK_MODELS.items()))}

def model_for(node):
    ident=node.get('model',DEFAULT_MODELS[node['type']])
    if not isinstance(ident,str):raise ValueError('Modello di rete non valido.')
    model=NETWORK_MODELS.get(ident)
    if not model or model['type']!=node['type']:raise ValueError('Modello incompatibile con il dispositivo.')
    return model
