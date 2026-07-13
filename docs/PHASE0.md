# Phase 0 — Real, Auditable Inbound + Anti-Hallucination + Telephony Primitives

Phase 0 makes the existing inbound system actually work end-to-end on **livekit-agents 1.6.5**,
adds the no-hallucination subsystem, and lays the telephony/outbound + call-persistence groundwork.
See the full roadmap in the plan file (`~/.claude/plans/hi-read-my-entire-synchronous-sparrow.md`).

## What changed

**Fixed pre-1.0 LiveKit API drift (these silently no-op'd or crashed on 1.x):**
- `pipeline/hooks.py` — rewritten to real 1.x events (`user_input_transcribed`,
  `conversation_item_added`, `metrics_collected`, `function_tools_executed`,
  `agent_state_changed`). Live transcripts, latency, and tool-fact capture now work.
- `state/agents.py` — **all 23 `await ctx.session.update_agent(...)` → `ctx.session.update_agent(...)`**
  (`update_agent` is sync in 1.x; every transition previously crashed on `await None`).
- `tools/human_intervention.py` — whisper via `session.generate_reply(instructions=...)`.
- `tools/call_control.py` — real SIP REFER (`lkapi.sip.transfer_sip_participant`) + real hangup
  (`get_job_context().delete_room()`).
- `state/machine.py` — `on_transition` callback replaces the broken monkeypatch.

**Anti-hallucination subsystem:**
- `pipeline/verifier.py` — redacts any ungrounded rate/$/MC/DOT/load/booking number before TTS,
  grounded against tool outputs + the caller's own words. 10 unit tests (`tests/test_verifier.py`).
- `state/agents.py` `NexusAgent` base — `tts_node` runs the verifier per sentence; `stt_node`
  flags low ASR confidence; `on_user_turn_completed` resets per-turn facts. Collapses the 11
  duplicate `transfer_to_human` tools into one that does a real transfer.
- `llm/prompts.py` — grounding + mandatory alphanumeric read-back rules.

**Latency / quality:** LiveKit turn detector (`EnglishModel`) + endpointing; Gemini 2.5 Flash with a
Groq/Llama `FallbackAdapter`; Deepgram Aura-2 TTS.

**Backend + persistence:**
- `auth.py` — WS `decode_token`, role tiers (`require_super_admin`), and a **service-key** path so the
  agent authenticates to the backend (`X-Service-Key`/`X-Tenant-Id`).
- `database.py` + Alembic — `calls` gains `transcript/sentiment/direction/exception_peak`.
- `agent.py` — wires the live-call registry (Redis, feeds the dashboard snapshot), `CallAnalytics`,
  POST/PATCH `/calls` via `CallReporter`, optional egress, and a real `add_shutdown_callback`.
- Dashboard `live/page.tsx` — token key fixed (`access_token`).

**Config:** `NEXUS_SERVICE_KEY` in settings/compose/`.env.example`; `RECORDING_ENABLED`,
`LIVEKIT_SIP_OUTBOUND_TRUNK_ID`.

## Verify locally (needs real keys)

1. Fill `.env` from `.env.example` (LiveKit, Deepgram, Gemini, Groq, `NEXUS_SERVICE_KEY`, `JWT_SECRET`).
2. `docker compose up --build` (postgres, redis, tms-backend, nexus-agent, dashboard).
3. Provision a tenant + SIP number (Telnyx → LiveKit inbound trunk; `scripts/setup_sip.sh`).
4. Place a test call to the tenant number and check:
   - Dashboard **/live** streams the transcript in real time; a whisper reaches the agent.
   - The agent books/looks up loads (grounded numbers only; invented numbers are redacted to a hedge).
   - `transfer_to_human` performs a real SIP REFER; `end_call` disconnects.
   - A row lands in `calls` (Postgres) with transcript + latency; **/analytics** KPIs are non-zero.
5. Outbound smoke test: set `LIVEKIT_SIP_OUTBOUND_TRUNK_ID`, then call
   `nexus_agent/telephony/outbound.place_outbound_call(...)` (or backend
   `services/livekit_control.place_outbound_call(...)`) to a **consented** number.

## Unit tests (no keys needed)
- `cd nexus_agent && python3 tests/test_verifier.py` → 10/10.
- Full suites (`nexus_agent/tests`, `tms_backend/tests`) run in CI (need the container deps).

## Known Phase 0 limitations (addressed later)
- Egress recording needs egress infra (self-hosted egress volume or S3) — off by default.
- Warm transfer uses a fixed announce grace delay; Phase 1 adds session-driven sequencing.
- Outbound is a primitive only; **no cold dialing** until Phase 1 compliance (consent/DNC/hours).
