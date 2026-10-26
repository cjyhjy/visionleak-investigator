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


def make_hard_negative_task(base: Path):
    """Declared synthetic negative sources with flat/gradient dHash ambiguity."""
    base.mkdir(parents=True,exist_ok=False)
    for split in ('train','test'):(base/'images'/split).mkdir(parents=True)
    Image.new('RGB',(48,48),(60,60,60)).save(base/'images/train/001.png')
    Image.new('RGB',(48,48),(90,90,90)).save(base/'images/test/002.png')
    for name,offset in [('train/003.png',0),('test/004.png',20)]:
        im=Image.new('RGB',(48,48))
        im.putdata([(20+x*4+offset,20+x*4+offset,20+x*4+offset) for y in range(48) for x in range(48)])
        im.save(base/'images'/name)
    task=read_json(PROJECT/'examples/task.example.json')
    task.update(task_id='negative-fixture',goal='content_audit',goal_confirmed=True,
                goal_evidence_refs=['user.local-task'],metadata_ref=None,context_refs=[],
                entity_key=None,entity_key_confirmed=False,entity_key_evidence_refs=[],
                request_text='受控合成工程验收：检查图像内容与旋转、镜像、裁切。')
    registry={'datasets':{task['dataset_ref']:str((base/'images').resolve())},'documents':{},
              'confirmations':{'user.local-task':{'kind':'user.goal_confirmation','goal':'content_audit','actor':'local synthetic fixture generator'}}}
    write_json(base/'task.json',task);write_json(base/'registry.json',registry)
    write_json(base/'fixture-source.json',{'kind':'synthetic declared hard negatives','independent_test':False,
        'license':'self-generated','model_calls':0,'generator_version':1,
        'parameters':{'size':[48,48],'flat_values':[60,90],'gradient_base':20,'gradient_step':4,'gradient_offsets':[0,20]},
        'truth_basis':'Four separately constructed synthetic source records; all cross-split pairs labelled unrelated for this controlled negative test, not a natural-scene source judgement.'})
    return task,registry
