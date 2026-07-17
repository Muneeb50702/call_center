/**
 * Wire types for the demo page.
 *
 * These mirror what the agent publishes on the `nexus.telemetry` data-channel
 * topic (see nexus_agent/pipeline/telemetry.py and pipeline/hooks.py). The agent
 * is the source of truth; this file is the contract.
 */

export const TELEMETRY_TOPIC = 'nexus.telemetry';
export const CONTROL_TOPIC = 'nexus.control';

export interface VoiceProfile {
  voice_id: string;
  provider: string;
  label: string;
  gender: string;
  accent: string;
  traits: string[];
  blurb: string;
  tags: string[];
}

export interface KbSource {
  chunk_id: string;
  title: string;
  heading: string;
  text: string;
  source_url: string;
  category: string;
  score: number;
  matched_by: 'hybrid' | 'keyword' | 'semantic';
}

export interface TurnLatency {
  speech_id: string;
  eou_delay_ms: number;
  transcription_delay_ms: number;
  llm_ttft_ms: number;
  tts_ttfb_ms: number;
  total_ms: number;
  prompt_tokens: number;
  cached_tokens: number;
  completion_tokens: number;
  cache_hit_rate: number | null;
}

export interface TranscriptLine {
  speaker: 'user' | 'agent';
  text: string;
  final: boolean;
  at: number;
}

export type AgentState = 'initializing' | 'idle' | 'listening' | 'thinking' | 'speaking';

/** Every message shape the agent can publish on the telemetry topic. */
export type TelemetryEvent =
  | {
      type: 'session_ready';
      call_id: string;
      tenant_id: string;
      company_name: string;
      agent_name: string;
      profile: string;
      voice: VoiceProfile;
      voices: VoiceProfile[];
      state: string;
      kb: { loaded: boolean; chunks: number; docs: number };
      pipeline: Record<string, string | boolean>;
    }
  | ({ type: 'turn_latency' } & TurnLatency)
  | { type: 'transcript'; speaker: 'user' | 'agent'; text: string; is_final?: boolean }
  | { type: 'agent_state'; state: AgentState }
  | { type: 'state_changed'; old_state: string; new_state: string }
  | { type: 'tool'; name: string }
  | {
      type: 'kb_retrieval';
      sources: KbSource[];
      latency_ms: number;
      queries: number;
      misses: number;
      hit: boolean;
    }
  | { type: 'verifier_intervention'; violations: string[]; total: number }
  | { type: 'voice_changed'; voice: VoiceProfile }
  | { type: 'latency'; metric: string; value: number }
  | { type: 'alert'; level: string; message: string }
  | { type: 'error'; message: string };

export interface DemoSession {
  url: string;
  token: string;
  room: string;
  identity: string;
  tenant_id: string;
  expires_in: number;
}
