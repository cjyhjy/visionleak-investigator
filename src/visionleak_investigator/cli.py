from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .common import PROJECT,read_json,write_json
from .core import CoreAdapter
from .workflow import run_task
from .demo import make_task

def main() -> int:
    p=argparse.ArgumentParser(prog='vli',description='Local deterministic evidence audit; models disabled by default')
    sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('doctor');d.add_argument('--core-path',type=Path);d.add_argument('--out',type=Path)
    d=sub.add_parser('demo');d.add_argument('--out',type=Path,required=True)
    r=sub.add_parser('run');r.add_argument('--task',type=Path,required=True);r.add_argument('--registry',type=Path,required=True);r.add_argument('--out',type=Path,required=True);r.add_argument('--mode',choices=['rules','agent'],default='rules');r.add_argument('--profiles')
    r=sub.add_parser('report');r.add_argument('--run',type=Path,required=True);r.add_argument('--format',choices=['html','json'],default='html')
    r=sub.add_parser('resume');r.add_argument('--run',type=Path,required=True);r.add_argument('--answers',type=Path,required=True)
    r=sub.add_parser('review-import');r.add_argument('--run',type=Path,required=True);r.add_argument('--review',type=Path,required=True)
    r=sub.add_parser('recover');r.add_argument('--run',type=Path,required=True)
    r=sub.add_parser('evaluate');r.add_argument('--out',type=Path,required=True);r.add_argument('--tasks',type=int,default=12);r.add_argument('--suite',choices=['synthetic-engineering'],default='synthetic-engineering')
    args=p.parse_args()
    try:
        if args.command=='doctor':
            value=CoreAdapter(args.core_path).doctor()
            if args.out:write_json(args.out,value,exclusive=True)
            print(json.dumps(value,ensure_ascii=False));return 0
        if args.command=='demo':make_task(args.out);print(args.out.resolve());return 0
        if args.command=='report':
            from .integrity import verify_run
            verify_run(args.run);print((args.run/f'report.{args.format}').resolve());return 0
        if args.command=='evaluate':
            from .evaluation import run_engineering_suite
            print(json.dumps(run_engineering_suite(args.out.resolve(),args.tasks),ensure_ascii=False));return 0
        if args.command=='recover':
            from .recovery import recover_interrupted
            value=recover_interrupted(args.run);print(json.dumps({'state':value['state'],'report':str((args.run/'report.html').resolve())}));return 2 if value['state']=='PARTIAL' else 0
        if args.command in ('resume','review-import'):
            from .interaction import resume_run,import_review
            result=resume_run(args.run,read_json(args.answers)) if args.command=='resume' else import_review(args.run,read_json(args.review))
            destination=Path(result['revision']['path'])
        else:
            result=run_task(read_json(args.task),read_json(args.registry),args.out,mode=args.mode,profiles=args.profiles.split(',') if args.profiles else None);destination=args.out
        print(json.dumps({'state':result['state'],'report':str((destination/'report.html').resolve()),'model_execution':'not_run'},ensure_ascii=False))
        return {'COMPLETED':0,'PARTIAL':2,'WAITING_USER':3,'FAILED':1}[result['state']]
    except (ValueError,OSError) as e:print(json.dumps({'status':'failed','error':str(e)},ensure_ascii=False),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
