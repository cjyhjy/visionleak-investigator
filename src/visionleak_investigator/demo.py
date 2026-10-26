"""Self-generated engineering fixtures; never an independent research test set."""
from pathlib import Path
import random, shutil
from PIL import Image, PngImagePlugin
from .common import PROJECT,read_json,write_json

def make_dataset(root: Path,seed: int=20261026) -> None:
    for s in ['train','validation','test']:(root/s).mkdir(parents=True,exist_ok=False)
    rng=random.Random(seed)
    image=Image.new('RGB',(96,96));image.putdata([(rng.randrange(256),rng.randrange(256),rng.randrange(256)) for _ in range(96*96)])
    image.save(root/'train/001.png');shutil.copyfile(root/'train/001.png',root/'test/002.png')
    info=PngImagePlugin.PngInfo();info.add_text('fixture','re-encoded controlled fixture')
    image.save(root/'validation/003.png',pnginfo=info,compress_level=0)
    image.transpose(Image.Transpose.ROTATE_90).save(root/'test/004.png')
    image.crop((7,9,79,81)).resize((96,96)).save(root/'validation/005.png')
    image=Image.new('RGB',(96,96));image.putdata([(rng.randrange(256),rng.randrange(256),rng.randrange(256)) for _ in range(96*96)])
    image.save(root/'train/006.png')

def make_task(base: Path,seed: int=20261026):
    base.mkdir(parents=True,exist_ok=True);make_dataset(base/'images',seed)
    task=read_json(PROJECT/'examples/task.example.json')
    task.update(goal='content_audit',goal_confirmed=True,goal_evidence_refs=['user.local-task'],metadata_ref=None,context_refs=[],entity_key=None,entity_key_confirmed=False,entity_key_evidence_refs=[])
    registry={'datasets':{'demo-dataset':str((base/'images').resolve())},'documents':{},'confirmations':{'user.local-task':{'kind':'user.goal_confirmation','goal':'content_audit','actor':'local synthetic fixture generator'}}}
    write_json(base/'task.json',task);write_json(base/'registry.json',registry)
    write_json(base/'fixture-source.json',{'kind':'synthetic-controlled-engineering','seed':seed,'independent_test':False,'license':'self-generated','model_calls':0})
    return task,registry
