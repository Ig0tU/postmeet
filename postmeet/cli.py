from __future__ import annotations
import argparse,json
from pathlib import Path
from .validation import validate
from .hydration import hydrate

def main():
 p=argparse.ArgumentParser(prog="postmeet",description="Turn meeting evidence into validated YOOtheme layout JSON")
 sub=p.add_subparsers(dest="command",required=True)
 v=sub.add_parser("validate"); v.add_argument("payload")
 h=sub.add_parser("hydrate"); h.add_argument("payload"); h.add_argument("--preset",default="presets/meeting_lens_full.json"); h.add_argument("-o","--output",default="layout.json")
 args=p.parse_args()
 if args.command=="validate":
  result=validate(json.loads(Path(args.payload).read_text())); print(json.dumps(result,indent=2)); raise SystemExit(0 if result["ok"] else 1)
 payload=json.loads(Path(args.payload).read_text()); result=validate(payload)
 if not result["ok"]: print(json.dumps(result,indent=2)); raise SystemExit(1)
 layout=hydrate(json.loads(Path(args.preset).read_text()),payload); Path(args.output).write_text(json.dumps(layout,indent=2),encoding="utf-8"); print(args.output)
if __name__=="__main__": main()
