"use client";

import { useEffect, useState } from "react";
import { Search, Plus } from "lucide-react";
import { fetchApi } from "@/lib/api";
import Modal from "@/components/ui/Modal";
import { SkeletonTable } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

interface Rate {
  lane_id: string;
  per_mile: number;
  flat: number;
  fuel_surcharge: number;
  miles: number;
}

const emptyRate = { lane_id: "", per_mile: 2.50, flat: 0, fuel_surcharge: 0.35, miles: 0 };

export default function RatesPage() {
  const [rates, setRates] = useState<Rate[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [formData, setFormData] = useState(emptyRate);
  const [saving, setSaving] = useState(false);
  const { addToast } = useToast();

  const loadData = async () => {
    try {
      const data = await fetchApi("/rates/");
      setRates(data);
    } catch (err) {
      console.error("Failed to fetch rates:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const filteredRates = rates.filter(r =>
    r.lane_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const openCreate = () => {
    setFormData({ ...emptyRate });
    setModalOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const params = new URLSearchParams({
        lane_id: formData.lane_id,
        per_mile: formData.per_mile.toString(),
        flat: formData.flat.toString(),
        fuel_surcharge: formData.fuel_surcharge.toString(),
        miles: formData.miles.toString(),
      });
      await fetchApi(`/rates/?${params.toString()}`, { method: "POST" });
      setModalOpen(false);
      setLoading(true);
      loadData();
      addToast({ type: "success", title: "Rate created", message: `Lane ${formData.lane_id} rate saved.` });
    } catch (err: any) {
      addToast({ type: "error", title: "Failed to create rate", message: err.message || "Something went wrong" });
    } finally {
      setSaving(false);
    }
  };

  const handleField = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const fieldStyle = { display: "flex", flexDirection: "column" as const, gap: "var(--spacing-2)" };
  const labelStyle = { fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "var(--spacing-1)" }}>Rate Cards</h2>
          <p style={{ color: "var(--text-secondary)" }}>Manage lane-based pricing guidelines for the AI dispatcher.</p>
        </div>
        <button className="btn-primary" onClick={openCreate}><Plus size={18} /> New Rate</button>
      </div>

      <div className="glass-panel" style={{ padding: "var(--spacing-4)", display: "flex", gap: "var(--spacing-4)" }}>
        <div style={{ position: "relative", flex: 1 }}>
          <Search size={18} style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input type="text" className="input-field" placeholder="Search by lane ID (e.g. IL-TX)..."
            style={{ paddingLeft: "38px" }} value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
        </div>
      </div>

      <div className="glass-panel">
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ background: "var(--bg-tertiary)", borderBottom: "1px solid var(--border)" }}>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Lane ID</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Base Rate (mi)</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>FSC (mi)</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Flat Fee</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Target Total / mi</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Est. Miles</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>Loading rates...</td></tr>
            ) : filteredRates.length === 0 ? (
              <tr><td colSpan={6} style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>No rates found. Click &quot;New Rate&quot; to add one.</td></tr>
            ) : (
              filteredRates.map((rate) => {
                const targetTotal = rate.per_mile + rate.fuel_surcharge;
                return (
                  <tr key={rate.lane_id} style={{ borderBottom: "1px solid var(--border)", transition: "background var(--transition-fast)" }} className="hover:bg-bg-tertiary">
                    <td style={{ padding: "var(--spacing-3) var(--spacing-4)", fontFamily: "var(--font-mono)", fontSize: "0.875rem", fontWeight: 600, color: "var(--accent-primary)" }}>{rate.lane_id}</td>
                    <td style={{ padding: "var(--spacing-3) var(--spacing-4)" }}>${rate.per_mile.toFixed(2)}</td>
                    <td style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)" }}>${rate.fuel_surcharge.toFixed(2)}</td>
                    <td style={{ padding: "var(--spacing-3) var(--spacing-4)" }}>${rate.flat.toFixed(2)}</td>
                    <td style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--success)", fontWeight: 600 }}>${targetTotal.toFixed(2)}</td>
                    <td style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)" }}>{rate.miles || '-'}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Create Rate Modal */}
      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title="Add New Rate">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-4)" }}>
          <div style={{ ...fieldStyle, gridColumn: "span 2" }}>
            <label style={labelStyle}>Lane ID *</label>
            <input type="text" className="input-field" placeholder="IL-TX (OriginState-DestState)" value={formData.lane_id} onChange={(e) => handleField("lane_id", e.target.value.toUpperCase())} />
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Format: OriginState-DestState (e.g., IL-TX, CA-AZ). If lane already exists, the rate will be updated.</span>
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Rate per Mile ($) *</label>
            <input type="number" step="0.01" className="input-field" value={formData.per_mile} onChange={(e) => handleField("per_mile", parseFloat(e.target.value))} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Fuel Surcharge per Mile ($)</label>
            <input type="number" step="0.01" className="input-field" value={formData.fuel_surcharge} onChange={(e) => handleField("fuel_surcharge", parseFloat(e.target.value))} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Flat Rate ($)</label>
            <input type="number" step="0.01" className="input-field" value={formData.flat} onChange={(e) => handleField("flat", parseFloat(e.target.value))} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Estimated Miles</label>
            <input type="number" className="input-field" value={formData.miles} onChange={(e) => handleField("miles", parseInt(e.target.value))} />
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--spacing-3)", paddingTop: "var(--spacing-3)", borderTop: "1px solid var(--border)" }}>
          <button className="btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving || !formData.lane_id}>
            {saving ? "Saving..." : "Create Rate"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
