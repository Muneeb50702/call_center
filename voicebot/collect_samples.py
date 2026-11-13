#!/usr/bin/env python3
"""
Generate a set of Fish Audio voice samples so you can A/B accents before
picking one for the bot.

Every voice reads the same sentence, which is what makes them comparable. The
line is chosen to exercise prosody: a greeting, a question, numbers, and a
clause break.

    python voicebot/collect_samples.py                  # curated accent set
    python voicebot/collect_samples.py --search irish   # whatever matches
    python voicebot/collect_samples.py --text "custom line to read"

Writes voicebot/samples/*.wav plus manifest.json, which the web UI reads to
populate its voice picker.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core  # noqa: E402

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")

DEFAULT_LINE = (
    "Hi there! I can help with just about anything, from explaining a tricky "
    "idea to drafting an email. What would you like to start with?"
)

# Searched by title at run time rather than hardcoding ids, so this keeps
# working as the public library changes. label -> search term.
CURATED = [
    ("default", None),  # whatever s2.1-pro-free uses with no reference_id
    ("british", "british"),
    ("american", "american"),
    ("indian", "indian"),
    ("australian", "australian"),
    ("irish", "irish"),
    ("scottish", "scottish"),
]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "voice"


def synth(label: str, voice_id: str | None, title: str, text: str) -> dict | None:
    name = f"{slug(label)}__{slug(title)}.wav" if voice_id else f"{slug(label)}.wav"
    path = os.path.join(SAMPLES_DIR, name)
    t0 = time.monotonic()
    try:
        pcm = core.tts_pcm(text, voice_id)
    except core.ConfigError as e:
        print(f"  !! {label:<11} {title[:38]:<38} {e}")
        return None
    with open(path, "wb") as f:
        f.write(core.wrap_wav(pcm))
    secs = core.pcm_seconds(pcm)
    print(f"  ok {label:<11} {title[:38]:<38} {secs:5.1f}s audio "
          f"in {time.monotonic() - t0:4.1f}s -> samples/{name}")
    return {
        "file": name,
        "label": label,
        "voice_id": voice_id,
        "title": title,
        "seconds": round(secs, 2),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Collect Fish Audio voice samples")
    p.add_argument("--text", default=DEFAULT_LINE, help="line every voice reads")
    p.add_argument("--search", help="collect voices matching this term instead")
    p.add_argument("--limit", type=int, default=6,
                   help="voices per search term (default 6)")
    args = p.parse_args()

    if core.missing_keys() and "FISH_API_KEY" in core.missing_keys():
        sys.exit("error: FISH_API_KEY is not set (repo .env or environment)")

    os.makedirs(SAMPLES_DIR, exist_ok=True)
    print(f"model={core.FISH_MODEL}\nline=\"{args.text[:70]}...\"\n")

    targets: list[tuple[str, str | None, str]] = []  # (label, voice_id, title)
    if args.search:
        for v in core.list_voices(args.search, args.limit):
            targets.append((args.search, v["id"], v["title"]))
        if not targets:
            sys.exit(f"no voices matched {args.search!r}")
    else:
        for label, term in CURATED:
            if term is None:
                targets.append((label, None, "s2.1-pro-free default"))
                continue
            found = core.list_voices(term, 2)
            if not found:
                print(f"  -- {label:<11} no library match, skipping")
                continue
            for v in found[:1]:
                targets.append((label, v["id"], v["title"]))

    entries = [e for label, vid, title in targets
               if (e := synth(label, vid, title, args.text))]

    # Merge with any previous run so repeated invocations accumulate voices
    # instead of clobbering them.
    manifest_path = os.path.join(SAMPLES_DIR, "manifest.json")
    old = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path) as f:
                old = json.load(f).get("samples", [])
        except (json.JSONDecodeError, OSError):
            pass
    merged = {e["file"]: e for e in old}
    merged.update({e["file"]: e for e in entries})

    with open(manifest_path, "w") as f:
        json.dump({"line": args.text, "model": core.FISH_MODEL,
                   "samples": sorted(merged.values(), key=lambda e: e["file"])},
                  f, indent=2)

    print(f"\n{len(entries)} new / {len(merged)} total -> samples/manifest.json")


if __name__ == "__main__":
    main()
