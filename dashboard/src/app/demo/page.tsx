'use client';

/**
 * The client-facing pitch page.
 *
 * Two audiences in one screen. The hero has to land with someone who just wants
 * to press a button and talk; the HUD has to survive a technical founder asking
 * "yes, but what's the actual latency and how do I know it isn't making things
 * up?". So the numbers are real, measured per turn, and broken down by stage —
 * a single averaged headline figure would read as marketing.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import styles from './demo.module.css';
import { useVoiceSession } from './useVoiceSession';

const STAGE_COLORS = {
  eou: '#f59e0b',
  llm: '#8b5cf6',
  tts: '#06b6d4',
};

/** Latency bands. Sub-800ms reads as conversational; past ~1.5s people talk over it. */
function latencyGrade(ms: number): { label: string; className: string } {
  if (ms <= 0) return { label: '—', className: styles.gradeIdle };
  if (ms < 800) return { label: 'Excellent', className: styles.gradeGood };
  if (ms < 1200) return { label: 'Good', className: styles.gradeOk };
  if (ms < 1800) return { label: 'Noticeable', className: styles.gradeWarn };
  return { label: 'Slow', className: styles.gradeBad };
}

export default function DemoPage() {
  const s = useVoiceSession();
  const [name, setName] = useState('');
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = transcriptRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [s.transcript]);

  const start = useCallback(() => {
    s.connect({ prospectName: name.trim() });
  }, [s, name]);

  const live = s.status === 'live';
  const connecting = s.status === 'connecting' || s.status === 'requesting-mic';
  const grade = latencyGrade(s.lastTurn?.total_ms ?? 0);

  return (
    <main className={styles.page}>
      {/* ── Header ── */}
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.brandMark} />
          <span className={styles.brandName}>Nexus Voice</span>
        </div>
        <div className={styles.headerMeta}>
          {live && s.session ? (
            <>
              <span className={`${styles.dot} ${styles.dotLive}`} />
              Live · {s.session.companyName} knowledge base
            </>
          ) : (
            <>Built for Lumenia</>
          )}
        </div>
      </header>

      {/* ── Hero ── */}
      {!live && (
        <section className={styles.hero}>
          <p className={styles.eyebrow}>Voice AI for outbound sales</p>
          <h1 className={styles.title}>
            An AI sales rep that <em>already knows</em> Lumenia.
          </h1>
          <p className={styles.sub}>
            We read every page of lumenialab.com and gave it to a voice agent. It answers
            from your own material — services, projects, process, contact — and it will
            tell you when it doesn&apos;t know something instead of making it up.
            Press the button and interrogate it.
          </p>

          <div className={styles.startRow}>
            <input
              className={styles.nameInput}
              placeholder="Your name (optional)"
              value={name}
              maxLength={40}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && start()}
              disabled={connecting}
            />
            <button className={styles.startBtn} onClick={start} disabled={connecting}>
              {s.status === 'requesting-mic'
                ? 'Allow microphone…'
                : connecting
                  ? 'Connecting…'
                  : 'Start talking'}
            </button>
          </div>

          {s.error && <p className={styles.error}>{s.error}</p>}
          {s.status === 'ended' && !s.error && (
            <p className={styles.ended}>Call ended. Press start to run it again.</p>
          )}

          <ul className={styles.tryList}>
            <li>&ldquo;What does Lumenia actually do?&rdquo;</li>
            <li>&ldquo;Have you built anything for logistics?&rdquo;</li>
            <li>&ldquo;How much does a project cost?&rdquo;</li>
            <li>&ldquo;Are you a bot?&rdquo;</li>
            <li>&ldquo;Who is your CEO?&rdquo; <span>— watch it decline</span></li>
          </ul>
        </section>
      )}

      {/* ── Live console ── */}
      {live && (
        <section className={styles.console}>
          {/* Left: conversation */}
          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>Conversation</h2>
              <span className={`${styles.pill} ${styles[`agent_${s.agentState}`] ?? ''}`}>
                {s.agentState}
              </span>
            </div>

            <div className={styles.transcript} ref={transcriptRef}>
              {s.transcript.length === 0 && (
                <p className={styles.hint}>Say hello — the agent is listening.</p>
              )}
              {s.transcript.map((line, i) => (
                <div
                  key={`${line.at}-${i}`}
                  className={`${styles.line} ${line.speaker === 'user' ? styles.lineUser : styles.lineAgent}`}
                >
                  <span className={styles.speaker}>
                    {line.speaker === 'user' ? 'You' : s.session?.agentName ?? 'Agent'}
                  </span>
                  <p className={!line.final ? styles.interim : undefined}>{line.text}</p>
                </div>
              ))}
            </div>

            <div className={styles.micRow}>
              <div className={styles.meter}>
                <div
                  className={styles.meterFill}
                  style={{ width: `${Math.round(s.micLevel * 100)}%` }}
                />
              </div>
              <button className={styles.ghostBtn} onClick={s.toggleMic}>
                {s.micEnabled ? 'Mute' : 'Unmute'}
              </button>
              <button className={styles.endBtn} onClick={s.disconnect}>
                End
              </button>
            </div>
          </div>

          {/* Center: latency */}
          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>Response latency</h2>
              <span className={styles.subtle}>measured, per turn</span>
            </div>

            <div className={styles.bigNumber}>
              <span className={styles.bigValue}>{Math.round(s.lastTurn?.total_ms ?? 0)}</span>
              <span className={styles.bigUnit}>ms</span>
              <span className={`${styles.grade} ${grade.className}`}>{grade.label}</span>
            </div>
            <p className={styles.bigCaption}>
              From the moment you stop speaking to the first syllable you hear.
            </p>

            {s.lastTurn && (
              <div className={styles.breakdown}>
                {[
                  { key: 'eou', label: 'Turn detection', value: s.lastTurn.eou_delay_ms },
                  { key: 'llm', label: 'Thinking (TTFT)', value: s.lastTurn.llm_ttft_ms },
                  { key: 'tts', label: 'Voice (TTFB)', value: s.lastTurn.tts_ttfb_ms },
                ].map((stage) => (
                  <div key={stage.key} className={styles.stage}>
                    <div className={styles.stageHead}>
                      <span>{stage.label}</span>
                      <strong>{Math.round(stage.value)}ms</strong>
                    </div>
                    <div className={styles.stageBar}>
                      <div
                        className={styles.stageFill}
                        style={{
                          width: `${Math.min(100, (stage.value / (s.lastTurn!.total_ms || 1)) * 100)}%`,
                          background: STAGE_COLORS[stage.key as keyof typeof STAGE_COLORS],
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {s.turns.length > 1 && (
              <>
                <div className={styles.spark}>
                  {s.turns.map((t, i) => (
                    <div
                      key={t.speech_id + i}
                      className={styles.sparkBar}
                      style={{
                        height: `${Math.min(100, (t.total_ms / 2000) * 100)}%`,
                        background:
                          t.total_ms < 800
                            ? '#22c55e'
                            : t.total_ms < 1200
                              ? '#eab308'
                              : '#ef4444',
                      }}
                      title={`${Math.round(t.total_ms)}ms`}
                    />
                  ))}
                </div>
                <div className={styles.statRow}>
                  <div>
                    <span>{s.turns.length}</span>turns
                  </div>
                  <div>
                    <span>{s.avgLatency}</span>ms avg
                  </div>
                  <div>
                    <span>{s.bestLatency}</span>ms best
                  </div>
                </div>
              </>
            )}

            {s.lastTurn?.cache_hit_rate !== null && s.lastTurn && (
              <p className={styles.footnote}>
                Prompt cache hit {Math.round((s.lastTurn.cache_hit_rate ?? 0) * 100)}% ·{' '}
                {s.lastTurn.prompt_tokens} prompt tokens
              </p>
            )}
          </div>

          {/* Right: grounding */}
          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <h2>What it&apos;s reading</h2>
              <span className={styles.subtle}>
                {s.kbStats.lastLatencyMs > 0 && `${s.kbStats.lastLatencyMs.toFixed(1)}ms`}
              </span>
            </div>

            <div className={styles.kbStats}>
              <div>
                <span>{s.session?.kbChunks ?? 0}</span>chunks
              </div>
              <div>
                <span>{s.session?.kbDocs ?? 0}</span>pages
              </div>
              <div>
                <span>{s.kbStats.queries}</span>lookups
              </div>
              <div>
                <span>{s.kbStats.misses}</span>declined
              </div>
            </div>

            <div className={styles.sources}>
              {s.sources.length === 0 ? (
                <p className={styles.hint}>
                  Ask something about Lumenia and the exact sources it used will appear here.
                </p>
              ) : (
                s.sources.map((src) => (
                  <article key={src.chunk_id} className={styles.source}>
                    <div className={styles.sourceHead}>
                      <span className={styles.sourceTitle}>{src.heading}</span>
                      <span className={`${styles.badge} ${styles[`badge_${src.matched_by}`]}`}>
                        {src.matched_by}
                      </span>
                    </div>
                    <p className={styles.sourceText}>{src.text.slice(0, 180)}…</p>
                    <div className={styles.sourceFoot}>
                      <span>{src.score.toFixed(2)} similarity</span>
                      {src.source_url && (
                        <a href={src.source_url} target="_blank" rel="noreferrer">
                          source ↗
                        </a>
                      )}
                    </div>
                  </article>
                ))
              )}
            </div>

            <div className={styles.guardRow}>
              <div className={styles.guard}>
                <span className={styles.guardValue}>{s.interventions}</span>
                <span className={styles.guardLabel}>
                  ungrounded facts blocked before they were spoken
                </span>
              </div>
              {s.convoState && (
                <div className={styles.guard}>
                  <span className={styles.guardValue}>{s.convoState.replace(/_/g, ' ')}</span>
                  <span className={styles.guardLabel}>conversation stage</span>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* ── Voice picker ── */}
      {live && s.voices.length > 0 && (
        <section className={styles.voices}>
          <div className={styles.voicesHead}>
            <h2>Switch the voice mid-call</h2>
            <p>No reconnect. The change lands on the next thing it says.</p>
          </div>
          <div className={styles.voiceRow}>
            {s.voices.map((v) => (
              <button
                key={v.voice_id}
                className={`${styles.voiceChip} ${v.voice_id === s.voice?.voice_id ? styles.voiceActive : ''}`}
                onClick={() => s.switchVoice(v.voice_id)}
                disabled={s.switching}
                title={v.blurb}
              >
                <span className={styles.voiceName}>{v.label}</span>
                <span className={styles.voiceMeta}>
                  {v.gender === 'feminine' ? 'F' : v.gender === 'masculine' ? 'M' : '—'} ·{' '}
                  {v.accent}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* ── Pipeline footer ── */}
      {live && s.session && (
        <footer className={styles.pipeline}>
          {Object.entries(s.session.pipeline).map(([k, v]) => (
            <span key={k} className={styles.pipeChip}>
              <em>{k.replace(/_/g, ' ')}</em>
              {typeof v === 'boolean' ? (v ? 'on' : 'off') : v}
            </span>
          ))}
        </footer>
      )}
    </main>
  );
}
