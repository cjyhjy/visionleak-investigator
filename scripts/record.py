"""Record the exact command, exit status and logs; never convert failure to success."""
import datetime, json, pathlib, subprocess, sys, time
name, *argv = sys.argv[1:]
root = pathlib.Path(__file__).resolve().parents[1]
logs = root / 'reports/logs'; logs.mkdir(parents=True, exist_ok=True)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
log = logs / f'{stamp}-{name}.log'
start = time.monotonic()
with log.open('w') as out:
    result = subprocess.run(argv, cwd=root, stdout=out, stderr=subprocess.STDOUT)
record = dict(name=name, argv=argv, cwd=str(root), exit_code=result.returncode,
              wall_seconds=time.monotonic()-start, log=str(log.relative_to(root)), recorded_at=stamp)
with (root/'reports/commands.jsonl').open('a') as out: out.write(json.dumps(record)+'\n')
print(json.dumps(record)); print(log.read_text()[-5000:]); sys.exit(result.returncode)
