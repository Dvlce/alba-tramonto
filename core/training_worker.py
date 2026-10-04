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
    if Path('/previous/adapter_config.json').exists():
        model=PeftModel.from_pretrained(base,'/previous',is_trainable=True,local_files_only=True)
    else:
        model=get_peft_model(base,LoraConfig(task_type='CAUSAL_LM',r=4,lora_alpha=8,lora_dropout=.05,
              target_modules=['q_proj','v_proj'],layers_to_transform=[22,23]))
    params=[p for p in model.parameters() if p.requires_grad]
    before=[p.detach().clone() for p in params]
    optimizer=torch.optim.AdamW(params,lr=.0007)
    def batch(row):
        messages=[{'role':'system','content':'Sei Notte. Scrivi soltanto una funzione Python corretta.'},
                  {'role':'user','content':row['prompt']}]
        prefix=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)
        answer=tokenizer.encode(row['answer']+tokenizer.eos_token,add_special_tokens=False)
        ids=(prefix+answer)[:128]
        labels=([-100]*len(prefix)+answer)[:len(ids)]
        if not any(x!=-100 for x in labels): raise ValueError('Esempio senza token di risposta.')
        return {'input_ids':torch.tensor([ids]),'labels':torch.tensor([labels])}
    train=[batch(r) for r in spec['train']]
    validation=[batch(r) for r in spec['validation']]
    def evaluate():
        model.eval()
        with torch.inference_mode():return sum(float(model(**b).loss) for b in validation)/len(validation)
    initial=evaluate();emit(stage='baseline',validation_loss=initial,trainable_parameters=sum(p.numel() for p in params))
    losses=[];started=time.monotonic()
    for step in range(min(spec['steps'],48)):
        if stopping:break
        model.train();optimizer.zero_grad(set_to_none=True)
        loss=model(**train[step%len(train)]).loss
        if not torch.isfinite(loss):raise ValueError('Loss non finita.')
        loss.backward();torch.nn.utils.clip_grad_norm_(params,1.0);optimizer.step()
        losses.append(float(loss.detach()))
        emit(stage='training',step=step+1,total_steps=spec['steps'],loss=losses[-1],seconds=round(time.monotonic()-started))
    final=evaluate()
    delta=sum(float((p.detach()-old).abs().sum()) for p,old in zip(params,before))
    adapter=Path('/work/adapter');model.save_pretrained(adapter,safe_serialization=True)
    accepted=not stopping and bool(losses) and math.isfinite(final) and final<=initial and delta>0
    report={'initial_loss':initial,'final_loss':final,'parameter_delta_l1':delta,'steps':len(losses),
            'trainable_parameters':sum(p.numel() for p in params),'accepted':accepted,'interrupted':stopping,
            'seconds':round(time.monotonic()-started),'rss_mb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            'losses':losses,'adapter_sha256':hashlib.sha256((adapter/'adapter_model.safetensors').read_bytes()).hexdigest()}
    if accepted:
        emit(stage='merging')
        merged=model.merge_and_unload();merged.save_pretrained('/work/merged',safe_serialization=True,max_shard_size='2GB')
        tokenizer.save_pretrained('/work/merged')
    report['rss_mb']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    Path('/work/report.json').write_text(json.dumps(report));emit(stage='complete',**report)
    if stopping:raise SystemExit(130)


if __name__=='__main__':main()
