"use client";

import { useEffect, useState, useRef } from "react";
import { Phone, User, MicOff, Send, MessageSquare, AlertTriangle, CheckCircle2 } from "lucide-react";
import { fetchApi } from "@/lib/api";

interface TranscriptMessage {
  speaker: "user" | "agent";
  text: string;
  timestamp: number;
}

interface ActiveCall {
  call_id: string;
  tenant_id: string;
  driver_name: string;
  driver_mc: string;
  current_state: string;
  started_at: number;
  transcripts: TranscriptMessage[];
  escalated: boolean;
  escalation_reason?: string;
  latency_ms?: number;
}

export default function LiveMonitorPage() {
  const [activeCalls, setActiveCalls] = useState<Map<string, ActiveCall>>(new Map());
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
  const [wsStatus, setWsStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [whisperText, setWhisperText] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // Connect to WebSocket
  useEffect(() => {
    // In production, we'd get this from a proper auth context or API call
    const token = localStorage.getItem("token") || "test_token"; 
    // Usually WebSocket URL replaces http:// with ws://
    const wsUrl = process.env.NEXT_PUBLIC_API_URL?.replace("http", "ws") || "ws://localhost:8000";
    
    const ws = new WebSocket(`${wsUrl}/ws/calls/live?token=${token}`);
    wsRef.current = ws;

    ws.onopen = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");
    ws.onerror = (e) => console.error("WebSocket error", e);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWsMessage(data);
      } catch (err) {
        console.error("Failed to parse WS message", err);
      }
    };

    // Ping interval to keep connection alive
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      ws.close();
    };
  }, []);

  const handleWsMessage = (data: any) => {
    setActiveCalls((prev) => {
      const next = new Map(prev);
      
      // If we got a snapshot, initialize calls
      if (data.type === "snapshot") {
        data.active_calls?.forEach((call: any) => {
          if (!next.has(call.call_id)) {
            next.set(call.call_id, {
              call_id: call.call_id,
              tenant_id: call.tenant_id,
              driver_name: call.driver_name || "Unknown Driver",
              driver_mc: call.driver_mc || "",
              current_state: call.current_state || "Greeting",
              started_at: call.started_at || Date.now(),
              transcripts: [],
              escalated: false,
            });
          }
        });
        return next;
      }

      const callId = data.call_id;
      if (!callId) return prev;

      // Auto-create call if it doesn't exist
      if (!next.has(callId)) {
        next.set(callId, {
          call_id: callId,
          tenant_id: data.tenant_id,
          driver_name: "Connecting...",
          driver_mc: "",
          current_state: "Initializing",
          started_at: Date.now(),
          transcripts: [],
          escalated: false,
        });
      }

      const call = { ...next.get(callId)! };

      switch (data.type) {
        case "transcript":
          call.transcripts = [
            ...call.transcripts, 
            { speaker: data.speaker, text: data.text, timestamp: Date.now() }
          ];
          break;
        case "state_changed":
          call.current_state = data.new_state;
          break;
        case "alert":
          call.escalated = true;
          call.escalation_reason = data.message;
          break;
        case "call_started":
          call.driver_name = data.driver_name || "Unknown Driver";
          call.driver_mc = data.driver_mc || "";
          break;
        case "call_ended":
          // Keep it on screen for a moment, or mark as ended
          call.current_state = "Ended";
          break;
        case "whisper_sent":
          call.transcripts = [
            ...call.transcripts, 
            { speaker: "agent", text: `(Whispered instruction: ${data.text})`, timestamp: Date.now() }
          ];
          break;
      }

      next.set(callId, call);
      
      // If no call is selected, select the first active one
      if (!selectedCallId && next.size > 0) {
        setSelectedCallId(next.keys().next().value || null);
      }

      return next;
    });
  };

  // Auto-scroll transcripts
  useEffect(() => {
    if (transcriptEndRef.current) {
      transcriptEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [activeCalls, selectedCallId]);

  const sendWhisper = () => {
    if (!whisperText.trim() || !selectedCallId || !wsRef.current) return;
    
    wsRef.current.send(JSON.stringify({
      type: "whisper",
      call_id: selectedCallId,
      text: whisperText.trim()
    }));
    
    setWhisperText("");
  };

  const callsList = Array.from(activeCalls.values());
  const selectedCall = selectedCallId ? activeCalls.get(selectedCallId) : null;

  const formatDuration = (ms: number) => {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    return `${m}:${(s % 60).toString().padStart(2, '0')}`;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)", height: "calc(100vh - 100px)" }}>
      
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "var(--spacing-1)" }}>Live Calls Monitor</h2>
          <p style={{ color: "var(--text-secondary)" }}>Monitor and intervene in ongoing dispatch calls in real-time.</p>
        </div>
        <div style={{ display: "flex", gap: "var(--spacing-3)" }}>
          <div className="glass-panel" style={{ padding: "var(--spacing-2) var(--spacing-4)", display: "flex", alignItems: "center", gap: "var(--spacing-2)" }}>
            <div style={{ 
              width: "8px", height: "8px", borderRadius: "50%", 
              background: wsStatus === "connected" ? "var(--success)" : wsStatus === "connecting" ? "var(--warning)" : "var(--danger)",
              boxShadow: `0 0 8px ${wsStatus === "connected" ? "var(--success)" : "transparent"}`
            }} />
            <span style={{ fontWeight: 600 }}>{callsList.length} Active Sessions</span>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "var(--spacing-6)", flex: 1, minHeight: 0 }}>
        
        {/* Calls List (Left Sidebar) */}
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-3)", overflowY: "auto", paddingRight: "4px" }}>
          {callsList.length === 0 ? (
            <div className="glass-panel" style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
              No active calls at the moment. Waiting for incoming connections...
            </div>
          ) : (
            callsList.map(call => (
              <div 
                key={call.call_id} 
                onClick={() => setSelectedCallId(call.call_id)}
                className="glass-panel" 
                style={{ 
                  padding: "var(--spacing-4)", 
                  cursor: "pointer",
                  border: selectedCallId === call.call_id ? "1px solid var(--accent-primary)" : "1px solid var(--border)",
                  background: selectedCallId === call.call_id ? "var(--bg-tertiary)" : "var(--bg-secondary)",
                  transition: "all 0.2s ease"
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--spacing-2)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span className={`badge ${call.current_state === 'Ended' ? 'badge-neutral' : 'badge-success'}`}>
                      {call.current_state === 'Ended' ? 'Ended' : 'Live'}
                    </span>
                    {call.escalated && <AlertTriangle size={14} color="var(--danger)" />}
                  </div>
                  <span style={{ fontSize: "0.875rem", fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
                    {formatDuration(Date.now() - call.started_at)}
                  </span>
                </div>
                <h4 style={{ fontWeight: 600, fontSize: "1.05rem" }}>{call.driver_name} {call.driver_mc ? `(${call.driver_mc})` : ""}</h4>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginTop: "4px" }}>
                  State: <strong style={{ color: "var(--text-primary)" }}>{call.current_state.replace(/_/g, " ")}</strong>
                </p>
              </div>
            ))
          )}
        </div>

        {/* Active Call Detail (Right Panel) */}
        {selectedCall ? (
          <div className="glass-panel" style={{ display: "flex", flexDirection: "column", border: selectedCall.escalated ? "1px solid var(--danger)" : "1px solid var(--border)" }}>
            
            {/* Call Detail Header */}
            <div style={{ padding: "var(--spacing-4) var(--spacing-6)", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--bg-tertiary)", borderTopLeftRadius: "var(--radius-lg)", borderTopRightRadius: "var(--radius-lg)" }}>
              <div>
                <h3 style={{ fontSize: "1.25rem", fontWeight: 600 }}>{selectedCall.driver_name} {selectedCall.driver_mc ? `(${selectedCall.driver_mc})` : ""}</h3>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>Call ID: {selectedCall.call_id.substring(0, 8)}... | State: {selectedCall.current_state.replace(/_/g, " ")}</p>
              </div>
              <div style={{ display: "flex", gap: "var(--spacing-3)" }}>
                <button className="btn-secondary" style={{ color: "var(--warning)" }}><MicOff size={16} /> Mute AI</button>
                <button className="btn-primary" style={{ background: "var(--danger)", color: "white", borderColor: "var(--danger)" }}>Take Over</button>
              </div>
            </div>

            {selectedCall.escalated && (
              <div style={{ padding: "var(--spacing-3) var(--spacing-6)", background: "rgba(239, 68, 68, 0.1)", borderBottom: "1px solid var(--danger)", color: "var(--danger)", display: "flex", alignItems: "center", gap: "8px", fontWeight: 500 }}>
                <AlertTriangle size={18} /> ESCALATION: {selectedCall.escalation_reason || "Human intervention required"}
              </div>
            )}

            {/* Transcript Area */}
            <div style={{ flex: 1, padding: "var(--spacing-6)", overflowY: "auto", display: "flex", flexDirection: "column", gap: "var(--spacing-4)" }}>
              {selectedCall.transcripts.length === 0 ? (
                <div style={{ margin: "auto", color: "var(--text-muted)", display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
                  <MessageSquare size={32} opacity={0.5} />
                  <p>Waiting for speech...</p>
                </div>
              ) : (
                selectedCall.transcripts.map((msg, idx) => (
                  <div key={idx} style={{ display: "flex", gap: "var(--spacing-3)", alignSelf: msg.speaker === "agent" ? "flex-end" : "flex-start", flexDirection: msg.speaker === "agent" ? "row-reverse" : "row", maxWidth: "80%" }}>
                    <div style={{ 
                      background: msg.speaker === "agent" ? "var(--accent-glow)" : "var(--border-light)", 
                      color: msg.speaker === "agent" ? "var(--accent-primary)" : "var(--text-primary)", 
                      padding: "8px", borderRadius: "50%", height: "fit-content", flexShrink: 0 
                    }}>
                      {msg.speaker === "agent" ? <Phone size={16} /> : <User size={16} />}
                    </div>
                    <div style={{ textAlign: msg.speaker === "agent" ? "right" : "left" }}>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontWeight: 500, marginBottom: "4px", display: "block" }}>
                        {msg.speaker === "agent" ? "AI Dispatcher" : "Driver"}
                      </span>
                      <p style={{ 
                        background: msg.speaker === "agent" ? "var(--accent-primary)" : "var(--bg-secondary)", 
                        color: msg.speaker === "agent" ? "white" : "var(--text-primary)", 
                        padding: "var(--spacing-3) var(--spacing-4)", 
                        borderRadius: "var(--radius-lg)", 
                        fontSize: "0.9375rem",
                        borderBottomRightRadius: msg.speaker === "agent" ? "4px" : "var(--radius-lg)",
                        borderTopLeftRadius: msg.speaker === "user" ? "4px" : "var(--radius-lg)",
                        lineHeight: 1.5,
                        whiteSpace: "pre-wrap"
                      }}>
                        {msg.text}
                      </p>
                    </div>
                  </div>
                ))
              )}
              <div ref={transcriptEndRef} />
            </div>

            {/* Whisper Input */}
            <div style={{ padding: "var(--spacing-4)", borderTop: "1px solid var(--border)", background: "var(--bg-tertiary)", borderBottomLeftRadius: "var(--radius-lg)", borderBottomRightRadius: "var(--radius-lg)" }}>
              <div style={{ display: "flex", gap: "var(--spacing-3)" }}>
                <input 
                  type="text" 
                  className="input-field" 
                  placeholder="Whisper instructions to the AI (e.g. 'Offer him $2.80')..." 
                  value={whisperText}
                  onChange={e => setWhisperText(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") sendWhisper(); }}
                  disabled={selectedCall.current_state === "Ended"}
                />
                <button 
                  className="btn-primary" 
                  onClick={sendWhisper}
                  disabled={!whisperText.trim() || selectedCall.current_state === "Ended"}
                >
                  <Send size={18} /> Whisper
                </button>
              </div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "var(--spacing-2)" }}>
                Whispers are injected directly into the AI's logic without the driver hearing you.
              </p>
            </div>

          </div>
        ) : (
          <div className="glass-panel" style={{ display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
            Select a call from the list to monitor.
          </div>
        )}
        
      </div>
    </div>
  );
}
