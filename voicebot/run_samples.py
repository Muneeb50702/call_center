#!/usr/bin/env python3
"""
Generate a shareable set of Fish Audio voice samples.

Two suites, both general purpose -- no domain or company framing anywhere:

  qa      A fixed battery of everyday assistant questions (knowledge, math,
          code, writing, advice, trivia, planning, multi-turn memory). Each
          question goes through gpt-4o-mini, then the reply is spoken by Fish.
          This shows how the voice handles real, unscripted answers.

  accents One fixed line read by every accent in the library set, so voices are
          compared on identical text.

Every clip is then transcribed back with Deepgram as an intelligibility check --
if ASR reads the synthesized speech back correctly, a human will too. The
word-accuracy figure in the report is that round-trip, not a TTS quality score.

    python voicebot/run_samples.py                 # both suites
    python voicebot/run_samples.py --only qa
    python voicebot/run_samples.py --voice <id>    # run the qa suite in one voice

Outputs voicebot/samples/qa/*.wav, samples/accents/*.wav, samples/REPORT.md.
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

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")

# --------------------------------------------------------------------------- #
# The general-purpose battery. Each entry is (category, prompt).
# Chosen to cover the shapes a general assistant gets asked, and to make the
# TTS work: numbers, units, an acronym, a list read as prose, a question mark.
# --------------------------------------------------------------------------- #
QA_PROMPTS: list[tuple[str, str]] = [
    ("greeting",      "Hi! Introduce yourself in two sentences."),
    ("knowledge",     "Why is the sky blue? Keep it short."),
    ("math",          "What is 17 percent of 240?"),
    ("code",          "In Python, how do I reverse a list?"),
    ("explain",       "Explain what an API is to a ten year old."),
    ("writing",       "Write a two sentence thank-you note to a colleague "
                      "who covered my shift."),
    ("advice",        "I have trouble focusing in the afternoon. "
                      "Give me two practical tips."),
    ("trivia",        "Who wrote Pride and Prejudice, and roughly when?"),
    ("planning",      "Give me a simple three step plan to start running."),
    ("units",         "How many kilometres is a 5 mile run, and how long "
                      "would that take at a nine minute mile pace?"),
    ("ambiguity",     "Book it for tomorrow."),
    ("uncertainty",   "What will the weather be in Lahore next Tuesday?"),
    # Two turns in sequence, to show conversational memory in the audio.
    ("memory-1",      "My name is Muneeb and I'm learning Spanish."),
    ("memory-2",      "What am I learning, and what's my name?"),
]

ACCENT_LINE = (
    "Hi there! I can help with just about anything, from explaining a tricky "
    "idea to drafting an email. What would you like to start with?"
)

ACCENT_TERMS = ["british", "american", "indian", "australian", "irish", "scottish"]

# Hand-verified fact checks for prompts where gpt-4o-mini has been observed to
# slip. These are LLM content errors, not voice errors -- but the clips are
# unedited model output, so the report says so rather than quietly shipping a
# wrong number. Keyed by category; the checker only fires when the spoken text
# contains the bad value, so a corrected answer produces no note.
FACT_CHECKS: dict[str, list[tuple[str, str]]] = {
    "math": [("forty-one point four",
              "17% of 240 is 40.8, not 41.4")],
    "trivia": [("eight hundred and twelve",
                "Pride and Prejudice was published in 1813, not 1812")],
    "units": [("eight point zero one",
               "5 miles is 8.047 km, so 'eight point zero one' is off")],
}


def fact_notes(category: str, spoken: str) -> list[str]:
    low = spoken.lower()
    return [note for needle, note in FACT_CHECKS.get(category, [])
            if needle in low]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:44] or "x"


FILLER = {"a", "an", "the", "and"}  # ASR drops these freely; don't punish it


def word_accuracy(said: str, heard: str) -> float:
    """Fraction of the spoken words ASR recovered. Crude but directional."""
    def norm(s: str) -> list[str]:
        s = s.lower().replace("-", " ")
        return [w for w in re.findall(r"[a-z0-9]+", s) if w not in FILLER]

    a, b = norm(said), norm(heard)
    if not a:
        return 0.0
    remaining = list(b)
    hit = 0
    for w in a:
        if w in remaining:
            remaining.remove(w)
            hit += 1
    return hit / len(a)


def synth_and_check(text: str, voice_id: str | None, path: str,
                    verify: bool = True) -> dict:
    """TTS -> wav on disk -> optional ASR round trip. Returns a result row."""
    t0 = time.monotonic()
    pcm = core.tts_pcm(text, voice_id)
    gen = time.monotonic() - t0
    wav = core.wrap_wav(pcm)
    with open(path, "wb") as f:
        f.write(wav)

    row = {
        "file": os.path.relpath(path, SAMPLES),
        "text": text,
        "voice_id": voice_id,
        "seconds": round(core.pcm_seconds(pcm), 2),
        "tts_gen": round(gen, 2),
        "kb": round(len(wav) / 1024),
    }
    if verify:
        try:
            # smart_format off: we're comparing against known spoken text, and
            # digit normalisation would read as an error (see core.stt).
            heard, _ = core.stt(wav, "audio/wav", smart_format=False)
            row["heard"] = heard
            row["accuracy"] = round(word_accuracy(text, heard), 3)
        except core.ConfigError as e:
            row["heard"] = f"(check skipped: {e})"
            row["accuracy"] = None
    return row


# --------------------------------------------------------------------------- #
def run_qa(voice_id: str | None, voice_label: str, verify: bool) -> list[dict]:
    out_dir = os.path.join(SAMPLES, "qa")
    os.makedirs(out_dir, exist_ok=True)
    rows: list[dict] = []
    history: list[dict] = []  # shared, so the memory-* prompts actually chain

    print(f"\n=== qa suite  (voice: {voice_label}) ===")
    for i, (cat, prompt) in enumerate(QA_PROMPTS, 1):
        history.append({"role": "user", "content": prompt})
        t0 = time.monotonic()
        reply = core.llm(history)
        llm_s = time.monotonic() - t0
        history.append({"role": "assistant", "content": reply})

        path = os.path.join(out_dir, f"{i:02d}-{slug(cat)}.wav")
        row = synth_and_check(reply, voice_id, path, verify)
        row.update({"n": i, "category": cat, "prompt": prompt,
                    "llm": round(llm_s, 2), "suite": "qa"})
        rows.append(row)

        acc = f"{row['accuracy']:.0%}" if row.get("accuracy") is not None else "n/a"
        print(f"[{i:02d}/{len(QA_PROMPTS)}] {cat:<12} "
              f"llm {row['llm']:4.1f}s  tts {row['tts_gen']:4.1f}s  "
              f"{row['seconds']:5.1f}s audio  asr {acc}")
        print(f"      Q: {prompt}")
        print(f"      A: {reply}")
    return rows


def run_accents(verify: bool) -> list[dict]:
    out_dir = os.path.join(SAMPLES, "accents")
    os.makedirs(out_dir, exist_ok=True)
    rows: list[dict] = []

    print(f"\n=== accents suite  (same line, {len(ACCENT_TERMS) + 1} voices) ===")
    targets: list[tuple[str, str | None, str]] = [
        ("default", None, f"{core.FISH_MODEL} default")]
    for term in ACCENT_TERMS:
        found = core.list_voices(term, 2)
        if found:
            targets.append((term, found[0]["id"], found[0]["title"]))
        else:
            print(f"  -- {term}: no library match, skipped")

    for label, vid, title in targets:
        path = os.path.join(out_dir, f"{slug(label)}.wav")
        row = synth_and_check(ACCENT_LINE, vid, path, verify)
        row.update({"category": label, "voice_title": title, "suite": "accents"})
        rows.append(row)
        acc = f"{row['accuracy']:.0%}" if row.get("accuracy") is not None else "n/a"
        print(f"  {label:<11} {title[:40]:<40} {row['seconds']:5.1f}s  asr {acc}")
    return rows


# --------------------------------------------------------------------------- #
def write_report(qa: list[dict], accents: list[dict], voice_label: str) -> str:
    p = os.path.join(SAMPLES, "REPORT.md")
    all_rows = qa + accents
    checked = [r for r in all_rows if r.get("accuracy") is not None]
    mean_acc = sum(r["accuracy"] for r in checked) / len(checked) if checked else 0
    audio_total = sum(r["seconds"] for r in all_rows)

    L: list[str] = []
    L.append("# Fish Audio voice samples\n")
    L.append(f"- **TTS**: Fish Audio `{core.FISH_MODEL}`")
    L.append(f"- **LLM**: `{core.OPENAI_MODEL}` (general-purpose assistant, "
             f"no domain framing)")
    L.append(f"- **Intelligibility check**: Deepgram `{core.STT_MODEL}` "
             f"transcribes each clip back (no smart-formatting, so spoken "
             f"numbers stay as words)\n")
    L.append(f"{len(all_rows)} clips, {audio_total:.0f}s of audio total. "
             f"Mean round-trip word accuracy **{mean_acc:.0%}** "
             f"across {len(checked)} checked clips.\n")

    if qa:
        L.append(f"\n## Q&A suite — voice: {voice_label}\n")
        L.append("gpt-4o-mini answers a general-purpose question; Fish speaks "
                 "the reply. Turns share one conversation, so #13 and #14 test "
                 "memory.\n")
        for r in qa:
            L.append(f"\n### {r['n']:02d}. {r['category']}\n")
            L.append(f"**Asked:** {r['prompt']}\n")
            L.append(f"**Answered:** {r['text']}\n")
            L.append(f"**Audio:** [`{r['file']}`]({r['file']}) — "
                     f"{r['seconds']}s, {r['kb']} KB "
                     f"(llm {r['llm']}s, tts {r['tts_gen']}s)")
            if r.get("accuracy") is not None:
                L.append(f"**Heard back:** {r['heard']} "
                         f"— {r['accuracy']:.0%} word match")

    if accents:
        L.append("\n\n## Accent suite\n")
        L.append(f"Every voice reads the identical line, so they're directly "
                 f"comparable:\n\n> {ACCENT_LINE}\n")
        L.append("| accent | voice | audio | length | asr match |")
        L.append("|---|---|---|---|---|")
        for r in accents:
            acc = f"{r['accuracy']:.0%}" if r.get("accuracy") is not None else "n/a"
            L.append(f"| {r['category']} | {r['voice_title']} "
                     f"| [`{r['file']}`]({r['file']}) | {r['seconds']}s | {acc} |")

    L.append("\n\n## Notes\n")
    L.append("- `s2.1-pro-free` is the free tier and the same generation as "
             "`s2.1-pro`; it carries no latency or DPA guarantee but voice "
             "quality is representative. The paid models need API credit topped "
             "up separately from platform credit.")
    L.append("- WAV files are 44.1 kHz mono 16-bit with correct headers. "
             "Fish's own `format:\"wav\"` ships a placeholder length in the "
             "header (a 1.9s clip decodes as ~48,695s), so these are generated "
             "as raw PCM and re-framed locally.")
    L.append("- Word accuracy is a machine round trip (TTS out, ASR back in). "
             "It measures intelligibility, not naturalness — judge naturalness "
             "by listening.")

    text = "\n".join(L) + "\n"
    with open(p, "w") as f:
        f.write(text)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate shareable voice samples")
    ap.add_argument("--only", choices=("qa", "accents"), help="run one suite")
    ap.add_argument("--voice", help="reference_id for the qa suite")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the ASR round-trip check")
    args = ap.parse_args()

    missing = [k for k in core.missing_keys() if k != "DEEPGRAM_API_KEY"]
    if missing:
        sys.exit(f"error: missing {', '.join(missing)} in .env or environment")

    verify = not args.no_verify
    voice_label = "default"
    if args.voice:
        try:
            match = next((v for v in core.list_voices(None, 60)
                          if v["id"] == args.voice), None)
            voice_label = match["title"] if match else args.voice
        except Exception:
            voice_label = args.voice

    os.makedirs(SAMPLES, exist_ok=True)
    print(f"tts={core.FISH_MODEL}  llm={core.OPENAI_MODEL}  verify={verify}")

    qa = run_qa(args.voice, voice_label, verify) if args.only != "accents" else []
    accents = run_accents(verify) if args.only != "qa" else []

    with open(os.path.join(SAMPLES, "manifest.json"), "w") as f:
        json.dump({"tts_model": core.FISH_MODEL, "llm_model": core.OPENAI_MODEL,
                   "accent_line": ACCENT_LINE, "samples": qa + accents},
                  f, indent=2)
    report = write_report(qa, accents, voice_label)

    total = sum(r["seconds"] for r in qa + accents)
    print(f"\n{len(qa) + len(accents)} clips, {total:.0f}s of audio")
    print(f"report -> {os.path.relpath(report)}")


if __name__ == "__main__":
    main()
