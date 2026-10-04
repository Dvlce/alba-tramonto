"""Read bounded GGUF metadata and plan SSD placement without changing weights."""
import math
import re
import struct
from pathlib import Path

GIB = 1024 ** 3
FIXED = {0:'B', 1:'b', 2:'H', 3:'h', 4:'I', 5:'i', 6:'f', 7:'?', 10:'Q', 11:'q', 12:'d'}


def inspect_gguf(path):
    path = Path(path)
    size = path.stat().st_size
    with path.open('rb') as source:
        def read(n):
            value = source.read(n)
            if len(value) != n: raise ValueError('GGUF troncato.')
            return value
        def number(fmt): return struct.unpack('<'+fmt, read(struct.calcsize(fmt)))[0]
        def string(keep=True):
            length = number('Q')
            if length > 16*1024*1024 or source.tell()+length > size: raise ValueError('Stringa GGUF non valida.')
            if keep:
                if length > 65536: raise ValueError('Metadato GGUF troppo lungo.')
                return read(length).decode('utf-8', errors='strict')
            source.seek(length, 1)
        def value(kind, keep=True):
            if kind in FIXED: return number(FIXED[kind])
            if kind == 8: return string(keep)
            if kind != 9: raise ValueError('Tipo di metadato GGUF sconosciuto.')
            item, count = number('I'), number('Q')
            if item == 9 or count > 2_000_000: raise ValueError('Array GGUF non valido.')
            if item in FIXED:
                length = count*struct.calcsize(FIXED[item])
                if source.tell()+length > size: raise ValueError('Array GGUF troncato.')
                source.seek(length, 1)
            elif item == 8:
                for _ in range(count): string(False)
            else: raise ValueError('Tipo array GGUF sconosciuto.')
            return None
        if read(4) != b'GGUF' or number('I') not in (2,3): raise ValueError('Serve un GGUF v2/v3.')
        count, pairs = number('Q'), number('Q')
        if count > 100000 or pairs > 100000: raise ValueError('Indice GGUF troppo grande.')
        metadata = {}
        wanted = re.compile(r'^(general\.(architecture|name|file_type|alignment)|[a-z0-9_-]+\.(block_count|embedding_length|expert_count|expert_used_count|attention\.(head_count|head_count_kv|key_length|value_length)))$')
        for _ in range(pairs):
            key, kind = string(), number('I')
            v = value(kind, bool(wanted.fullmatch(key)))
            if wanted.fullmatch(key): metadata[key] = v
        tensors = []
        for _ in range(count):
            name, dimensions = string(), number('I')
            if not 1 <= dimensions <= 4: raise ValueError('Dimensioni GGUF non valide.')
            shape = [number('Q') for _ in range(dimensions)]
            if any(not n for n in shape): raise ValueError('Tensore GGUF vuoto.')
            tensors.append({'name':name, 'shape':shape, 'type':number('I'), 'offset':number('Q')})
        alignment = metadata.get('general.alignment',32)
        if type(alignment) is not int or not 1 <= alignment <= 4096: raise ValueError('Allineamento GGUF non valido.')
        start = (source.tell()+alignment-1)//alignment*alignment
        tensors.sort(key=lambda t:t['offset'])
        for i,tensor in enumerate(tensors):
            end = tensors[i+1]['offset'] if i+1<len(tensors) else size-start
            if tensor['offset'] >= end or start+end > size: raise ValueError('Offset GGUF non valido.')
            tensor['bytes'] = end-tensor['offset']
        return {'file_bytes':size, 'metadata':metadata, 'tensors':tensors}


def plan(info, total_ram, available_ram, context=1024, reserve=1024**3):
    if not 512 <= context <= 4096: raise ValueError('Contesto tra 512 e 4096 token.')
    if min(total_ram,available_ram) <= 0: raise ValueError('Memoria non disponibile.')
    meta = info['metadata']; arch = meta.get('general.architecture','unknown')
    scalar = lambda k,default=0: meta.get(arch+'.'+k,default)
    experts, used = scalar('expert_count'), scalar('expert_used_count')
    expert_bytes = sum(t['bytes'] for t in info['tensors'] if re.search(r'ffn_(?:gate|up|down)_exps\.weight$',t['name']))
    recognized = bool(experts and 0<used<=experts and expert_bytes)
    dense_bytes = info['file_bytes']-expert_bytes if recognized else info['file_bytes']
    active_bytes = dense_bytes+math.ceil(expert_bytes*used/experts) if recognized else info['file_bytes']
    layers, width, heads = scalar('block_count'), scalar('embedding_length'), scalar('attention.head_count')
    kv_heads = scalar('attention.head_count_kv',heads)
    dimension = width//heads if heads else 0
    # Full f16 KV; no quantized cache. Hybrid/recurrent architectures need the
    # actual server allocation as well; this conservative estimate is labelled.
    kv_bytes = context*layers*kv_heads*(scalar('attention.key_length',dimension)+scalar('attention.value_length',dimension))*2
    overhead = 384*1024**2
    budget = max(0,min(total_ram-reserve,available_ram))
    full = info['file_bytes']+kv_bytes+overhead <= budget
    repack_fits = 2*info['file_bytes']+kv_bytes+overhead <= budget
    working = active_bytes+kv_bytes+overhead <= budget
    return {'architecture':arch, 'file_bytes':info['file_bytes'], 'experts':experts,
            'active_experts':used, 'recognized_moe_tensors':recognized,
            'dense_bytes':dense_bytes,'estimated_active_weight_bytes':active_bytes,
            'kv_f16_estimate_bytes':kv_bytes, 'runtime_allowance_bytes':overhead,
            'ram_budget_bytes':budget,'context_tokens':context,
            'classification':'resident' if full else 'moe_disk_candidate' if recognized and working else 'disk_bound',
            'policy':'native' if repack_fits else 'mapped', 'repack_peak_fits':repack_fits,
            'weights_changed':False,
            'quantization_changed':False, 'cache_type':'f16',
            'note':'Selective experts require compatible MoE kernels; mmap alone is not a Colibri expert cache.' if recognized else
                   'Dense inference uses every layer; SSD paging preserves weights but may be very slow.',
            'estimate_only':True}
