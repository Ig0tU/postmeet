from __future__ import annotations
import argparse, json
from pathlib import Path
from .validation import validate
from .hydration import hydrate
from .render import render
from .inject import inject_youtube_embed

def main():
    p = argparse.ArgumentParser(prog="postmeet", description="Turn meeting evidence into a validated YOOtheme-ready meeting page")
    sub = p.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate"); v.add_argument("payload")
    h = sub.add_parser("hydrate"); h.add_argument("payload"); h.add_argument("--preset", default="presets/meeting_lens_full.json"); h.add_argument("-o", "--output", default="layout.json")
    r = sub.add_parser("render"); r.add_argument("payload"); r.add_argument("-o", "--output", default="meeting.html")
    x = sub.add_parser("run"); x.add_argument("source"); x.add_argument("--site-url", default=""); x.add_argument("--media-root", default=""); x.add_argument("--model", default=""); x.add_argument("--output-dir", default="postmeet-output"); x.add_argument("--preset", default="presets/meeting_lens_full.json"); x.add_argument("--youtube-url", default=""); x.add_argument("--media-url", default="")
    inj = sub.add_parser("inject-youtube", help="Inject YouTube iframe embed into target xs-meeting-lens HTML")
    inj.add_argument("target_html", nargs="?", help="Path to target HTML file")
    inj.add_argument("--youtube-url", required=True, help="YouTube video URL")
    inj.add_argument("--video-title", default="", help="Legacy option; exact title is resolved from YouTube metadata")
    inj.add_argument("--target-html", dest="target_html_opt", help="Path to target HTML file (optional alternative to positional)")
    inj.add_argument("-o", "--output", default="-", help="Output file path (default stdout)")

    args = p.parse_args()

    if args.command == "inject-youtube":
        target_path = args.target_html_opt or args.target_html
        if not target_path:
            p.error("the following arguments are required: target_html or --target-html")
        target_content = Path(target_path).read_text(encoding="utf-8")
        out_html = inject_youtube_embed(target_content, youtube_url=args.youtube_url, video_title=args.video_title)
        if args.output == "-":
            print(out_html)
        else:
            Path(args.output).write_text(out_html, encoding="utf-8")
        return

    if args.command == "validate":
        result = validate(json.loads(Path(args.payload).read_text()))
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["ok"] else 1)

    if args.command == "run":
        from .pipeline import run
        print(json.dumps(run(args.source, site_url=args.site_url, media_root=args.media_root, model=args.model, output_dir=args.output_dir, preset_path=args.preset, youtube_url=args.youtube_url, media_url=args.media_url), indent=2))
        return

    payload = json.loads(Path(args.payload).read_text())
    if args.command == "render":
        Path(args.output).write_text(render(payload), encoding="utf-8")
        print(args.output)
        return
    if args.command == "hydrate":
        result = validate(payload)
        if not result["ok"]:
            print(json.dumps(result, indent=2))
            raise SystemExit(1)
        Path(args.output).write_text(json.dumps(hydrate(json.loads(Path(args.preset).read_text()), payload), indent=2), encoding="utf-8")
        print(args.output)
        return



if __name__ == "__main__":
    main()
