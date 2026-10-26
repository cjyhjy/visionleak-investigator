"""Run only during explicit dependency setup; never silently replace a runtime lock."""
import argparse
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from visionleak_investigator.runtime import pin_runtime

parser = argparse.ArgumentParser()
parser.add_argument('--migrate-runtime', action='store_true')
parser.add_argument('--receipt', type=Path)
args = parser.parse_args()
try:
    print(json.dumps(pin_runtime(root, migrate=args.migrate_runtime, receipt=args.receipt)))
except (ValueError, OSError) as exc:
    raise SystemExit(str(exc))
