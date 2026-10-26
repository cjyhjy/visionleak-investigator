from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from pathlib import Path
import os
from jsonschema import Draft202012Validator
from PIL import Image
from .common import PROJECT,read_json,digest,file_hash,no_symlink,safe_child

def validate(value: Any, schema: str) -> None:
    errors=list(Draft202012Validator(read_json(PROJECT/f'contracts/{schema}.schema.json')).iter_errors(value))
    if errors:raise ValueError(f'{schema}: '+errors[0].message)

@dataclass(frozen=True)
class TaskSpec:
    value: dict[str,Any]
    @classmethod
    def parse(cls,value: dict) -> TaskSpec:
        validate(value,'task');l=value['limits']
        if l['max_tool_calls']<=l['finalization_reserve_tool_calls'] or l['max_tool_wall_seconds']<=l['finalization_reserve_seconds']:raise ValueError('Budget must exceed finalization reserve')
        return cls(value)

@dataclass(frozen=True)
class AgentAction:
    value: dict[str,Any]
    @classmethod
    def parse(cls,value: dict) -> AgentAction:
        validate(value,'action');return cls(value)

class Registry:
    def __init__(self,value: dict):
        if set(value)-{'datasets','documents','confirmations'}:raise ValueError('Unknown registry fields')
        self.value=value
    def dataset(self,ref: str) -> Path:
        if ref not in self.value['datasets']:raise ValueError('Unregistered dataset')
        root=no_symlink(Path(self.value['datasets'][ref]))
        if not root.is_dir():raise ValueError('Dataset is not directory')
        return root
    def document(self,ref: str) -> Path:
        if ref not in self.value.get('documents',{}):raise ValueError('Unregistered document')
        item=self.value['documents'][ref];p=no_symlink(Path(item['path']))
        if p.suffix.lower() not in ('.md','.txt','.csv') or not p.is_file() or p.stat().st_size>1024*1024:raise ValueError('Unsupported or oversized registered document')
        if item.get('sha256')!=file_hash(p):raise ValueError('Registered document digest changed')
        return p
    def check_confirmations(self,task: dict) -> None:
        confirmations=self.value.get('confirmations',{})
        for flag,refs,field,kind in [('goal_confirmed','goal_evidence_refs','goal','user.goal_confirmation'),('entity_key_confirmed','entity_key_evidence_refs','entity_key','user.entity_key_confirmation')]:
            if task[flag] and not any(confirmations.get(ref,{}).get('kind')==kind and confirmations[ref].get(field)==task[field] and confirmations[ref].get('actor') for ref in task[refs]):raise ValueError('Confirmation is missing from host registry')

SPLITS={a:s for s,aliases in read_json(PROJECT/'core-capabilities.json')['input']['splitAliases'].items() for a in aliases}
EXTENSIONS=set(read_json(PROJECT/'core-capabilities.json')['input']['extensions'])
def input_manifest(root: Path, limits: dict) -> dict:
    no_symlink(root);rows=[];split_images=0
    for directory,dirs,files in os.walk(root,followlinks=False):
        for name in sorted(dirs+files):
            p=Path(directory)/name;no_symlink(p)
            if len(p.relative_to(root).parts)>64:raise ValueError('Input directory depth limit')
        for name in sorted(files):
            p=Path(directory)/name
            if not p.is_file():raise ValueError('Nonregular input')
            rel=p.relative_to(root).as_posix();split=SPLITS.get(rel.split('/')[0]);image=p.suffix.lower() in EXTENSIONS
            if image and not split:raise ValueError('Image outside supported split directories')
            size=p.stat().st_size
            # Stream hashes: no whole-file allocation, all source files participate in identity.
            row={'path':rel,'sha256':file_hash(p),'bytes':size,'image_split':split,'supported_image':image,'pixels':None}
            if image:
                split_images+=1
                if size<=limits['max_file_bytes']:
                    try:
                        with Image.open(p) as im: row['pixels']=im.width*im.height
                    except (OSError,ValueError,Image.DecompressionBombError):pass
            rows.append(row)
            if len(rows)>100000:raise ValueError('Input manifest entry limit')
    if not split_images:raise ValueError('No supported images in split directories')
    rows.sort(key=lambda r:r['path'])
    return {'digest':digest(rows),'files':rows,'image_count':split_images,'estimated_source_pixels':sum(r['pixels'] or 0 for r in rows),'header_unknown_count':sum(r['supported_image'] and r['pixels'] is None for r in rows),'snapshot_guarantee':'before/after hashes; not an atomic filesystem snapshot'}
