"use client";

import { useEffect, useState, useRef } from "react";
import { Phone, CheckCircle, Clock, AlertTriangle, PhoneIncoming, TrendingUp } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { fetchApi } from "@/lib/api";
import { SkeletonCardGrid } from "@/components/ui/Skeleton";

/** Animated counter that counts up from 0 to target */
function AnimatedNumber({ value, duration = 1200, prefix = "", suffix = "" }: { value: number; duration?: number; prefix?: string; suffix?: string }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef<number | null>(null);
  const startTime = useRef<number>(0);

  useEffect(() => {
    if (value === 0) { setDisplay(0); return; }
    startTime.current = performance.now();
    const animate = (now: number) => {
      const elapsed = now - startTime.current;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setDisplay(Math.round(eased * value));
      if (progress < 1) ref.current = requestAnimationFrame(animate);
    };
    ref.current = requestAnimationFrame(animate);
    return () => { if (ref.current) cancelAnimationFrame(ref.current); };
  }, [value, duration]);

  return <>{prefix}{display}{suffix}</>;
}

export default function TenantAdminView() {
  const [kpiData, setKpiData] = useState<any>(null);
  const [chartData, setChartData] = useState<any[]>([]);
  const [liveCalls, setLiveCalls] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [kpis, daily, calls] = await Promise.all([
          fetchApi("/analytics/kpis"),
          fetchApi("/analytics/daily"),
          fetchApi("/calls/history?limit=3")
        ]);
        setKpiData(kpis);
        setChartData(daily.map((d: any) => ({ time: d.date, calls: d.calls, bookings: d.bookings })));
        setLiveCalls(calls);
      } catch (err) {
        console.error("Failed to load dashboard data:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>
        <SkeletonCardGrid count={4} />
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "var(--spacing-6)" }}>
          <div className="glass-panel" style={{ height: "380px" }} />
          <div className="glass-panel" style={{ height: "380px" }} />
        </div>
      </div>
    );
  }

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m ${s}s`;
  };

  const kpis = [
    {
      title: "Total Calls (Today)",
      value: kpiData?.calls_today || 0,
      suffix: "",
      gradient: "linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(139, 92, 246, 0.08))",
      iconBg: "rgba(59, 130, 246, 0.15)",
      iconColor: "var(--accent-primary)",
      icon: Phone,
    },
    {
      title: "Bookings (All Time)",
      value: kpiData?.total_bookings || 0,
      suffix: "",
      gradient: "linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(16, 185, 129, 0.05))",
      iconBg: "rgba(16, 185, 129, 0.15)",
      iconColor: "var(--success)",
      icon: CheckCircle,
    },
    {
      title: "Avg Duration",
      value: kpiData?.avg_call_duration_s || 0,
      isTime: true,
      gradient: "linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(245, 158, 11, 0.04))",
      iconBg: "rgba(245, 158, 11, 0.15)",
      iconColor: "var(--warning)",
      icon: Clock,
    },
    {
      title: "Human Transfers",
      value: kpiData?.transfer_rate_pct || 0,
      suffix: "%",
      gradient: "linear-gradient(135deg, rgba(239, 68, 68, 0.12), rgba(239, 68, 68, 0.04))",
      iconBg: "rgba(239, 68, 68, 0.15)",
      iconColor: "var(--danger)",
      icon: AlertTriangle,
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>

      {/* ── KPI Cards ── */}
      <div className="stagger-in" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "var(--spacing-4)" }}>
        {kpis.map((kpi, i) => {
          const Icon = kpi.icon;
          return (
            <div
              key={i}
              className="glass-panel"
              style={{
                padding: "var(--spacing-5)",
                display: "flex",
                flexDirection: "column",
                gap: "var(--spacing-3)",
                background: kpi.gradient,
                transition: "transform 0.2s ease, box-shadow 0.2s ease",
                cursor: "default",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "var(--shadow-lg)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = "var(--shadow-md)"; }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "var(--text-secondary)", fontSize: "0.875rem", fontWeight: 500 }}>{kpi.title}</span>
                <div style={{
                  padding: "10px",
                  background: kpi.iconBg,
                  borderRadius: "var(--radius-lg)",
                  color: kpi.iconColor,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}>
                  <Icon size={20} />
                </div>
              </div>
              <h2 style={{ fontSize: "2.25rem", fontWeight: 700, lineHeight: 1, letterSpacing: "-0.02em" }}>
                {kpi.isTime ? (
                  formatDuration(kpi.value)
                ) : (
                  <AnimatedNumber value={kpi.value} suffix={kpi.suffix} />
                )}
              </h2>
            </div>
          );
        })}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "var(--spacing-6)", alignItems: "start" }}>

        {/* ── Main Chart ── */}
        <div className="glass-panel animate-fade-in" style={{ padding: "var(--spacing-6)" }}>
          <div style={{ marginBottom: "var(--spacing-6)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ fontSize: "1.125rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "8px" }}>
              <TrendingUp size={18} color="var(--accent-primary)" />
              Fleet Call Volume vs Bookings
            </h3>
            <span className="badge badge-neutral">Daily</span>
          </div>
          <div style={{ height: "300px", width: "100%" }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="var(--accent-primary)" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorBookings" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--success)" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="var(--success)" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
                <XAxis dataKey="time" stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--border)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }}
                  itemStyle={{ color: 'var(--text-primary)' }}
                />
                <Area type="monotone" dataKey="calls" stroke="var(--accent-primary)" strokeWidth={3} fillOpacity={1} fill="url(#colorCalls)" />
                <Area type="monotone" dataKey="bookings" stroke="var(--success)" strokeWidth={3} fillOpacity={1} fill="url(#colorBookings)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ── Recent Calls Feed ── */}
        <div className="glass-panel animate-fade-in" style={{ padding: "var(--spacing-6)" }}>
          <div style={{ marginBottom: "var(--spacing-6)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ fontSize: "1.125rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "8px" }}>
              <PhoneIncoming size={18} color="var(--accent-primary)" />
              Recent Calls
            </h3>
            <span className="badge badge-success" style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <div className="live-pulse" style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--success)" }} />
              {liveCalls.length} Found
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-3)" }}>
            {liveCalls.map((call) => (
              <div key={call.id} style={{
                padding: "var(--spacing-3)", borderRadius: "var(--radius-md)",
                background: "var(--bg-tertiary)", border: "1px solid var(--border-light)",
                display: "flex", flexDirection: "column", gap: "var(--spacing-2)",
                transition: "border-color var(--transition-fast)",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border-light)")}
              >
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontWeight: 600 }}>{call.driver_name || "Unknown Driver"}</span>
                  <span style={{ color: "var(--accent-primary)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                    {formatDuration(call.duration_seconds)}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  <span>{call.driver_mc || "Pending MC"}</span>
                  <span className="badge badge-neutral">{call.call_mode}</span>
                </div>
              </div>
            ))}
            {liveCalls.length === 0 && (
              <div style={{ color: "var(--text-muted)", fontSize: "0.875rem", padding: "var(--spacing-4)", textAlign: "center" }}>No recent calls</div>
            )}
          </div>

          <button className="btn-secondary" style={{ width: "100%", marginTop: "var(--spacing-4)" }} onClick={() => window.location.href='/history'}>
            View All Calls
          </button>
        </div>

      </div>
    </div>
  );
}
