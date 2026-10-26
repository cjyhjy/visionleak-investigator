"""Host-only isolated A/B/C worker, never a registered Planner tool."""
import argparse
import json
from pathlib import Path

from .common import read_json
from .workflow import run_task, run_baseline


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',type=Path,required=True)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--condition',choices=['A','B','C'],required=True)
    args=parser.parse_args()
    task,registry=read_json(args.task),read_json(args.registry)
    if task['privacy']['remote_model_allowed']:
        raise ValueError('A/B/C worker requires a local-only task')
    result=run_task(task,registry,args.out) if args.condition=='C' else run_baseline(task,registry,args.out,args.condition)
    print(json.dumps({'state':result['state'],'model_execution':result['model_execution']}))
    return {'COMPLETED':0,'PARTIAL':2,'WAITING_USER':3,'FAILED':1}[result['state']]


if __name__=='__main__':
    raise SystemExit(main())
