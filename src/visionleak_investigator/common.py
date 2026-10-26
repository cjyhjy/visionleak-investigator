from __future__ import annotations
import hashlib, json, os, tempfile
from pathlib import Path
from datetime import datetime, UTC
from typing import Any
PROJECT = Path(__file__).resolve().parents[2]
def now() -> str: return datetime.now(UTC).isoformat()
def canonical(value: Any) -> bytes: return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(value: Any) -> str: return hashlib.sha256(canonical(value)).hexdigest()
def file_hash(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(262144),b''): h.update(chunk)
    return h.hexdigest()
def no_symlink(path: Path) -> Path:
    p=Path(os.path.abspath(path))
    for node in [p,*p.parents]:
        if node.is_symlink(): raise ValueError(f'Symlink rejected: {node}')
    return p

def safe_child(root: Path, name: str) -> Path:
    if not isinstance(name,str) or not name or '\\' in name or any(ord(c)<32 for c in name):raise ValueError('Unsafe path')
    if name.startswith('/') or any(x in ('','.','..') for x in name.split('/')):raise ValueError('Unsafe path')
    p=no_symlink(root/name)
    if not p.is_relative_to(root.resolve()):raise ValueError('Path escaped registry root')
    return p

def read_json(path: Path) -> Any:
    no_symlink(path)
    if path.stat().st_size>64*1024*1024:raise ValueError('JSON input too large')
    def pairs(rows):
        out={}
        for k,v in rows:
            if k in out:raise ValueError('Duplicate JSON key')
            out[k]=v
        return out
    return json.loads(path.read_text(),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))

def write_json(path: Path, value: Any, *, exclusive: bool=False) -> None:
    no_symlink(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if exclusive:
        with path.open('x') as f:f.write(data)
    else:
        fd,temp=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
        try:
            with os.fdopen(fd,'w') as f:f.write(data);f.flush();os.fsync(f.fileno())
            os.replace(temp,path)
        finally:
            if os.path.exists(temp):os.unlink(temp)

def append_json(path: Path,value: Any) -> None:
    no_symlink(path)
    with path.open('a') as f:f.write(canonical(value).decode()+'\n');f.flush();os.fsync(f.fileno())
