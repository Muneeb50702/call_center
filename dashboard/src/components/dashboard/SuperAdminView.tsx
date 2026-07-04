"use client";

import { useEffect, useState } from "react";
import { Activity, Users, DollarSign, Server, ArrowUpRight, ArrowDownRight, UserPlus, ShieldAlert, CheckCircle } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { fetchApi } from "@/lib/api";
import { SkeletonCardGrid } from "@/components/ui/Skeleton";

const mockData = [
  { month: 'Jan', revenue: 12500, usage: 8400 },
  { month: 'Feb', revenue: 15200, usage: 10200 },
  { month: 'Mar', revenue: 18500, usage: 13500 },
  { month: 'Apr', revenue: 22400, usage: 16800 },
  { month: 'May', revenue: 28900, usage: 22100 },
  { month: 'Jun', revenue: 35000, usage: 28400 },
];

const mockRecentActivity = [
  { id: 1, event: "New Tenant Registration", detail: "FastFreight Logistics signed up.", time: "10 mins ago", icon: UserPlus, type: "success" },
  { id: 2, event: "Billing Processed", detail: "$12,450 collected for June.", time: "1 hour ago", icon: DollarSign, type: "info" },
  { id: 3, event: "High API Latency", detail: "ElevensLab TTS spike detected.", time: "2 hours ago", icon: ShieldAlert, type: "warning" },
  { id: 4, event: "Worker Node Added", detail: "LiveKit Worker Node #04 joined.", time: "5 hours ago", icon: Server, type: "info" },
];

export default function SuperAdminView() {
  const [tenantsCount, setTenantsCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const tenants = await fetchApi("/tenants");
        setTenantsCount(tenants.length);
      } catch (err) {
        console.error("Failed to load admin data:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
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

  const kpis = [
    { title: "Total Active Tenants", value: tenantsCount.toString(), change: "Active", positive: true, icon: Users },
    { title: "Platform MRR", value: "$35,000", change: "+12%", positive: true, icon: DollarSign },
    { title: "Global API Uptime", value: "99.99%", change: "Healthy", positive: true, icon: Server },
    { title: "Total Calls Processed", value: "1.2M", change: "+8% this week", positive: true, icon: Activity },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>
      
      {/* ── Global KPIs ── */}
      <div className="stagger-in" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "var(--spacing-4)" }}>
        {kpis.map((kpi, i) => {
          const Icon = kpi.icon;
          return (
            <div key={i} className="glass-panel" style={{ padding: "var(--spacing-4)", display: "flex", flexDirection: "column", gap: "var(--spacing-3)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "var(--text-secondary)", fontSize: "0.875rem", fontWeight: 500 }}>{kpi.title}</span>
                <div style={{ padding: "8px", background: "var(--bg-tertiary)", borderRadius: "var(--radius-md)", color: "var(--accent-secondary)" }}>
                  <Icon size={20} />
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: "var(--spacing-3)" }}>
                <h2 style={{ fontSize: "2rem", fontWeight: 700, lineHeight: 1 }}>{kpi.value}</h2>
                <div style={{ display: "flex", alignItems: "center", color: kpi.positive ? "var(--success)" : "var(--danger)", fontSize: "0.875rem", fontWeight: 600, paddingBottom: "4px" }}>
                  {kpi.change.includes('+') ? <ArrowUpRight size={16} /> : kpi.change === 'Healthy' ? <CheckCircle size={16} /> : <ArrowDownRight size={16} />}
                  <span>{kpi.change}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "var(--spacing-6)", alignItems: "start" }}>
        
        {/* ── Revenue Chart ── */}
        <div className="glass-panel animate-fade-in" style={{ padding: "var(--spacing-6)" }}>
          <div style={{ marginBottom: "var(--spacing-6)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ fontSize: "1.125rem", fontWeight: 600 }}>Platform Revenue & Usage (YTD)</h3>
            <span className="badge badge-neutral">Last 6 Months</span>
          </div>
          <div style={{ height: "300px", width: "100%" }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={mockData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorRev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent-secondary)" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="var(--accent-secondary)" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorUsage" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--info)" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="var(--info)" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
                <XAxis dataKey="month" stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--border)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }}
                  itemStyle={{ color: 'var(--text-primary)' }}
                />
                <Area type="monotone" dataKey="revenue" name="MRR ($)" stroke="var(--accent-secondary)" strokeWidth={3} fillOpacity={1} fill="url(#colorRev)" />
                <Area type="monotone" dataKey="usage" name="API Usage (k)" stroke="var(--info)" strokeWidth={3} fillOpacity={1} fill="url(#colorUsage)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ── System Activity ── */}
        <div className="glass-panel animate-fade-in" style={{ padding: "var(--spacing-6)" }}>
          <div style={{ marginBottom: "var(--spacing-6)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ fontSize: "1.125rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "8px" }}>
              <Activity size={18} color="var(--accent-secondary)" />
              System Activity
            </h3>
          </div>
          
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-3)" }}>
            {mockRecentActivity.map((act) => (
              <div key={act.id} style={{ padding: "var(--spacing-3)", borderRadius: "var(--radius-md)", background: "var(--bg-tertiary)", border: "1px solid var(--border-light)", display: "flex", gap: "var(--spacing-3)", alignItems: "center" }}>
                <div style={{ padding: "8px", borderRadius: "50%", background: `var(--${act.type}-bg)`, color: `var(--${act.type})` }}>
                  <act.icon size={16} />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "2px", flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{act.event}</span>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{act.time}</span>
                  </div>
                  <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>{act.detail}</span>
                </div>
              </div>
            ))}
          </div>
          
          <button className="btn-secondary" style={{ width: "100%", marginTop: "var(--spacing-4)" }}>
            View Full Audit Log
          </button>
        </div>

      </div>
    </div>
  );
}
