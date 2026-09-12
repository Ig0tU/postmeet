import json
from postmeet.publication import finalize
from postmeet.hydration import hydrate


def test_legacy_worker_all_variants_are_canonical(youtube_metadata):
    original = {"ok": True, "payload": {"recording_url": "local.mp4", "items": []},
                "html": '<video src="local.mp4"></video>',
                "layout": {"children": [{"type": "xs_meeting_lens", "props": {"recording_url": "local.mp4"}}]},
                "prepared": {"mobile": '<video src="local.mp4"></video>'},
                "bundle": json.dumps({"alternate": '<video src="local.mp4"></video>'})}
    output = finalize(original, {"youtube_url": "https://youtu.be/jNQXAC9IVRw"})
    for field in ("html", "layout", "prepared", "bundle"):
        value = json.dumps(output[field])
        assert '<video' not in value
        assert "youtube.com/embed/jNQXAC9IVRw" in value
    assert output["layout"]["children"][0]["type"] == "html"
    assert '<iframe' in output["layout"]["children"][0]["props"]["content"]
    assert '<video' in original["html"]
    assert output["manifest"]["playback"] == output["payload"]["playback"]
    youtube_metadata.assert_called_once()


def test_native_worker_behavior_preserved():
    original = {"ok": True, "payload": {"recording_url": "local.mp4"}, "html": '<video src="local.mp4"></video>'}
    assert finalize(original)["html"] == original["html"]


def test_layout_uses_real_html_element_not_unconsumed_new_props(youtube_metadata):
    payload = {"youtube_url": "https://youtu.be/jNQXAC9IVRw", "items": []}
    layout = hydrate({"children": [{"type": "xs_meeting_lens", "props": {}}]}, payload)
    element = layout["children"][0]
    assert element["type"] == "html"
    assert '<iframe' in element["props"]["content"]
    assert '<video' not in element["props"]["content"]
