"use client";

import { useEffect, useState } from "react";
import { Building, Plus, Shield, MoreVertical, Copy, Check } from "lucide-react";
import { fetchApi } from "@/lib/api";
import Modal from "@/components/ui/Modal";

const emptyTenant = {
  id: "", company_name: "", greeting_script: "", sip_numbers: [],
  human_transfer_number: "", voice_model: "aura-orion-en",
  negotiation_floor_pct: 0.90, max_negotiation_rounds: 3,
  max_concurrent_calls: 20, llm_model: "llama-3.1-8b-instant",
};

export default function SuperAdminPage() {
  const [tenants, setTenants] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [formData, setFormData] = useState(emptyTenant);
  const [saving, setSaving] = useState(false);

  // Onboard result state (to show API key)
  const [onboardResult, setOnboardResult] = useState<any>(null);
  const [copied, setCopied] = useState(false);

  const loadData = async () => {
    try {
      const data = await fetchApi("/tenants");
      setTenants(data);
    } catch (err) {
      console.error("Failed to load tenants:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const openCreate = () => {
    setFormData({ ...emptyTenant });
    setOnboardResult(null);
    setModalOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await fetchApi("/tenants/onboard", {
        method: "POST",
        body: JSON.stringify(formData),
      });
      setOnboardResult(result);
      setLoading(true);
      loadData();
    } catch (err: any) {
      alert(err.message || "Failed to onboard tenant");
    } finally {
      setSaving(false);
    }
  };

  const handleField = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const copyKey = () => {
    navigator.clipboard.writeText(onboardResult?.api_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const fieldStyle = { display: "flex", flexDirection: "column" as const, gap: "var(--spacing-2)" };
  const labelStyle = { fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "var(--spacing-1)", display: "flex", alignItems: "center", gap: "8px" }}>
            <Shield size={24} color="var(--accent-primary)" /> Super Admin
          </h2>
          <p style={{ color: "var(--text-secondary)" }}>Manage tenants, API keys, and global system configurations.</p>
        </div>
        <button className="btn-primary" onClick={openCreate}><Plus size={18} /> Onboard Tenant</button>
      </div>

      {/* System Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--spacing-4)" }}>
        <div className="glass-panel" style={{ padding: "var(--spacing-4)", display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
          <span style={{ color: "var(--text-secondary)", fontSize: "0.875rem", fontWeight: 500 }}>Active Tenants</span>
          <h3 style={{ fontSize: "2rem", fontWeight: 700 }}>{loading ? "-" : tenants.length}</h3>
        </div>
        <div className="glass-panel" style={{ padding: "var(--spacing-4)", display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
          <span style={{ color: "var(--text-secondary)", fontSize: "0.875rem", fontWeight: 500 }}>Total Concurrent Calls (System-wide)</span>
          <h3 style={{ fontSize: "2rem", fontWeight: 700, display: "flex", alignItems: "baseline", gap: "8px" }}>
            - <span style={{ fontSize: "1rem", color: "var(--text-muted)", fontWeight: 500 }}>/ {tenants.reduce((sum, t) => sum + (t.max_concurrent_calls || 0), 0)} limit</span>
          </h3>
        </div>
        <div className="glass-panel" style={{ padding: "var(--spacing-4)", display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
          <span style={{ color: "var(--text-secondary)", fontSize: "0.875rem", fontWeight: 500 }}>Global API Latency (Avg)</span>
          <h3 style={{ fontSize: "2rem", fontWeight: 700, color: "var(--success)" }}>-</h3>
        </div>
      </div>

      <div className="glass-panel">
        <div style={{ padding: "var(--spacing-4)", borderBottom: "1px solid var(--border)" }}>
          <h3 style={{ fontSize: "1.125rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "8px" }}>
            <Building size={18} color="var(--text-secondary)" /> Tenant Directory
          </h3>
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ background: "var(--bg-tertiary)", borderBottom: "1px solid var(--border)" }}>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Tenant ID</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Company Name</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>LLM Model</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Max Concurrent</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Status</th>
              <th style={{ padding: "var(--spacing-3) var(--spacing-4)", color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.875rem" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>Loading tenants...</td></tr>
            ) : tenants.length === 0 ? (
              <tr><td colSpan={6} style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>No tenants. Click &quot;Onboard Tenant&quot; to add the first.</td></tr>
            ) : (
              tenants.map((tenant) => (
                <tr key={tenant.id} style={{ borderBottom: "1px solid var(--border)", transition: "background var(--transition-fast)" }} className="hover:bg-bg-tertiary">
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)", fontFamily: "var(--font-mono)", fontSize: "0.875rem", color: "var(--text-muted)" }}>{tenant.id}</td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)", fontWeight: 600 }}>{tenant.company_name}</td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)", fontSize: "0.875rem" }}>{tenant.llm_model}</td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)" }}>{tenant.max_concurrent_calls}</td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)" }}>
                    <span className={`badge ${tenant.is_active ? 'badge-success' : 'badge-danger'}`}>
                      {tenant.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={{ padding: "var(--spacing-3) var(--spacing-4)" }}>
                    <button className="btn-secondary" style={{ padding: "4px 8px" }} title="Manage Tenant"><MoreVertical size={14} /></button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Onboard Tenant Modal */}
      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title={onboardResult ? "Tenant Onboarded!" : "Onboard New Tenant"} width="600px">
        {onboardResult ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-4)" }}>
            <div style={{ background: "var(--success-bg)", border: "1px solid var(--success)", borderRadius: "var(--radius-md)", padding: "var(--spacing-4)" }}>
              <p style={{ color: "var(--success)", fontWeight: 600, marginBottom: "var(--spacing-2)" }}>✅ Tenant "{onboardResult.tenant.company_name}" created successfully!</p>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Copy the API key below — it will <strong>only be shown once</strong>.</p>
            </div>
            <div style={fieldStyle}>
              <label style={labelStyle}>API Key (Copy & save securely)</label>
              <div style={{ display: "flex", gap: "var(--spacing-2)" }}>
                <input type="text" className="input-field" readOnly value={onboardResult.api_key} style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem" }} />
                <button className="btn-primary" onClick={copyKey} style={{ minWidth: "90px" }}>
                  {copied ? <><Check size={16} /> Copied!</> : <><Copy size={16} /> Copy</>}
                </button>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "var(--spacing-3)", borderTop: "1px solid var(--border)" }}>
              <button className="btn-primary" onClick={() => setModalOpen(false)}>Done</button>
            </div>
          </div>
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-4)" }}>
              <div style={fieldStyle}>
                <label style={labelStyle}>Tenant ID (slug) *</label>
                <input type="text" className="input-field" placeholder="abc-logistics" value={formData.id} onChange={(e) => handleField("id", e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))} />
              </div>
              <div style={fieldStyle}>
                <label style={labelStyle}>Company Name *</label>
                <input type="text" className="input-field" placeholder="ABC Logistics" value={formData.company_name} onChange={(e) => handleField("company_name", e.target.value)} />
              </div>
              <div style={fieldStyle}>
                <label style={labelStyle}>Human Transfer Number</label>
                <input type="tel" className="input-field" placeholder="+1 (555) 999-9999" value={formData.human_transfer_number} onChange={(e) => handleField("human_transfer_number", e.target.value)} />
              </div>
              <div style={fieldStyle}>
                <label style={labelStyle}>Max Concurrent Calls</label>
                <input type="number" className="input-field" value={formData.max_concurrent_calls} onChange={(e) => handleField("max_concurrent_calls", parseInt(e.target.value))} min={1} max={100} />
              </div>
              <div style={fieldStyle}>
                <label style={labelStyle}>Voice Model</label>
                <select className="input-field" value={formData.voice_model} onChange={(e) => handleField("voice_model", e.target.value)}>
                  <option value="aura-orion-en">Orion (Male)</option>
                  <option value="aura-asteria-en">Asteria (Female)</option>
                  <option value="aura-luna-en">Luna (Female)</option>
                </select>
              </div>
              <div style={fieldStyle}>
                <label style={labelStyle}>LLM Model</label>
                <select className="input-field" value={formData.llm_model} onChange={(e) => handleField("llm_model", e.target.value)}>
                  <option value="llama-3.1-8b-instant">Llama 3.1 8B (Fastest)</option>
                  <option value="llama-3.3-70b-versatile">Llama 3.3 70B (High Accuracy)</option>
                </select>
              </div>
              <div style={{ ...fieldStyle, gridColumn: "span 2" }}>
                <label style={labelStyle}>Greeting Script</label>
                <textarea className="input-field" style={{ minHeight: "60px", resize: "vertical" }} placeholder="Thanks for calling ABC Logistics. I am Nexus, your AI dispatcher..."
                  value={formData.greeting_script} onChange={(e) => handleField("greeting_script", e.target.value)} />
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--spacing-3)", paddingTop: "var(--spacing-3)", borderTop: "1px solid var(--border)" }}>
              <button className="btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
              <button className="btn-primary" onClick={handleSave} disabled={saving || !formData.id || !formData.company_name}>
                {saving ? "Onboarding..." : "Onboard Tenant"}
              </button>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}
