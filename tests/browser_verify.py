"""Opt-in real Chromium/output verification (live YouTube metadata, no mocks).
Run: PYTHONPATH=. python3 tests/browser_verify.py --output /tmp/postmeet-evidence
Requires: pip install playwright; python3 -m playwright install chromium
"""
import argparse
import copy
import functools
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from postmeet.pipeline import run
from postmeet.render import render
from postmeet.hydration import hydrate
from postmeet.inject import inject_youtube_embed
from postmeet.publication import finalize


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True)
    ap.add_argument('--youtube-url', default='https://www.youtube.com/watch?v=jNQXAC9IVRw')
    args = ap.parse_args()
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    # Synthetic timestamped fixture exercises the real caption pipeline. It is
    # not presented as a transcript of the metadata verification video.
    source = out / 'synthetic-fixture.vtt'
    source.write_text('WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nCall to order.\n\n00:00:06.000 --> 00:00:10.000\nI move to approve the agenda.\n\n00:00:11.000 --> 00:00:15.000\nMotion carries.\n')
    run(str(source), output_dir=str(out / 'pipeline'), youtube_url=args.youtube_url)
    payload = json.loads((out / 'pipeline/payload.json').read_text())
    descriptor = payload['playback']; embed = descriptor['embed_url']; title = descriptor['title']
    assert payload['source_media']['resolved_ref'] == str(source)
    (out / 'render-function.html').write_text(render(copy.deepcopy(payload)))
    subprocess.run([sys.executable, '-m', 'postmeet.cli', 'render', str(out/'pipeline/payload.json'), '-o', str(out/'render-cli.html')], cwd=root, check=True, capture_output=True)
    subprocess.run([sys.executable, '-m', 'postmeet.render', str(out/'pipeline/payload.json'), '-o', str(out/'render-module.html')], cwd=root, check=True, capture_output=True)
    legacy = '<!doctype html><html><head><title>Legacy multi-player injection verification</title></head><body><video src="old.mp4"></video><iframe src="old.mp4"></iframe></body></html>'
    (out/'legacy.html').write_text(legacy)
    (out/'inject-function.html').write_text(inject_youtube_embed(legacy, args.youtube_url, playback=descriptor))
    subprocess.run([sys.executable, '-m', 'postmeet.cli', 'inject-youtube', str(out/'legacy.html'), '--youtube-url', args.youtube_url, '-o', str(out/'inject-cli.html')], cwd=root, check=True, capture_output=True)
    subprocess.run([sys.executable, '-m', 'postmeet.cli', 'hydrate', str(out/'pipeline/payload.json'), '--preset', str(root/'presets/meeting_lens_full.json'), '-o', str(out/'hydrate-cli.json')], cwd=root, check=True, capture_output=True)
    layout = json.loads((out/'hydrate-cli.json').read_text())
    def content_nodes(value):
        if isinstance(value, dict):
            if value.get('type') == 'html' and '<iframe' in str((value.get('props') or {}).get('content', '')):
                yield value['props']['content']
            for child in value.values():
                yield from content_nodes(child)
        elif isinstance(value, list):
            for child in value: yield from content_nodes(child)
    (out/'layout-export.html').write_text('<!doctype html><html><body>' + '\n'.join(content_nodes(layout)) + '</body></html>')
    custom = hydrate({'children': [{'type':'video','props':{'video':'old.mp4'}}, {'type':'html','props':{'content':'<video src="old.mp4"></video>'}}]}, copy.deepcopy(payload))
    (out/'custom-layout.html').write_text('<!doctype html><html><body>'+'\n'.join(content_nodes(custom))+'</body></html>')
    result = finalize({'ok':True, 'payload':copy.deepcopy(payload), 'html':legacy, 'layout':layout, 'prepared':{'mobile':legacy}, 'bundle':json.dumps({'html':legacy})}, {'youtube_url':args.youtube_url})
    (out/'worker-publication.html').write_text(result['html'])
    (out/'prepared-mobile.html').write_text(result['prepared']['mobile'])
    (out/'bundle-html.html').write_text(json.loads(result['bundle'])['html'])
    native = copy.deepcopy(json.loads((root/'examples/sample_payload.json').read_text()))
    native['recording_url'] = 'local.mp4'
    (out/'native.html').write_text(render(native))
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(Quiet,directory=str(out)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    modes = ['pipeline/meeting.html','render-function.html','render-cli.html','render-module.html','inject-function.html','inject-cli.html','layout-export.html','custom-layout.html','worker-publication.html','prepared-mobile.html','bundle-html.html']
    evidence = {'youtube':descriptor, 'fixture':'Synthetic VTT processing; real live YouTube oEmbed metadata. No ASR/model inference tested.', 'checks':[]}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width':1440,'height':1000})
        for mode in modes:
            errors=[]
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(base+'/'+mode, wait_until='domcontentloaded')
            page.locator('iframe').first.wait_for(state='attached')
            frames=page.locator('iframe').evaluate_all('(els)=>els.map(e=>({src:e.src,title:e.title,outerHTML:e.outerHTML}))')
            assert frames, mode
            assert page.locator('video,audio,source').count()==0, mode
            for frame in frames:
                u=urlsplit(frame['src'])
                assert u.scheme+'://'+u.netloc+u.path == embed, (mode,frame)
                assert frame['title']==title, (mode,frame)
            assert not errors, (mode,errors)
            evidence['checks'].append({'mode':mode,'iframe_count':len(frames),'native_count':0,'frames':frames,'page_errors':errors})
            if mode in ('pipeline/meeting.html','layout-export.html','prepared-mobile.html'):
                page.locator('iframe').first.scroll_into_view_if_needed()
                page.screenshot(path=str(out/(mode.replace('/','-')+'.png')))
        page.goto(base+'/pipeline/meeting.html', wait_until='domcontentloaded')
        page.emulate_media(media='print')
        assert page.locator('iframe').count()==1 and page.locator('video').count()==0
        evidence['checks'].append({'mode':'print DOM','iframe_count':1,'native_count':0})
        page.emulate_media(media='screen')
        page.goto(base+'/native.html', wait_until='domcontentloaded')
        assert page.locator('video').count()==1 and page.locator('iframe').count()==0
        assert page.locator('video source').get_attribute('src')=='local.mp4'
        evidence['checks'].append({'mode':'native control','iframe_count':0,'native_count':1})
        page.screenshot(path=str(out/'native-control.png'))
        browser.close()
    server.shutdown()
    evidence['limitations']=['Checks inspect actual Chromium DOM, not a deployed Joomla/YOOtheme host.', 'YouTube iframe presence/title verified; autoplay, audible playback and cross-origin seek success not asserted.', 'Next production build unavailable because npm registry returned 403 for undici-types.']
    (out/'browser-evidence.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False))
    print(json.dumps({'checks':len(evidence['checks']),'title':title,'embed_url':embed,'evidence':str(out/'browser-evidence.json')}))

if __name__=='__main__': main()
