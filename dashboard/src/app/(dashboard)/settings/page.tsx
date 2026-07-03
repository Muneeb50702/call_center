"use client";

import { useEffect, useState } from "react";
import { Save, Building, Volume2, DollarSign } from "lucide-react";
import { fetchApi } from "@/lib/api";

export default function SettingsPage() {
  const [tenant, setTenant] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await fetchApi("/tenants/me");
        setTenant(data);
      } catch (err) {
        console.error("Failed to load settings:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleChange = (field: string, value: any) => {
    setTenant({ ...tenant, [field]: value });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetchApi(`/tenants/${tenant.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          company_name: tenant.company_name,
          human_transfer_number: tenant.human_transfer_number,
          voice_model: tenant.voice_model,
          llm_model: tenant.llm_model,
          greeting_script: tenant.greeting_script,
          negotiation_floor_pct: parseFloat(tenant.negotiation_floor_pct),
          max_negotiation_rounds: parseInt(tenant.max_negotiation_rounds, 10),
        }),
      });
      alert("Settings saved successfully!");
    } catch (err) {
      console.error(err);
      alert("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div style={{ padding: "2rem" }}>Loading settings...</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)", maxWidth: "800px" }}>
      
      <div>
        <h2 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "var(--spacing-1)" }}>Settings</h2>
        <p style={{ color: "var(--text-secondary)" }}>Configure AI behavior, tenant profile, and integrations.</p>
      </div>

      {/* Profile Section */}
      <div className="glass-panel" style={{ padding: "var(--spacing-6)", display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>
        <h3 style={{ fontSize: "1.125rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "8px", borderBottom: "1px solid var(--border)", paddingBottom: "var(--spacing-3)" }}>
          <Building size={18} color="var(--accent-primary)" /> Company Profile
        </h3>
        
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-4)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 }}>Company Name</label>
            <input 
              type="text" 
              className="input-field" 
              value={tenant?.company_name || ""} 
              onChange={(e) => handleChange("company_name", e.target.value)} 
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 }}>Human Transfer Number</label>
            <input 
              type="text" 
              className="input-field" 
              value={tenant?.human_transfer_number || ""} 
              onChange={(e) => handleChange("human_transfer_number", e.target.value)} 
            />
          </div>
        </div>
      </div>

      {/* AI Config Section */}
      <div className="glass-panel" style={{ padding: "var(--spacing-6)", display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>
        <h3 style={{ fontSize: "1.125rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "8px", borderBottom: "1px solid var(--border)", paddingBottom: "var(--spacing-3)" }}>
          <Volume2 size={18} color="var(--accent-primary)" /> AI Configuration
        </h3>
        
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-4)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 }}>Voice Model</label>
            <select className="input-field" value={tenant?.voice_model || ""} onChange={(e) => handleChange("voice_model", e.target.value)}>
              <option value="aura-orion-en">Orion (Male, Authoritative)</option>
              <option value="aura-asteria-en">Asteria (Female, Professional)</option>
              <option value="aura-luna-en">Luna (Female, Friendly)</option>
            </select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 }}>LLM Engine</label>
            <select className="input-field" value={tenant?.llm_model || ""} onChange={(e) => handleChange("llm_model", e.target.value)}>
              <option value="llama-3.1-8b-instant">Llama 3.1 8B (Fastest)</option>
              <option value="llama-3.3-70b-versatile">Llama 3.3 70B (High Accuracy)</option>
            </select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)", gridColumn: "span 2" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 }}>Greeting Script</label>
            <textarea 
              className="input-field" 
              style={{ minHeight: "80px", resize: "vertical" }} 
              value={tenant?.greeting_script || ""} 
              onChange={(e) => handleChange("greeting_script", e.target.value)} 
            />
          </div>
        </div>
      </div>

      {/* Negotiation Section */}
      <div className="glass-panel" style={{ padding: "var(--spacing-6)", display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>
        <h3 style={{ fontSize: "1.125rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "8px", borderBottom: "1px solid var(--border)", paddingBottom: "var(--spacing-3)" }}>
          <DollarSign size={18} color="var(--accent-primary)" /> Negotiation Rules
        </h3>
        
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-4)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 }}>Negotiation Floor (%)</label>
            <input 
              type="number" 
              className="input-field" 
              value={tenant?.negotiation_floor_pct ? tenant.negotiation_floor_pct * 100 : 90} 
              onChange={(e) => handleChange("negotiation_floor_pct", parseFloat(e.target.value) / 100)} 
              min="50" max="100" 
            />
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Agent won&apos;t accept offers below this % of target rate.</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 500 }}>Max Negotiation Rounds</label>
            <input 
              type="number" 
              className="input-field" 
              value={tenant?.max_negotiation_rounds || 3} 
              onChange={(e) => handleChange("max_negotiation_rounds", e.target.value)} 
              min="1" max="10" 
            />
          </div>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button className="btn-primary" style={{ minWidth: "150px" }} onClick={handleSave} disabled={saving}>
          <Save size={18} /> {saving ? "Saving..." : "Save Settings"}
        </button>
      </div>

    </div>
  );
}
