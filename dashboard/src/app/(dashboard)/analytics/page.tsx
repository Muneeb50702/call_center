"use client";

import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Legend, PieChart, Pie, Cell } from 'recharts';
import { Calendar } from "lucide-react";
import { fetchApi } from "@/lib/api";

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444'];

export default function AnalyticsPage() {
  const [dailyData, setDailyData] = useState<any[]>([]);
  const [modeData, setModeData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [daily, modes] = await Promise.all([
          fetchApi("/analytics/daily"),
          fetchApi("/analytics/call-modes")
        ]);
        
        // Map daily data to expected format for Bar chart
        const formattedDaily = daily.map((d: any) => ({
          name: new Date(d.date).toLocaleDateString('en-US', { weekday: 'short' }),
          completed: d.calls - (d.transfers || 0), // If we had transfers returned
          calls: d.calls,
          bookings: d.bookings
        }));
        setDailyData(formattedDaily);

        const formattedModes = modes.map((m: any) => ({
          name: m.mode,
          value: m.count
        }));
        setModeData(formattedModes);
      } catch (err) {
        console.error("Failed to load analytics:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) return <div style={{ padding: "2rem" }}>Loading analytics...</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>
      
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "var(--spacing-1)" }}>Analytics & Insights</h2>
          <p style={{ color: "var(--text-secondary)" }}>Deep dive into AI performance, call resolution, and business metrics.</p>
        </div>
        <button className="btn-secondary"><Calendar size={18} /> Last 30 Days</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "var(--spacing-6)" }}>
        
        {/* Weekly Performance Bar Chart */}
        <div className="glass-panel" style={{ padding: "var(--spacing-6)" }}>
          <h3 style={{ fontSize: "1.125rem", fontWeight: 600, marginBottom: "var(--spacing-6)" }}>Call Volume & Bookings by Day</h3>
          <div style={{ height: "300px", width: "100%" }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dailyData} margin={{ top: 20, right: 30, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
                <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                <RechartsTooltip cursor={{ fill: 'var(--bg-tertiary)' }} contentStyle={{ backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--border)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }} />
                <Legend iconType="circle" wrapperStyle={{ paddingTop: "20px" }} />
                <Bar dataKey="calls" name="Total Calls" fill="var(--accent-primary)" radius={[4, 4, 0, 0]} />
                <Bar dataKey="bookings" name="Total Bookings" fill="var(--success)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Intent Distribution Pie Chart */}
        <div className="glass-panel" style={{ padding: "var(--spacing-6)" }}>
          <h3 style={{ fontSize: "1.125rem", fontWeight: 600, marginBottom: "var(--spacing-6)" }}>Call Intent Distribution</h3>
          <div style={{ height: "300px", width: "100%", position: "relative" }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={modeData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={5}
                  dataKey="value"
                  stroke="none"
                >
                  {modeData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <RechartsTooltip contentStyle={{ backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--border)', borderRadius: 'var(--radius-md)' }} itemStyle={{ color: 'var(--text-primary)' }} />
              </PieChart>
            </ResponsiveContainer>
            
            {/* Custom Legend */}
            <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, display: "flex", justifyContent: "center", gap: "var(--spacing-3)", flexWrap: "wrap" }}>
              {modeData.map((entry, index) => (
                <div key={entry.name} style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                  <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: COLORS[index % COLORS.length] }} />
                  {entry.name}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
