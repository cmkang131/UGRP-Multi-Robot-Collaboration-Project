"""Bounded Mac countTokens probe over one saved text+RGB call; no generation/physics."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from harness.gemini_proxy import _to_gemini_multi_image_messages
from harness.s4_compact_prompt import transform
from scripts.gemma_fallback_proxy import Gemma,generate_body


def saved_request(path,call_id,images):
    row=next(x for x in json.loads(Path(path).read_text()) if x['call_id']==call_id)
    request=dict(messages=[dict(role='system',content=row['system']),dict(role='user',content=row['user'])],
                 image_refs=row['image_refs'],images=[])
    for ref in request['image_refs']:
        p=next(Path(images).glob(ref['bytes_sha256']+'.*'));raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=ref['bytes_sha256']:raise ValueError('image integrity mismatch')
        mime='image/png' if raw.startswith(b'\x89PNG') else 'image/jpeg'
        request['images'].append(dict(label=ref['label'],image='data:'+mime+';base64,'+base64.b64encode(raw).decode()))
    return request


def wire(request,model='gemma-4-31b-it'):
    return dict(model=model,temperature=.2,max_tokens=800,reasoning_effort='none',
                messages=_to_gemini_multi_image_messages(request['messages'],request['images']))


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--requests',type=Path,required=True)
    p.add_argument('--call-id',default='call-0261-r1');p.add_argument('--images',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    engine=Gemma(a.output/'probe',expected_model='gemma-4-31b-it',expected_version='001',standard=True)
    request=saved_request(a.requests,a.call_id,a.images);rows=[]
    for name,compact,lang in [('original_ko',False,'ko'),('compact_ko',True,'ko'),('compact_en',True,'en')]:
        r=transform(request,compact=compact,lang=lang);w=wire(r);count=engine.count_tokens(generate_body(w))
        rows.append(dict(variant=name,count=count,system_characters=len(r['messages'][0]['content']),
            image_count=len(r['images']),input_sha256=hashlib.sha256(json.dumps(w).encode()).hexdigest(),
            system=r['messages'][0]['content'],user=r['messages'][1]['content'],image_refs=r['image_refs']))
        print(name,count['totalTokens'])
    record=dict(model=engine.discovery,source=str(a.requests),source_sha256=hashlib.sha256(a.requests.read_bytes()).hexdigest(),
        call_id=a.call_id,rows=rows,model_generation_calls=0,qualifier='Old delivered Korean text retained verbatim in both compact variants; language delta isolates instructions, not hypothetical new English dialogue.')
    (a.output/'count-tokens-final.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
