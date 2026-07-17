"""
Nexus — Silero VAD

Voice activity detection, tuned for turn-taking latency.

The previous settings claimed to be "tuned aggressively for fast barge-in" but
did the opposite on all three axes:

    min_speech_duration  = 0.4   # 400ms of speech before a barge-in registers
    min_silence_duration = 0.8   # 800ms of dead air before end-of-turn
    activation_threshold = 0.8   # only confident, loud speech counts as speech

Those stack: with min_endpointing_delay on top, a caller waited roughly 1.2s
after finishing a sentence before the agent even began to think. That is the
single largest controllable delay in the pipeline, and it is pure dead air.

What each knob actually costs:

- `min_silence_duration` is charged in full to every single turn. It is not a
  detection window, it is a mandatory wait. With a semantic turn detector
  downstream, VAD does not need to be certain the caller has finished — it only
  needs to hand off quickly and let the turn detector decide, since the detector
  reads the transcript and can wait longer when the sentence is obviously
  unfinished. So VAD should be trigger-happy and the detector should be the
  patient one. 0.25s.

- `activation_threshold` at 0.8 ignores anything but clear, loud speech — a
  quiet "wait—" or "no, actually" fails to register, so barge-in feels dead and
  callers talk over an agent that will not stop. 0.5 is Silero's default and is
  calibrated for exactly this.

- `min_speech_duration` at 0.4 discards every utterance shorter than 400ms.
  "Yes", "no", "yep", "stop" are all shorter than that. On a sales call, "no" is
  the most important word a prospect can say. 0.05.

Because barge-in is now genuinely sensitive, false interruptions are handled at
the session layer (`false_interruption_timeout` / `resume_false_interruption` in
agent.py) rather than by making the VAD deaf.
"""

from livekit.plugins import silero

# Speech must persist this long to count. Low enough to catch one-syllable words
# ("no", "stop", "yes") which are the ones that most need to land.
MIN_SPEECH_DURATION = 0.05

# Silence before VAD calls end-of-speech. Paid on every turn, so it is the first
# thing to cut. The semantic turn detector is what actually decides whether the
# caller is done; this only decides how fast VAD asks it.
MIN_SILENCE_DURATION = 0.25

# Audio retained from before the speech trigger, so STT is not fed a clipped
# first phoneme. Below ~0.2 the opening consonant starts getting eaten.
PREFIX_PADDING_DURATION = 0.3

# Silero's calibrated default. Higher misses quiet or hesitant speech.
ACTIVATION_THRESHOLD = 0.5


def create_vad() -> silero.VAD:
    """Silero VAD tuned to hand off to the semantic turn detector quickly.

    Runs on CPU. Load it once per worker process via a prewarm hook — loading it
    per call costs ~200ms of the caller's first turn.
    """
    return silero.VAD.load(
        min_speech_duration=MIN_SPEECH_DURATION,
        min_silence_duration=MIN_SILENCE_DURATION,
        prefix_padding_duration=PREFIX_PADDING_DURATION,
        activation_threshold=ACTIVATION_THRESHOLD,
    )
