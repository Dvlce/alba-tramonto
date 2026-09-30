"""Bounded request bodies/rate buckets; independent of a proxy-supplied client IP."""
import time
from collections import OrderedDict,deque
from aiohttp import web

class HTTPGuard:
    def __init__(self,keys,public_url): self.keys,self.public_url=keys,public_url; self.buckets=OrderedDict(); self.pending=0
    def enter(self):
        if self.pending>=64: return False
        self.pending+=1; return True
    def leave(self): self.pending-=1
    def hit(self,name,limit=600,period=60):
        now=time.monotonic(); values=self.buckets.pop(name,deque())
        while values and now-values[0]>=period: values.popleft()
        self.buckets[name]=values
        while len(self.buckets)>2048: self.buckets.popitem(last=False)
        if len(values)>=limit: raise web.HTTPTooManyRequests(text='Troppe richieste. Attendi un minuto.',headers={'Retry-After':'60'})
        values.append(now)
    async def check(self,request):
        api=request.path.startswith(('/api/','/auth/'))
        if not api: return
        identity=request.get('identity'); owner='user:'+str(identity['user_id']) if identity else 'anonymous'
        self.hit(owner,600 if identity else 120)
        if request.method in ('POST','PUT','PATCH','DELETE'):
            origin=request.headers.get('Origin')
            allowed={self.public_url,str(request.url.origin())}
            if origin and origin not in allowed: raise PermissionError('Origine non autorizzata.')
            limit=1100000 if request.path.startswith('/api/tramonto/') else 20000
            if request.path=='/api/login' or request.path.startswith('/auth/'): limit=4000
            image=request.path.startswith('/api/tramonto/notes/') and request.path.endswith('/images')
            if image: limit=8*1024*1024
            if request.content_length and request.content_length>limit: raise web.HTTPRequestEntityTooLarge(max_size=limit,actual_size=request.content_length)
            if request.can_read_body and not image:
                value=bytearray()
                async for chunk in request.content.iter_chunked(8192):
                    value.extend(chunk)
                    if len(value)>limit: raise web.HTTPRequestEntityTooLarge(max_size=limit,actual_size=len(value))
                request._read_bytes=bytes(value)  # aiohttp caches read() here; json() uses the same bounded bytes.
