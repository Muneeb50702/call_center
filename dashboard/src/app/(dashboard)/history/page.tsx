"use client";

import { useEffect, useState, useCallback } from "react";
import { Search, Download, Play, MoreVertical } from "lucide-react";
import { fetchApi } from "@/lib/api";
import DataTable, { Column } from "@/components/ui/DataTable";
import { SkeletonTable } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

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
  const { addToast } = useToast();

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
    if (!seconds) return "—";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m ${s}s`;
  };

  const filteredCalls = calls.filter(c =>
    (c.driver_name || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
    (c.driver_mc || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const exportCSV = () => {
    if (filteredCalls.length === 0) {
      addToast({ type: "warning", title: "No data to export" });
      return;
    }
    const headers = ["Call ID", "Driver", "MC Number", "Date", "Mode", "Duration (s)", "Outcome", "Transferred", "Agreed Rate"];
    const rows = filteredCalls.map(c => [
      c.id,
      c.driver_name || "Unknown",
      c.driver_mc || "",
      c.started_at ? new Date(c.started_at).toISOString() : "",
      c.call_mode || "",
      c.duration_seconds?.toString() || "0",
      c.outcome || "",
      c.transferred_to_human ? "Yes" : "No",
      c.agreed_rate?.toFixed(2) || "0",
    ]);
    const csv = [headers.join(","), ...rows.map(r => r.map(v => `"${v}"`).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `nexus_call_history_${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    addToast({ type: "success", title: "CSV exported", message: `${filteredCalls.length} calls exported successfully.` });
  };

  const columns: Column<CallHistory>[] = [
    {
      key: "id",
      label: "Call ID",
      sortable: true,
      width: "120px",
      render: (val) => (
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem", color: "var(--text-muted)" }}>
          {val?.substring(0, 8)}...
        </span>
      ),
    },
    {
      key: "driver_name",
      label: "Driver",
      sortable: true,
      render: (val, row) => (
        <div>
          <span style={{ fontWeight: 500 }}>{val || "Unknown"}</span>
          {row.driver_mc && <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{row.driver_mc}</div>}
        </div>
      ),
    },
    {
      key: "started_at",
      label: "Date & Time",
      sortable: true,
      render: (val) => (
        <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          {val ? new Date(val).toLocaleString() : "—"}
        </span>
      ),
    },
    {
      key: "call_mode",
      label: "Mode",
      sortable: true,
      render: (val) => <span className="badge badge-neutral">{(val || "unknown").replace(/_/g, " ")}</span>,
    },
    {
      key: "duration_seconds",
      label: "Duration",
      sortable: true,
      align: "right",
      render: (val) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{formatDuration(val)}</span>
      ),
    },
    {
      key: "outcome",
      label: "Outcome",
      sortable: true,
      render: (val, row) => {
        const cls = val === "booked" || val === "resolved" ? "badge-success" : row.transferred_to_human ? "badge-warning" : "badge-neutral";
        const text = row.transferred_to_human ? "Transferred" : (val || "unknown").replace(/_/g, " ");
        return <span className={`badge ${cls}`}>{text}</span>;
      },
    },
    {
      key: "actions",
      label: "",
      width: "80px",
      render: () => (
        <div style={{ display: "flex", gap: "var(--spacing-2)" }}>
          <button className="btn-secondary" style={{ padding: "4px 8px" }} title="Play Recording"><Play size={14} /></button>
        </div>
      ),
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "var(--spacing-1)" }}>Call History</h2>
          <p style={{ color: "var(--text-secondary)" }}>Review past calls, listen to recordings, and analyze transcripts.</p>
        </div>
        <button className="btn-primary" onClick={exportCSV}><Download size={18} /> Export CSV</button>
      </div>

      {/* Search */}
      <div className="glass-panel" style={{ padding: "var(--spacing-4)", display: "flex", gap: "var(--spacing-4)" }}>
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
      </div>

      {loading ? (
        <SkeletonTable rows={8} columns={7} />
      ) : (
        <DataTable
          data={filteredCalls}
          columns={columns}
          pageSize={10}
          emptyMessage="No calls found. Calls will appear here after the AI handles incoming dispatch calls."
        />
      )}
    </div>
  );
}
