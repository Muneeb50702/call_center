"use client";

import { useEffect, useState } from "react";
import { Search, Filter, Play, MoreVertical } from "lucide-react";
import { fetchApi } from "@/lib/api";

interface CallHistory {
  id: string;
  driver_name: string;
  driver_mc: string;
  started_at: string;
  call_mode: string;
  duration_seconds: number;
  outcome: string;
  transferred_to_human: boolean;
  agreed_rate: number;
}

export default function CallHistoryPage() {
  const [calls, setCalls] = useState<CallHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    async function loadData() {
      try {
        const data = await fetchApi("/calls/history");
        setCalls(data);
      } catch (err) {
        console.error("Failed to fetch history:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m ${s}s`;
  };

  const filteredCalls = calls.filter(c => 
    (c.driver_name || "").toLowerCase().includes(searchQuery.toLowerCase()) || 
    (c.driver_mc || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>
      
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "var(--spacing-1)" }}>Call History</h2>
          <p style={{ color: "var(--text-secondary)" }}>Review past calls, listen to recordings, and analyze transcripts.</p>
        </div>
        <button className="btn-primary">Export CSV</button>
      </div>

      <div className="glass-panel">
        
        {/* Toolbar */}
        <div style={{ padding: "var(--spacing-4)", borderBottom: "1px solid var(--border)", display: "flex", gap: "var(--spacing-4)" }}>
          <div style={{ position: "relative", flex: 1 }}>
            <Search size={18} style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input 
              type="text" 
              className="input-field" 
              placeholder="Search by driver, MC, or call ID..." 
              style={{ paddingLeft: "38px" }}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <button className="btn-secondary"><Filter size={18} /> Filters</button>
        </div>
        
        {/* Table */}
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ background: "var(--bg-tertiary)", borderBottom: "1px solid var(--border)" }}>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Call ID</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Driver</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Date & Time</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Mode</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Duration</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Outcome</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>Loading history...</td>
              </tr>
            ) : filteredCalls.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>No calls found.</td>
              </tr>
            ) : (
              filteredCalls.map((call) => (
                <tr key={call.id} style={{ borderBottom: "1px solid var(--border)", transition: "background var(--transition-fast)" }} className="hover:bg-bg-tertiary">
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)", fontFamily: "var(--font-mono)", fontSize: "0.875rem" }}>{call.id}</td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)", fontWeight: 500 }}>
                    {call.driver_name || "Unknown"}
                    {call.driver_mc && <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{call.driver_mc}</div>}
                  </td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                    {new Date(call.started_at).toLocaleString()}
                  </td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)" }}><span className="badge badge-neutral">{call.call_mode}</span></td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)", fontVariantNumeric: "tabular-nums" }}>{formatDuration(call.duration_seconds)}</td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)" }}>
                    <span className={`badge ${call.outcome === 'booked' || call.outcome === 'resolved' ? 'badge-success' : call.transferred_to_human ? 'badge-warning' : 'badge-neutral'}`}>
                      {call.transferred_to_human ? 'Transferred' : call.outcome.replace('_', ' ')}
                    </span>
                  </td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)" }}>
                    <div style={{ display: "flex", gap: "var(--spacing-2)" }}>
                      <button className="btn-secondary" style={{ padding: "4px 8px" }} title="Play Recording"><Play size={14} /></button>
                      <button className="btn-secondary" style={{ padding: "4px 8px" }} title="More"><MoreVertical size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        
      </div>
    </div>
  );
}
