"""Offline CPU LoRA; executed in bubblewrap, no application DB or networking."""
import hashlib
import json
import math
import os
import resource
import signal
import sys
import time
from pathlib import Path

sys.path=[p for p in sys.path if not p.endswith(('dist-packages','site-packages'))]
sys.path[:0]=[str(p) for p in Path('/venv/lib').glob('python*/site-packages')]
resource.setrlimit(resource.RLIMIT_CPU,(7200,7200))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
resource.setrlimit(resource.RLIMIT_FSIZE,(3*1024**3,3*1024**3))
os.nice(15)
os.environ.update({'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1',
                   'TOKENIZERS_PARALLELISM':'false','OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2'})
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
from peft import LoraConfig,PeftModel,get_peft_model
from peft import get_peft_model_state_dict,set_peft_model_state_dict
from peft.utils import load_peft_weights

stopping=False
def stop(*unused):
    global stopping
    stopping=True
signal.signal(signal.SIGTERM,stop)


def emit(**value):print(json.dumps(value),flush=True)


def main():
    spec=json.loads(Path('/work/spec.json').read_text())
    torch.set_num_threads(2);torch.set_num_interop_threads(1);torch.manual_seed(42)
    emit(stage='loading',base=spec['base'],revision=spec['revision'])
    tokenizer=AutoTokenizer.from_pretrained('/base',local_files_only=True,trust_remote_code=False)
    base=AutoModelForCausalLM.from_pretrained('/base',local_files_only=True,trust_remote_code=False,
          use_safetensors=True,torch_dtype=torch.float32,attn_implementation='eager')
    base.config.use_cache=False
    layers=list(range(18,24));expanded=False
    previous_config=Path('/previous/adapter_config.json')
    previous=json.loads(previous_config.read_text()) if previous_config.exists() else None
    compatible=previous and previous.get('r')==4 and previous.get('lora_alpha')==8 and not previous.get('rank_pattern') and set(previous.get('target_modules',[]))=={'q_proj','v_proj'}
    if previous and not compatible:
        model=PeftModel.from_pretrained(base,'/previous',is_trainable=True,local_files_only=True)
        layers=previous.get('layers_to_transform',[])
    else:
        if previous:layers=sorted(set(layers)|set(previous.get('layers_to_transform') or []))
        model=get_peft_model(base,LoraConfig(task_type='CAUSAL_LM',r=4,lora_alpha=8,lora_dropout=.05,
              target_modules=['q_proj','v_proj'],layers_to_transform=layers))
        if previous:
            state=load_peft_weights('/previous',device='cpu',local_files_only=True)
            result=set_peft_model_state_dict(model,state)
            restored=get_peft_model_state_dict(model)
            if result.unexpected_keys or any(key not in restored or not torch.equal(restored[key],value) for key,value in state.items()):
                raise ValueError('Checkpoint precedente non ripristinato integralmente.')
            expanded=set(layers)!=set(previous.get('layers_to_transform') or [])
    params=[p for p in model.parameters() if p.requires_grad]
    before=[p.detach().clone() for p in params]
    optimizer=torch.optim.AdamW(params,lr=spec.get('learning_rate', .0003))
    maximum=192
    truncated=0
    def batch(row):
        nonlocal truncated
        messages=[{'role':'system','content':row.get('system','Sei Notte. Scrivi soltanto una funzione Python corretta.')},
                  {'role':'user','content':row['prompt']}]
        prefix=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)
        answer=tokenizer.encode(row['answer']+tokenizer.eos_token,add_special_tokens=False)
        clipped=len(prefix)>maximum-32 or len(prefix)+len(answer)>maximum
        if len(prefix)>maximum-32:
            prefix=prefix[-(maximum-32):]
        if clipped:truncated+=1
        ids=(prefix+answer)[:maximum]
        labels=([-100]*len(prefix)+answer)[:len(ids)]
        if not any(x!=-100 for x in labels): raise ValueError('Esempio senza token di risposta.')
        return {'input_ids':torch.tensor([ids]),'labels':torch.tensor([labels])}
    train=[batch(r) for r in spec['train']]
    validation=[batch(r) for r in spec['validation']]
    def evaluate():
        model.eval()
        with torch.inference_mode():values=[float(model(**b).loss) for b in validation]
        groups={task:sum(v for v,r in zip(values,spec['validation']) if r.get('task','code')==task)/sum(r.get('task','code')==task for r in spec['validation'])
                for task in {r.get('task','code') for r in spec['validation']}}
        return sum(values)/len(values),groups
    initial,initial_groups=evaluate()
    emit(stage='baseline',validation_loss=initial,trainable_parameters=sum(p.numel() for p in params))
    best=initial;best_groups=initial_groups;best_step=0;best_params=[p.detach().clone() for p in params]
    losses=[];started=time.monotonic()
    total_steps=min(spec['steps'],96)
    generator=torch.Generator().manual_seed(42)
    order=torch.randperm(len(train),generator=generator).tolist()
    for step in range(total_steps):
        if stopping:break
        model.train();optimizer.zero_grad(set_to_none=True)
        loss=model(**train[order[step%len(train)]]).loss
        if not torch.isfinite(loss):raise ValueError('Loss non finita.')
        loss.backward();torch.nn.utils.clip_grad_norm_(params,1.0);optimizer.step()
        losses.append(float(loss.detach()))
        emit(stage='training',step=step+1,total_steps=total_steps,percent=round((step+1)/total_steps*100,1),loss=losses[-1],seconds=round(time.monotonic()-started))
        if (step+1)%12==0 or step+1==total_steps:
            current,groups=evaluate()
            safe_code=groups.get('code',0)<=max(initial_groups.get('code',0)*1.25,initial_groups.get('code',0)+.10)
            if math.isfinite(current) and current<best and safe_code:
                best=current;best_groups=groups;best_step=step+1
                best_params=[p.detach().clone() for p in params]
            emit(stage='validation',step=step+1,total_steps=total_steps,percent=round((step+1)/total_steps*100,1),validation_loss=current,best_step=best_step)
    with torch.no_grad():
        for parameter,value in zip(params,best_params):parameter.copy_(value)
    final=best
    delta=sum(float((p.detach()-old).abs().sum()) for p,old in zip(params,before))
    adapter=Path('/work/adapter');model.save_pretrained(adapter,safe_serialization=True)
    accepted=not stopping and bool(losses) and best_step>0 and math.isfinite(final) and final<initial and delta>0
    report={'initial_loss':initial,'final_loss':final,'parameter_delta_l1':delta,'steps':len(losses),
            'trainable_parameters':sum(p.numel() for p in params),'accepted':accepted,'interrupted':stopping,
            'seconds':round(time.monotonic()-started),'rss_mb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            'losses':losses,'best_step':best_step,'initial_groups':initial_groups,'final_groups':best_groups,
            'trained_layers':layers,'expanded_adapter':expanded,
            'validation_gain_percent':round((initial-final)/initial*100,2) if initial else 0,
            'training_tokens':sum(int((b['labels']!=-100).sum()) for b in train),
            'seen_training_tokens':sum(int((train[order[s%len(train)]]['labels']!=-100).sum()) for s in range(len(losses))),
            'truncated_examples':truncated,'max_sequence_tokens':maximum,
            'adapter_sha256':hashlib.sha256((adapter/'adapter_model.safetensors').read_bytes()).hexdigest()}
    if accepted:
        emit(stage='merging')
        # Safetensors serializes each shard into a temporary buffer. A single
        # 2 GB shard doubled live weight memory on the 8 GB Pi.
        merged=model.merge_and_unload();merged.save_pretrained('/work/merged',safe_serialization=True,max_shard_size='512MB')
        tokenizer.save_pretrained('/work/merged')
    report['rss_mb']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    Path('/work/report.json').write_text(json.dumps(report));emit(stage='complete',**report)
    if stopping:raise SystemExit(130)


if __name__=='__main__':main()
