from __future__ import annotations
import argparse,json
from pathlib import Path
from .validation import validate
from .hydration import hydrate
from .render import render

def main():
 p=argparse.ArgumentParser(prog="postmeet",description="Turn meeting evidence into a validated YOOtheme-ready meeting page")
 sub=p.add_subparsers(dest="command",required=True)
 v=sub.add_parser("validate"); v.add_argument("payload")
 h=sub.add_parser("hydrate"); h.add_argument("payload"); h.add_argument("--preset",default="presets/meeting_lens_full.json"); h.add_argument("-o","--output",default="layout.json")
 r=sub.add_parser("render"); r.add_argument("payload"); r.add_argument("-o","--output",default="meeting.html")
 x=sub.add_parser("run"); x.add_argument("source"); x.add_argument("--site-url",default=""); x.add_argument("--media-root",default=""); x.add_argument("--model",default=""); x.add_argument("--output-dir",default="postmeet-output"); x.add_argument("--preset",default="presets/meeting_lens_full.json")
 args=p.parse_args()
 if args.command=="validate":
  result=validate(json.loads(Path(args.payload).read_text())); print(json.dumps(result,indent=2)); raise SystemExit(0 if result["ok"] else 1)
 payload=json.loads(Path(args.payload).read_text())
 if args.command=="render": Path(args.output).write_text(render(payload),encoding="utf-8"); print(args.output); return
 if args.command=="hydrate":
  result=validate(payload)
  if not result["ok"]: print(json.dumps(result,indent=2)); raise SystemExit(1)
  Path(args.output).write_text(json.dumps(hydrate(json.loads(Path(args.preset).read_text()),payload),indent=2),encoding="utf-8"); print(args.output); return
 from .pipeline import run
 print(json.dumps(run(args.source,site_url=args.site_url,media_root=args.media_root,model=args.model,output_dir=args.output_dir,preset_path=args.preset),indent=2))
if __name__=="__main__": main()
