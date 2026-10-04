/** Optional local bridge. Credentials and incoming messages stay outside git. */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import makeWASocket, {useMultiFileAuthState, DisconnectReason} from '@whiskeysockets/baileys';
import pino from 'pino';
import qr from 'qrcode-terminal';

process.umask(0o077);
const token=process.env.WHATSAPP_BRIDGE_TOKEN||'';
const matt=process.env.WHATSAPP_MATT_NUMBER||'';
if(token.length<32||!/^\d{8,15}$/.test(matt))throw Error('Configura un token lungo almeno 32 caratteri e il numero internazionale di Matt.');
const directory=path.resolve(process.env.WHATSAPP_AUTH_DIR||'../data/whatsapp');
fs.mkdirSync(directory,{recursive:true,mode:0o700});
const journal=path.join(directory,'inbox.jsonl');
let inbox=[];
if(fs.existsSync(journal))inbox=fs.readFileSync(journal,'utf8').trim().split('\n').filter(Boolean).slice(-200).map(line=>JSON.parse(line));
let nextId=(inbox.at(-1)?.id||0)+1,connected=false,sock=null,reconnect=null;
const log=pino({level:'silent'});
async function connect(){
  const {state,saveCreds}=await useMultiFileAuthState(directory);
  sock=makeWASocket({auth:state,logger:log,markOnlineOnConnect:false,syncFullHistory:false});
  sock.ev.on('creds.update',saveCreds);
  sock.ev.on('connection.update',update=>{
    if(update.qr)qr.generate(update.qr,{small:true});
    if(update.connection==='open'){connected=true;console.log('WhatsApp collegato.');}
    if(update.connection==='close'){
      connected=false;
      const code=update.lastDisconnect?.error?.output?.statusCode;
      if(code!==DisconnectReason.loggedOut){clearTimeout(reconnect);reconnect=setTimeout(()=>connect().catch(()=>console.error('Connessione da riprovare.')),10000);}
      else console.error('Account scollegato: ripetere l’abbinamento.');
    }
  });
  sock.ev.on('messages.upsert',({messages,type})=>{
    if(type!=='notify')return;
    for(const message of messages){
      if(message.key.fromMe||message.key.remoteJid!==matt+'@s.whatsapp.net')continue;
      const text=message.message?.conversation||message.message?.extendedTextMessage?.text;
      if(!text||inbox.some(entry=>entry.sourceId===message.key.id))continue;
      inbox.push({id:nextId++,sourceId:message.key.id,text:text.slice(0,3500),created:Date.now()/1000});
    }
    inbox=inbox.slice(-200);const tmp=journal+'.tmp';fs.writeFileSync(tmp,inbox.map(r=>JSON.stringify(r)).join('\n')+'\n',{mode:0o600});fs.renameSync(tmp,journal);
  });
}
let sending=false;
http.createServer(async(req,res)=>{
  const auth=req.headers.authorization||'',expected='Bearer '+token;
  const ok=Buffer.byteLength(auth)===Buffer.byteLength(expected)&&crypto.timingSafeEqual(Buffer.from(auth),Buffer.from(expected));
  res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');
  if(!ok){res.writeHead(401);res.end('{}');return;}
  const url=new URL(req.url,'http://localhost');
  if(req.method==='GET'&&url.pathname==='/status'){res.end(JSON.stringify({connected}));return;}
  if(req.method==='GET'&&url.pathname==='/inbox'){
    const after=Number(url.searchParams.get('after')||0);res.end(JSON.stringify({messages:inbox.filter(row=>row.id>after)}));return;
  }
  if(req.method!=='POST'||url.pathname!=='/send'){res.writeHead(404);res.end('{}');return;}
  if(!connected||sending){res.writeHead(503);res.end('{}');return;}
  let raw='';try{
    for await(const chunk of req){raw+=chunk;if(Buffer.byteLength(raw)>16000){res.writeHead(413);res.end('{}');return;}}
    const body=JSON.parse(raw);
    if(body.number!==matt||typeof body.text!=='string'||!body.text.trim()||body.text.length>3500){res.writeHead(400);res.end('{}');return;}
    sending=true;await sock.sendMessage(matt+'@s.whatsapp.net',{text:body.text});res.end('{"ok":true}');
  }catch{res.writeHead(502);res.end('{}');}finally{sending=false;}
}).listen(8091,'127.0.0.1',()=>console.log('Bridge locale 127.0.0.1:8091'));
connect().catch(()=>console.error('Abbinamento non riuscito.'));
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{clearTimeout(reconnect);sock?.end();process.exit(0);});
