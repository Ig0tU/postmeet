import json
from pathlib import Path
from postmeet.validation import validate
from postmeet.hydration import hydrate

ROOT=Path(__file__).resolve().parents[1]

def payload(): return json.loads((ROOT/"examples/sample_payload.json").read_text())
def preset(): return json.loads((ROOT/"presets/meeting_lens_full.json").read_text())

def test_sample_validates():
    result=validate(payload())
    assert result["ok"], result
    assert result["agenda_count"]==2

def test_hydration_fills_layout_and_preserves_items():
    layout=hydrate(preset(),payload())
    assert layout["version"]=="5.0.43"
    lens=[]
    def walk(n):
        if isinstance(n,dict):
            if n.get("type")=="xs_meeting_lens": lens.append(n)
            for c in n.get("children") or []: walk(c)
        elif isinstance(n,list):
            for c in n: walk(c)
    walk(layout)
    assert len(lens)==1
    assert len(lens[0]["children"])==2
    assert lens[0]["children"][1]["props"]["motion_text"].startswith("I move")
