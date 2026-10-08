/* Bounded expression conversion and real-domain analysis, without evaluating code. */
(()=>{'use strict';
function normalize(input){
 if(typeof input!=='string'||input.length>4000)throw Error('Espressione troppo lunga.');
 let source=input.trim().replace(/[−–]/g,'-').replace(/[×·]/g,'*').replace(/÷/g,'/').replace(/π/g,'pi').replace(/²/g,'^2').replace(/³/g,'^3').replace(/√\s*\(/g,'sqrt(').replace(/\$/g,'');let i=0,depth=0;
 function group(){while(/\s/.test(source[i]||'')&&i<source.length)i++;if(source[i]!=='{')throw Error('LaTeX incompleto: manca una parentesi graffa.');i++;return read('}');}
 function read(end){if(++depth>32)throw Error('Espressione troppo annidata.');let out='';while(i<source.length){const c=source[i++];if(c===end){depth--;return out;}if(c==='}')throw Error('Parentesi graffa inattesa.');if(c==='{'){out+='('+read('}')+')';continue;}if(c!=='\\'){out+=c;continue;}
 const match=source.slice(i).match(/^[A-Za-z]+|^./);if(!match)throw Error('Comando LaTeX incompleto.');const command=match[0];i+=command.length;
 if(['frac','dfrac','tfrac'].includes(command)){const a=group(),b=group();out+='(('+a+')/('+b+'))';}
 else if(command==='sqrt'){while(source[i]===' ')i++;let root='2';if(source[i]==='['){const close=source.indexOf(']',++i);if(close<0)throw Error('Indice della radice incompleto.');root=source.slice(i,close);i=close+1;}const a=group();if(root==='2')out+='sqrt('+a+')';else if(root==='3')out+='cbrt('+a+')';else throw Error('Per il grafico usa sqrt o cbrt per le radici.');}
 else if(command==='colorbox'){group();out+=group();}
 else if(command==='fcolorbox'){group();group();out+=group();}
 else if(['boxed','mathrm','operatorname','text'].includes(command))out+=group();
 else if(command==='color')group();
 else if(['left','right','displaystyle','textstyle',',','!',';',' '].includes(command)){}
 else if(['cdot','times'].includes(command))out+='*';else if(command==='div')out+='/';
 else if(command==='pi')out+='pi';else if(command==='ln')out+='log';
 else if(['sin','cos','tan','asin','acos','atan','sinh','cosh','tanh','log','exp','abs'].includes(command))out+=command;
 else if(['{','}'].includes(command))out+=command==='{'?'(':')';
 else throw Error('Comando non utilizzabile nel grafico: \\'+command+'. Usa una funzione di x.');
 }depth--;if(end)throw Error('Parentesi graffa non chiusa.');return out;}
 let value=read().trim().replace(/^\s*(?:y|f\s*\(\s*x\s*\))\s*=\s*/i,'').replace(/\b(sen|tg|ln)\b/g,m=>({sen:'sin',tg:'tan',ln:'log'})[m]);
 if(!/\b(?:min|max|pow|atan2|log)\s*\([^)]*,/.test(value))value=value.replace(/(\d),(\d)/g,'$1.$2');
 value=value.replace(/\b(sin|cos|tan|log|exp|abs)\s+(x|pi|e|\d+(?:\.\d+)?)\b/g,'$1($2)');
 if(!value||value.length>250)throw Error('Inserisci una funzione di x lunga al massimo 250 caratteri.');return value;
}
function polynomial(node){
 if(node.type==='ParenthesisNode')return polynomial(node.content);
 if(node.type==='ConstantNode'&&typeof node.value==='number')return [node.value];
 if(node.type==='SymbolNode')return node.name==='x'?[0,1]:node.name==='pi'?[Math.PI]:node.name==='e'?[Math.E]:null;
 if(node.type!=='OperatorNode')return null;const args=node.args.map(polynomial);if(args.some(a=>!a))return null;
 function add(a,b,sign=1){return Array.from({length:Math.max(a.length,b.length)},(_,i)=>(a[i]||0)+sign*(b[i]||0));}
 function multiply(a,b){const p=Array(a.length+b.length-1).fill(0);if(p.length>3)return null;a.forEach((v,i)=>b.forEach((w,j)=>p[i+j]+=v*w));return p;}
 if(node.op==='+')return args.length===1?args[0]:add(...args);if(node.op==='-')return args.length===1?args[0].map(x=>-x):add(...args,-1);
 if(node.op==='*')return multiply(...args);if(node.op==='/'&&args[1].length===1&&args[1][0]!==0)return args[0].map(x=>x/args[1][0]);
 if(node.op==='^'&&args[1].length===1){const n=args[1][0];if(n===0)return [1];if(n===1)return args[0];if(n===2)return multiply(args[0],args[0]);}return null;
}
function roots(p){if(!p)return [];p=[...p];while(p.length>1&&p.at(-1)===0)p.pop();if(p.length===1)return [];if(p.length===2)return [-p[0]/p[1]];const [c,b,a]=p,d=b*b-4*a*c;if(d<0)return [];if(d===0)return [-b/(2*a)];const q=-.5*(b+Math.sign(b||1)*Math.sqrt(d));return [q/a,c/q].sort((x,y)=>x-y);}
const unique=values=>values.filter(Number.isFinite).sort((a,b)=>a-b).filter((x,i,a)=>!i||Math.abs(x-a[i-1])>1e-8*Math.max(1,Math.abs(x)));
const format=x=>x===Infinity?'+∞':x===-Infinity?'−∞':Math.abs(x)<1e-10?'0':String(Number(x.toPrecision(7)));
function analyze(expression,fn){
 const tree=math.parse(normalize(expression)),conditions=[];
 function condition(n,op){conditions.push({node:n,op,p:polynomial(n),label:n.toString()+' '+({'ge':'≥ 0','gt':'> 0','ne':'≠ 0'})[op],compiled:n.compile()});}
 function offset(n,c){return math.parse('('+n.toString()+')'+(c<0?'-':'+')+Math.abs(c));}
 tree.traverse(n=>{
  if(n.type==='OperatorNode'&&['/','%'].includes(n.op)){let denominator=n.args[1];while(denominator.type==='ParenthesisNode')denominator=denominator.content;if(denominator.type==='FunctionNode'&&denominator.fn.name==='sqrt')condition(denominator.args[0],'gt');else condition(denominator,'ne');}
  if(n.type==='OperatorNode'&&n.op==='^'){const p=polynomial(n.args[1]);if(p?.length===1){if(!Number.isInteger(p[0]))condition(n.args[0],p[0]<0?'gt':'ge');else if(p[0]<0)condition(n.args[0],'ne');}else condition(n.args[0],'gt');}
  if(n.type!=='FunctionNode')return;const name=n.fn.name,a=n.args[0];if(name==='sqrt')condition(a,'ge');
  if(['log','log10','log2'].includes(name)){condition(a,'gt');if(n.args[1]){condition(n.args[1],'gt');condition(offset(n.args[1],-1),'ne');}}
  if(['asin','acos','atanh'].includes(name)){condition(offset(a,1),name==='atanh'?'gt':'ge');condition(math.parse('1-('+a.toString()+')'),name==='atanh'?'gt':'ge');}
  if(name==='acosh')condition(offset(a,-1),'ge');if(name==='tan')condition(math.parse('cos('+a.toString()+')'),'ne');
  if(name==='pow'){const p=polynomial(n.args[1]);if(!p||p.length!==1)condition(a,'gt');else if(!Number.isInteger(p[0]))condition(a,p[0]<0?'gt':'ge');else if(p[0]<0)condition(a,'ne');}
 });
 const cuts=unique(conditions.flatMap(c=>roots(c.p))),known=conditions.filter(c=>c.p),unknown=conditions.filter(c=>!c.p);
 function allowed(x,list=conditions){return list.every(c=>{let v;try{v=c.compiled.evaluate({x,pi:Math.PI,e:Math.E});}catch(_){return false;}if(typeof v!=='number'||!Number.isFinite(v))return false;const epsilon=c.p?1e-12*Math.max(...c.p.map((a,i)=>Math.abs(a*x**i))):0;return c.op==='ge'?v>=-epsilon:c.op==='gt'?v>epsilon:Math.abs(v)>epsilon;});}
 const edges=[-Infinity,...cuts,Infinity],intervals=[];
 for(let i=0;i<edges.length-1;i++){const lo=edges[i],hi=edges[i+1],mid=lo===-Infinity?(hi===Infinity?0:hi-Math.max(1,Math.abs(hi))):hi===Infinity?lo+Math.max(1,Math.abs(lo)):(lo+hi)/2;if(allowed(mid,known))intervals.push({lo,hi,lc:Number.isFinite(lo)&&allowed(lo,known),hc:Number.isFinite(hi)&&allowed(hi,known)});}
 for(const x of cuts)if(allowed(x,known)&&!intervals.some(s=>(s.lo===x&&s.lc)||(s.hi===x&&s.hc)))intervals.push({lo:x,hi:x,lc:true,hc:true});
 intervals.sort((a,b)=>a.lo-b.lo);const merged=[];for(const interval of intervals){const previous=merged.at(-1);if(previous&&previous.hi===interval.lo&&(previous.hc||interval.lc)){previous.hi=interval.hi;previous.hc=interval.hc;}else merged.push({...interval});}
 const intervalText=s=>s.lo===s.hi?'{'+format(s.lo)+'}':(s.lc?'[':'(')+format(s.lo)+'; '+format(s.hi)+(s.hc?']':')');
 let domain=merged.length===1&&merged[0].lo===-Infinity&&merged[0].hi===Infinity?'ℝ':merged.length?merged.map(intervalText).join(' ∪ '):'∅';
 if(unknown.length)domain+=' con '+[...new Set(unknown.map(c=>c.label))].join(' e ');
 function numerator(n){while(n.type==='ParenthesisNode')n=n.content;const p=polynomial(n);if(p)return {roots:roots(p),complete:true,zero:p.every(x=>x===0)};if(n.type==='OperatorNode'&&n.op==='/')return numerator(n.args[0]);if(n.type==='FunctionNode'&&['sqrt','cbrt','abs'].includes(n.fn.name))return numerator(n.args[0]);if(n.type==='OperatorNode'&&n.op==='*'){const a=n.args.map(numerator);return {roots:unique(a.flatMap(x=>x.roots)),complete:a.every(x=>x.complete),zero:a.some(x=>x.zero)};}if(n.type==='OperatorNode'&&n.op==='^'){const exponent=polynomial(n.args[1]);if(exponent?.length===1&&exponent[0]>0)return numerator(n.args[0]);}return {roots:[],complete:false,zero:false};}
 const zero=numerator(tree);zero.roots=zero.roots.filter(x=>allowed(x)&&Number.isFinite(fn(x))&&Math.abs(fn(x))<1e-6);
 allowed.excluded=cuts.filter(x=>!allowed(x));
 return {tree,conditions,cuts,intervals:merged,domain,complete:!unknown.length,allowed,zero,intervalText};
}
function sampledRoots(fn,a,b){const found=[];let previous=null;for(let i=0;i<=1600;i++){const x=a+(b-a)*i/1600,y=fn(x);if(!Number.isFinite(y)){previous=null;continue;}if(y===0)found.push(x);if(previous&&y*previous.y<0){let lo=previous.x,hi=x,flo=previous.y;for(let n=0;n<45;n++){const mid=(lo+hi)/2,v=fn(mid);if(!Number.isFinite(v))break;if(v*flo<=0)hi=mid;else{lo=mid;flo=v;}}const root=(lo+hi)/2;if(Number.isFinite(fn(root))&&Math.abs(fn(root))<=Math.max(Number.MIN_VALUE,Math.min(Math.abs(y),Math.abs(previous.y))*1e-5))found.push(root);}previous={x,y};}return unique(found);}
function study(expression,fn,a,b){const analysis=analyze(expression,fn),exact=analysis.complete&&analysis.zero.complete,zeros=analysis.zero.complete?analysis.zero.roots:sampledRoots(fn,a,b),edges=unique([...analysis.cuts,...zeros,0,...(exact?[]:[a,b])]),bounds=exact?[-Infinity,...edges,Infinity]:[a,...edges.filter(x=>x>a&&x<b),b],signs=[];
 for(let i=0;i<bounds.length-1;i++){const lo=bounds[i],hi=bounds[i+1],x=lo===-Infinity?hi-Math.max(1,Math.abs(hi)):hi===Infinity?lo+Math.max(1,Math.abs(lo)):(lo+hi)/2,y=fn(x);if(analysis.allowed(x)&&Number.isFinite(y))signs.push({lo,hi,sign:y===0?'0':y>0?'+':'−'});}
 const quadrants=new Set();let finite=0;for(let i=0;i<=1200;i++){const x=a+(b-a)*i/1200,y=fn(x);if(!analysis.allowed(x)||!Number.isFinite(y))continue;finite++;if(x>0&&y>0)quadrants.add('I');if(x<0&&y>0)quadrants.add('II');if(x<0&&y<0)quadrants.add('III');if(x>0&&y<0)quadrants.add('IV');}
 let derivative='';try{derivative=math.derivative(analysis.tree,'x').toString();}catch(_){derivative='Derivata simbolica non disponibile per questa funzione.';}
 return {...analysis,zeros,signs,exact,quadrants:[...quadrants],finite,derivative,yIntercept:analysis.allowed(0)&&Number.isFinite(fn(0))?fn(0):null};
}
function integrate(fn,a,b,allowed){if(!Number.isFinite(a)||!Number.isFinite(b)||a>=b)throw Error('Scegli a < b.');const invalid='Intervallo fuori dal dominio o discontinuo: scegli estremi nel tratto reale della funzione.';if(allowed?.excluded?.some(x=>x>=a&&x<=b))throw Error(invalid);
 function simpson(n){const h=(b-a)/n;let signed=0,absolute=0;for(let i=0;i<=n;i++){const x=a+i*h,y=fn(x);if((allowed&&!allowed(x))||!Number.isFinite(y))throw Error(invalid);const weight=i===0||i===n?1:i%2?4:2;signed+=weight*y;absolute+=weight*Math.abs(y);}return {signed:signed*h/3,absolute:absolute*h/3};}
 const coarse=simpson(600),fine=simpson(1200);if(Math.abs(fine.absolute-coarse.absolute)>Math.max(.002,fine.absolute*.02))throw Error('La stima dell’area non converge: restringi l’intervallo a un tratto continuo.');return fine;}
window.TramontoMath={normalize,polynomial,roots,format,analyze,study,integrate,sampledRoots};
})();
