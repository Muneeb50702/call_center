'use client';

/**
 * useVoiceSession — owns the LiveKit room, the microphone, and the telemetry stream.
 *
 * Keeping every side effect in one hook means the page component is pure
 * rendering, and there is exactly one place that can leak a room connection or a
 * mic permission.
 *
 * Two things worth knowing:
 *
 * - Mic permission is requested BEFORE the room is created. If we connected
 *   first, a user who denies the mic would sit in a live room paying for an agent
 *   that can never hear them.
 *
 * - Local audio level is sampled from a WebAudio analyser rather than taken from
 *   the agent. It drives the "you're being heard" meter, and it has to reflect
 *   the browser's own mic to be honest — a meter fed from the server would still
 *   wiggle if the mic were muted.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ConnectionState,
  RemoteAudioTrack,
  Room,
  RoomEvent,
  Track,
} from 'livekit-client';

import {
  AgentState,
  CONTROL_TOPIC,
  DemoSession,
  KbSource,
  TELEMETRY_TOPIC,
  TelemetryEvent,
  TranscriptLine,
  TurnLatency,
  VoiceProfile,
} from './types';

// Same-origin, on purpose. Proxied to the backend by the /api/:path* rewrite in
// next.config.mjs.
//
// This must NOT use NEXT_PUBLIC_API_URL. That value is inlined into the browser
// bundle at build time as http://localhost:8001, which only works on the machine
// running Docker — on a phone "localhost" is the phone, and over an ngrok HTTPS
// tunnel an http:// call is blocked as mixed content anyway. A relative path
// inherits whatever scheme and host actually served the page, so one build works
// on localhost, through ngrok, and behind a real domain.
const API_URL = '/api';

// Keep the transcript bounded — a long demo should not grow the DOM without limit.
const MAX_TRANSCRIPT_LINES = 60;
const MAX_TURNS_CHARTED = 20;

export type Status = 'idle' | 'requesting-mic' | 'connecting' | 'live' | 'ended' | 'error';

export interface SessionInfo {
  callId: string;
  companyName: string;
  agentName: string;
  kbChunks: number;
  kbDocs: number;
  kbLoaded: boolean;
  pipeline: Record<string, string | boolean>;
}

export function useVoiceSession() {
  const roomRef = useRef<Room | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);

  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string>('');
  const [session, setSession] = useState<SessionInfo | null>(null);

  const [agentState, setAgentState] = useState<AgentState>('initializing');
  const [convoState, setConvoState] = useState<string>('');
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [turns, setTurns] = useState<TurnLatency[]>([]);
  const [sources, setSources] = useState<KbSource[]>([]);
  const [kbStats, setKbStats] = useState({ queries: 0, misses: 0, lastLatencyMs: 0 });
  const [interventions, setInterventions] = useState(0);
  const [toolCalls, setToolCalls] = useState<string[]>([]);

  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [voice, setVoice] = useState<VoiceProfile | null>(null);
  const [switching, setSwitching] = useState(false);

  const [micLevel, setMicLevel] = useState(0);
  const [micEnabled, setMicEnabled] = useState(true);

  // ── Telemetry ──

  const handleEvent = useCallback((event: TelemetryEvent) => {
    switch (event.type) {
      case 'session_ready':
        setSession({
          callId: event.call_id,
          companyName: event.company_name,
          agentName: event.agent_name,
          kbChunks: event.kb?.chunks ?? 0,
          kbDocs: event.kb?.docs ?? 0,
          kbLoaded: event.kb?.loaded ?? false,
          pipeline: event.pipeline ?? {},
        });
        setVoices(event.voices ?? []);
        setVoice(event.voice ?? null);
        setConvoState(event.state);
        break;

      case 'turn_latency':
        setTurns((prev) => [...prev, event as TurnLatency].slice(-MAX_TURNS_CHARTED));
        break;

      case 'transcript': {
        const { speaker, text, is_final } = event;
        if (!text?.trim()) break;
        setTranscript((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          // Interim results stream in as successive partials of the same
          // utterance — replace the open line rather than appending a new one
          // per keystroke, or the transcript becomes unreadable noise.
          if (last && last.speaker === speaker && !last.final) {
            next[next.length - 1] = { speaker, text, final: is_final !== false, at: last.at };
          } else {
            next.push({ speaker, text, final: is_final !== false, at: Date.now() });
          }
          return next.slice(-MAX_TRANSCRIPT_LINES);
        });
        break;
      }

      case 'agent_state':
        if (event.state) setAgentState(event.state);
        break;

      case 'state_changed':
        setConvoState(event.new_state);
        break;

      case 'tool':
        setToolCalls((prev) => [...prev, event.name].slice(-12));
        break;

      case 'kb_retrieval':
        setSources(event.sources ?? []);
        setKbStats({
          queries: event.queries ?? 0,
          misses: event.misses ?? 0,
          lastLatencyMs: event.latency_ms ?? 0,
        });
        break;

      case 'verifier_intervention':
        setInterventions(event.total ?? 0);
        break;

      case 'voice_changed':
        setVoice(event.voice);
        setSwitching(false);
        break;

      case 'error':
      case 'alert':
        // Non-fatal: surface it but never tear down a live call over it.
        console.warn('[nexus]', event);
        setSwitching(false);
        break;
    }
  }, []);

  // ── Mic level meter ──

  const startMeter = useCallback((stream: MediaStream) => {
    try {
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(analyser);
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;

      const buffer = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(buffer);
        // RMS around the 128 midpoint of unsigned 8-bit PCM.
        let sum = 0;
        for (let i = 0; i < buffer.length; i += 1) {
          const v = (buffer[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / buffer.length);
        setMicLevel(Math.min(1, rms * 4));
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch (e) {
      console.warn('mic meter unavailable', e);
    }
  }, []);

  const stopMeter = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    analyserRef.current = null;
    setMicLevel(0);
  }, []);

  // ── Lifecycle ──

  const connect = useCallback(
    async (opts: { voiceId?: string; prospectName?: string } = {}) => {
      setError('');
      setStatus('requesting-mic');

      let micStream: MediaStream;
      try {
        // Ask before spending anything. A denied mic here costs nothing; a denied
        // mic after connecting leaves an agent talking to silence on the meter.
        micStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
      } catch {
        setStatus('error');
        setError(
          'Microphone access was blocked. Allow the mic in your browser address bar, then try again.',
        );
        return;
      }

      setStatus('connecting');
      let detail: DemoSession;
      try {
        const response = await fetch(`${API_URL}/demo/session`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            // ngrok's free tier serves an HTML interstitial to browser-agent
            // requests. Without this the fetch resolves with that page instead
            // of JSON and the parse blows up somewhere confusing. Harmless when
            // not behind ngrok.
            'ngrok-skip-browser-warning': 'true',
          },
          body: JSON.stringify({
            voice_id: opts.voiceId ?? '',
            prospect_name: opts.prospectName ?? '',
          }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || `Server returned ${response.status}`);
        }

        // A same-origin misconfiguration returns the Next.js 404 page (HTML)
        // with a 200, so check the type rather than trusting response.ok.
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
          throw new Error(
            'The demo API returned a non-JSON response. Check that the /api proxy is configured.',
          );
        }
        detail = await response.json();
      } catch (e) {
        micStream.getTracks().forEach((t) => t.stop());
        setStatus('error');
        setError(e instanceof Error ? e.message : 'Could not reach the demo server.');
        return;
      }

      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        // Publish at a speech-appropriate rate; the agent's STT is 16kHz mono.
        audioCaptureDefaults: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      roomRef.current = room;

      room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
        if (topic !== TELEMETRY_TOPIC) return;
        try {
          handleEvent(JSON.parse(new TextDecoder().decode(payload)) as TelemetryEvent);
        } catch {
          /* a malformed frame is not worth breaking the call over */
        }
      });

      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind !== Track.Kind.Audio) return;
        // Attach the agent's voice to a real <audio> element. Browsers will not
        // play a MediaStream that is not attached to one.
        const el = (track as RemoteAudioTrack).attach();
        el.autoplay = true;
        document.body.appendChild(el);
        audioElRef.current = el;
        el.play().catch(() => {
          setError('Your browser blocked audio playback. Click anywhere on the page.');
        });
      });

      room.on(RoomEvent.Disconnected, () => {
        stopMeter();
        setStatus('ended');
        setAgentState('idle');
      });

      room.on(RoomEvent.ConnectionStateChanged, (state) => {
        if (state === ConnectionState.Reconnecting) setAgentState('initializing');
      });

      try {
        await room.connect(detail.url, detail.token);
        await room.localParticipant.setMicrophoneEnabled(true);
        setMicEnabled(true);
        startMeter(micStream);
        setStatus('live');
      } catch (e) {
        micStream.getTracks().forEach((t) => t.stop());
        setStatus('error');
        setError(e instanceof Error ? e.message : 'Could not connect to the voice session.');
      }
    },
    [handleEvent, startMeter, stopMeter],
  );

  const disconnect = useCallback(async () => {
    stopMeter();
    await roomRef.current?.disconnect();
    roomRef.current = null;
    audioElRef.current?.remove();
    audioElRef.current = null;
    setStatus('ended');
  }, [stopMeter]);

  const toggleMic = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const next = !micEnabled;
    await room.localParticipant.setMicrophoneEnabled(next);
    setMicEnabled(next);
  }, [micEnabled]);

  const switchVoice = useCallback(
    async (voiceId: string) => {
      const room = roomRef.current;
      if (!room || voiceId === voice?.voice_id) return;
      setSwitching(true);
      try {
        await room.localParticipant.publishData(
          new TextEncoder().encode(JSON.stringify({ type: 'switch_voice', voice_id: voiceId })),
          { reliable: true, topic: CONTROL_TOPIC },
        );
        // The agent confirms with a voice_changed event, which clears `switching`.
        // If it never arrives, do not leave the picker spinning forever.
        setTimeout(() => setSwitching(false), 4000);
      } catch {
        setSwitching(false);
      }
    },
    [voice],
  );

  // Disconnect on unmount — a live room left behind bills until it times out.
  useEffect(() => {
    return () => {
      stopMeter();
      roomRef.current?.disconnect();
      audioElRef.current?.remove();
    };
  }, [stopMeter]);

  const lastTurn = turns.length ? turns[turns.length - 1] : null;
  const avgLatency = turns.length
    ? Math.round(turns.reduce((sum, t) => sum + t.total_ms, 0) / turns.length)
    : 0;
  const bestLatency = turns.length ? Math.round(Math.min(...turns.map((t) => t.total_ms))) : 0;

  return {
    status,
    error,
    session,
    agentState,
    convoState,
    transcript,
    turns,
    lastTurn,
    avgLatency,
    bestLatency,
    sources,
    kbStats,
    interventions,
    toolCalls,
    voices,
    voice,
    switching,
    micLevel,
    micEnabled,
    connect,
    disconnect,
    toggleMic,
    switchVoice,
  };
}
