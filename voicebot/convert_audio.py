#!/usr/bin/env python3
"""
Transcode existing sample WAVs into a format messaging apps actually accept.

WhatsApp (and Slack, iMessage, Teams) will not send 44.1 kHz PCM WAV as playable
audio -- it either refuses the file or attaches it as an inert document. MP3 is
the safe universal choice; m4a/opus are here for completeness.

Transcodes in place from the files already on disk -- no new TTS calls, so the
audio is bit-for-bit the same performance you already reviewed, just repackaged.
Uses PyAV's bundled FFmpeg libraries (there is no ffmpeg binary on this box).

    python voicebot/convert_audio.py                        # accents -> mp3
    python voicebot/convert_audio.py --dir samples/qa
    python voicebot/convert_audio.py --to m4a --bitrate 128k
    python voicebot/convert_audio.py --all                  # every suite

Writes alongside the source, e.g. samples/accents/british.mp3.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import av

HERE = os.path.dirname(os.path.abspath(__file__))

# container -> (codec, default bitrate). WhatsApp handles all three; mp3 is the
# most universally previewable, which is why it's the default.
TARGETS = {
    "mp3": ("libmp3lame", "192k"),
    "m4a": ("aac", "160k"),
    "opus": ("libopus", "96k"),
}


def convert(src: str, dst: str, codec: str, bitrate: str) -> tuple[float, int]:
    """Decode src, re-encode to dst. Returns (duration_seconds, out_bytes)."""
    with av.open(src) as inp:
        in_stream = inp.streams.audio[0]
        with av.open(dst, mode="w") as out:
            # Preserve the source channel count. Left to its default,
            # libmp3lame emits stereo, which upmixes these mono clips into two
            # identical channels and doubles the file for no gain.
            #
            # Derive the layout from the channel count rather than reusing
            # in_stream.layout.name: a WAV written without a channel mask (which
            # is what Python's wave module produces) reports as "1 channels",
            # and passing that string back to the encoder fails with EINVAL.
            layout = {1: "mono", 2: "stereo"}.get(in_stream.channels, "stereo")
            out_stream = out.add_stream(codec, rate=in_stream.rate, layout=layout)
            out_stream.bit_rate = int(float(bitrate.rstrip("k")) * 1000)

            resampler = av.AudioResampler(
                format=out_stream.format.name,
                layout=out_stream.layout.name,
                rate=out_stream.rate,
            )
            for frame in inp.decode(in_stream):
                frame.pts = None
                for rframe in resampler.resample(frame):
                    out.mux(out_stream.encode(rframe))
            # Flush the resampler, then the encoder -- skipping either truncates
            # the tail of the clip.
            for rframe in resampler.resample(None):
                out.mux(out_stream.encode(rframe))
            out.mux(out_stream.encode(None))

    with av.open(dst) as chk:
        dur = float(chk.duration or 0) / av.time_base
    return dur, os.path.getsize(dst)


def wav_seconds(path: str) -> float:
    import wave
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcode sample WAVs for sharing")
    ap.add_argument("--dir", default="samples/accents",
                    help="directory of .wav files, relative to voicebot/")
    ap.add_argument("--all", action="store_true",
                    help="convert samples/accents and samples/qa")
    ap.add_argument("--to", choices=tuple(TARGETS), default="mp3")
    ap.add_argument("--bitrate", help="e.g. 192k (default depends on format)")
    ap.add_argument("--keep-wav", action="store_true",
                    help="default already keeps the wavs; kept for clarity")
    args = ap.parse_args()

    codec, default_br = TARGETS[args.to]
    bitrate = args.bitrate or default_br

    dirs = ["samples/accents", "samples/qa"] if args.all else [args.dir]
    total_in = total_out = 0
    n = 0

    for d in dirs:
        abs_dir = os.path.join(HERE, d)
        wavs = sorted(glob.glob(os.path.join(abs_dir, "*.wav")))
        if not wavs:
            print(f"-- {d}: no .wav files, skipping")
            continue
        print(f"\n=== {d} -> .{args.to} ({codec} @ {bitrate}) ===")
        for src in wavs:
            dst = os.path.splitext(src)[0] + "." + args.to
            src_secs = wav_seconds(src)
            try:
                dur, size = convert(src, dst, codec, bitrate)
            except Exception as e:
                print(f"  !! {os.path.basename(src)}: {type(e).__name__}: {e}")
                continue
            in_kb = os.path.getsize(src) // 1024
            out_kb = size // 1024
            drift = abs(dur - src_secs)
            # A few ms of encoder padding is normal; a big gap means the tail
            # was truncated (usually a missed flush).
            warn = "  <-- LENGTH MISMATCH" if drift > 0.15 else ""
            print(f"  {os.path.basename(src):<22} {src_secs:5.2f}s "
                  f"{in_kb:>5} KB  ->  {os.path.basename(dst):<22} "
                  f"{dur:5.2f}s {out_kb:>4} KB "
                  f"({out_kb / max(in_kb, 1):.0%} of original){warn}")
            total_in += in_kb
            total_out += out_kb
            n += 1

    if n:
        print(f"\n{n} files: {total_in} KB wav -> {total_out} KB {args.to} "
              f"({total_out / max(total_in, 1):.0%}). Originals left in place.")
    else:
        print("\nnothing converted")


if __name__ == "__main__":
    main()
