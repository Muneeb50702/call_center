# Fish Audio voice samples

- **TTS**: Fish Audio `s2.1-pro-free`
- **LLM**: `gpt-4o-mini` (general-purpose assistant, no domain framing)
- **Intelligibility check**: Deepgram `nova-2` transcribes each clip back (no smart-formatting, so spoken numbers stay as words)

21 clips, 177s of audio total. Mean round-trip word accuracy **100%** across 21 checked clips.


## Q&A suite — voice: default

gpt-4o-mini answers a general-purpose question; Fish speaks the reply. Turns share one conversation, so #13 and #14 test memory.


### 01. greeting

**Asked:** Hi! Introduce yourself in two sentences.

**Answered:** I am a voice assistant designed to help you with a variety of questions and tasks. My goal is to provide clear and concise information to assist you.

**Audio:** [`qa/01-greeting.wav`](qa/01-greeting.wav) — 8.82s, 760 KB (llm 1.31s, tts 3.26s)
**Heard back:** i am a voice assistant designed to help you with a variety of questions and tasks my goal is to provide clear and concise information to assist you — 100% word match

### 02. knowledge

**Asked:** Why is the sky blue? Keep it short.

**Answered:** The sky appears blue because of a phenomenon called Rayleigh scattering, where shorter blue wavelengths of sunlight are scattered in all directions by the gases in the atmosphere.

**Audio:** [`qa/02-knowledge.wav`](qa/02-knowledge.wav) — 10.68s, 920 KB (llm 1.15s, tts 4.39s)
**Heard back:** the sky appears blue because of a phenomenon called rayleigh scattering where shorter blue wavelengths of sunlight are scattered in all directions by the gases in the atmosphere — 100% word match

### 03. math

**Asked:** What is 17 percent of 240?

**Answered:** Seventeen percent of two hundred forty is forty-one point four.

**Audio:** [`qa/03-math.wav`](qa/03-math.wav) — 4.6s, 396 KB (llm 1.07s, tts 2.98s)
**Heard back:** seventeen percent of two hundred forty is forty one point four — 100% word match

### 04. code

**Asked:** In Python, how do I reverse a list?

**Answered:** You can reverse a list in Python by using the reverse method on the list or by slicing it with a step of negative one. Would you like more details on how to do that?

**Audio:** [`qa/04-code.wav`](qa/04-code.wav) — 8.82s, 760 KB (llm 1.36s, tts 3.74s)
**Heard back:** you can reverse a list in python by using the reverse method on the list or by slicing it with a step of negative one would you like more details on how to do that — 100% word match

### 05. explain

**Asked:** Explain what an API is to a ten year old.

**Answered:** An API is like a waiter at a restaurant. You tell the waiter what you want, and they go to the kitchen to get it for you, bringing back your food. In the same way, an API lets different computer programs talk to each other and ask for information or services.

**Audio:** [`qa/05-explain.wav`](qa/05-explain.wav) — 18.39s, 1584 KB (llm 1.58s, tts 7.16s)
**Heard back:** an api is like a waiter at a restaurant you tell the waiter what you want and they go to the kitchen to get it for you bringing back your food in the same way an api lets different computer programs talk to each other and ask for information or services — 100% word match

### 06. writing

**Asked:** Write a two sentence thank-you note to a colleague who covered my shift.

**Answered:** Thank you so much for covering my shift; I really appreciate your help. Your support made a big difference for me!

**Audio:** [`qa/06-writing.wav`](qa/06-writing.wav) — 6.64s, 572 KB (llm 1.12s, tts 2.92s)
**Heard back:** thank you so much for covering my shift i really appreciate your help your support made a big difference for me — 100% word match

### 07. advice

**Asked:** I have trouble focusing in the afternoon. Give me two practical tips.

**Answered:** Try taking short breaks every hour to refresh your mind, and consider having a healthy snack to boost your energy. Staying hydrated can also help improve your focus.

**Audio:** [`qa/07-advice.wav`](qa/07-advice.wav) — 10.08s, 868 KB (llm 1.73s, tts 4.06s)
**Heard back:** try taking short breaks every hour to refresh your mind and consider having a healthy snack to boost your energy staying hydrated can also help improve your focus — 100% word match

### 08. trivia

**Asked:** Who wrote Pride and Prejudice, and roughly when?

**Answered:** "Pride and Prejudice" was written by Jane Austen and published in the year one thousand eight hundred and twelve.

**Audio:** [`qa/08-trivia.wav`](qa/08-trivia.wav) — 6.69s, 576 KB (llm 1.15s, tts 2.91s)
**Heard back:** pride and prejudice was written by jane austen and published in the year one thousand eight hundred and twelve — 100% word match

### 09. planning

**Asked:** Give me a simple three step plan to start running.

**Answered:** Start by setting a goal, like running for ten minutes three times a week. Next, find a comfortable pair of running shoes. Finally, begin with a combination of walking and jogging to gradually build your stamina.

**Audio:** [`qa/09-planning.wav`](qa/09-planning.wav) — 12.86s, 1108 KB (llm 1.42s, tts 5.43s)
**Heard back:** start by setting a goal like running for ten minutes three times a week next find a comfortable pair of running shoes finally begin with a combination of walking and jogging to gradually build your stamina — 100% word match

### 10. units

**Asked:** How many kilometres is a 5 mile run, and how long would that take at a nine minute mile pace?

**Answered:** A five mile run is approximately eight point zero one kilometers. At a nine minute mile pace, it would take about forty-five minutes to complete the run.

**Audio:** [`qa/10-units.wav`](qa/10-units.wav) — 10.08s, 868 KB (llm 1.45s, tts 4.37s)
**Heard back:** a five mile run is approximately eight point zero one kilometers at a nine minute mile pace it would take about forty five minutes to complete the run — 100% word match

### 11. ambiguity

**Asked:** Book it for tomorrow.

**Answered:** I can't make bookings for you, but you can easily schedule it on your calendar or set a reminder on your phone. Would you like tips on how to do that?

**Audio:** [`qa/11-ambiguity.wav`](qa/11-ambiguity.wav) — 8.5s, 732 KB (llm 1.93s, tts 3.37s)
**Heard back:** i can't make bookings for you but you can easily schedule it on your calendar or set a reminder on your phone would you like tips on how to do that — 100% word match

### 12. uncertainty

**Asked:** What will the weather be in Lahore next Tuesday?

**Answered:** I'm sorry, but I can't provide real-time weather updates. You can check a weather website or app for the most accurate forecast.

**Audio:** [`qa/12-uncertainty.wav`](qa/12-uncertainty.wav) — 7.76s, 668 KB (llm 1.19s, tts 3.51s)
**Heard back:** i'm sorry but i can't provide real time weather updates you can check a weather website or app for the most accurate forecast — 100% word match

### 13. memory-1

**Asked:** My name is Muneeb and I'm learning Spanish.

**Answered:** That's great, Muneeb! How can I assist you with your Spanish learning?

**Audio:** [`qa/13-memory-1.wav`](qa/13-memory-1.wav) — 4.64s, 400 KB (llm 1.22s, tts 2.09s)
**Heard back:** that's great muneeb how can i assist you with your spanish learning — 100% word match

### 14. memory-2

**Asked:** What am I learning, and what's my name?

**Answered:** You are learning Spanish, and your name is Muneeb.

**Audio:** [`qa/14-memory-2.wav`](qa/14-memory-2.wav) — 3.44s, 296 KB (llm 1.05s, tts 1.61s)
**Heard back:** you are learning spanish and your name is muneeb — 100% word match


## Accent suite

Every voice reads the identical line, so they're directly comparable:

> Hi there! I can help with just about anything, from explaining a tricky idea to drafting an email. What would you like to start with?

| accent | voice | audio | length | asr match |
|---|---|---|---|---|
| default | s2.1-pro-free default | [`accents/default.wav`](accents/default.wav) | 8.64s | 100% |
| british | Brian British | [`accents/british.wav`](accents/british.wav) | 8.36s | 100% |
| american | Alex American Young male  | [`accents/american.wav`](accents/american.wav) | 6.69s | 100% |
| indian | Funny Indian accent | [`accents/indian.wav`](accents/indian.wav) | 7.76s | 100% |
| australian | Australian female | [`accents/australian.wav`](accents/australian.wav) | 7.94s | 100% |
| irish | Irish Redux | [`accents/irish.wav`](accents/irish.wav) | 8.27s | 100% |
| scottish | Scottish Sans | [`accents/scottish.wav`](accents/scottish.wav) | 7.62s | 100% |


## Notes

- `s2.1-pro-free` is the free tier and the same generation as `s2.1-pro`; it carries no latency or DPA guarantee but voice quality is representative. The paid models need API credit topped up separately from platform credit.
- WAV files are 44.1 kHz mono 16-bit with correct headers. Fish's own `format:"wav"` ships a placeholder length in the header (a 1.9s clip decodes as ~48,695s), so these are generated as raw PCM and re-framed locally.
- Word accuracy is a machine round trip (TTS out, ASR back in). It measures intelligibility, not naturalness — judge naturalness by listening.
