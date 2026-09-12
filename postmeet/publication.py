"""Final publication boundary for local or legacy external worker results.

Workers may process local assets; every returned playback artifact is normalized
by the same playback and layout renderers before it is exposed for download.
"""
from __future__ import annotations
import copy
import json
import sys
from .playback import ensure_playback, replace_playback_html, extract_youtube_id
from .hydration import hydrate
from .render import render


def finalize(result: dict, request: dict | None = None) -> dict:
    if not isinstance(result, dict) or not isinstance(result.get("payload"), dict):
        raise ValueError("Worker must return a source payload before artifacts can be published.")
    output = copy.deepcopy(result)
    payload = output["payload"]
    request = request or {}
    association = request.get("youtube_url") or request.get("youtubeUrl") or (request.get("media_url") if extract_youtube_id(request.get("media_url")) else "")
    if association:
        payload["youtube_url"] = association
    if request.get("source"):
        payload.setdefault("source_media", {}).setdefault("original_ref", request["source"])
    descriptor = ensure_playback(payload)
    if descriptor["provider"] != "youtube":
        return output

    def rewrite(value, depth=0):
        if depth > 80:
            raise ValueError("Artifact nesting exceeds publication limit")
        if isinstance(value, dict):
            if "type" in value and "props" in value:
                # Use the same template transformation, including legacy media elements.
                return hydrate({"children": [value]}, payload)["children"][0]
            return {k: rewrite(v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            return [rewrite(v, depth + 1) for v in value]
        if isinstance(value, str):
            if value.lstrip().startswith(("{", "[")):
                try:
                    return json.dumps(rewrite(json.loads(value), depth + 1), ensure_ascii=False)
                except json.JSONDecodeError:
                    pass
            return replace_playback_html(value, descriptor)
        return value

    # The source payload deliberately retains local processing references.
    for key in list(output):
        if key != "payload":
            output[key] = rewrite(output[key])
    output["html"] = render(payload)
    if isinstance(output.get("layout"), dict):
        output["layout"] = hydrate(output["layout"], payload)
    output.setdefault("manifest", {})["playback"] = dict(descriptor)
    return output


if __name__ == "__main__":
    data = json.load(sys.stdin)
    print(json.dumps(finalize(data["result"], data.get("request")), ensure_ascii=False))
