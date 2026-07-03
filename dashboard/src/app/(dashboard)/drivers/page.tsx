"use client";

import { useEffect, useState } from "react";
import { Search, Plus, Mail, Phone, FileText, Pencil } from "lucide-react";
import { fetchApi } from "@/lib/api";
import Modal from "@/components/ui/Modal";

interface Driver {
  id: string;
  name: string;
  mc_number: string;
  equipment: string;
  hos_status: string;
  phone: string;
  email: string;
  dot_number: string;
  insurance_expiry: string | null;
  is_active: boolean;
}

const emptyDriver = {
  name: "", mc_number: "", equipment: "Dry Van", hos_status: "available",
  phone: "", email: "", dot_number: "", insurance_expiry: "",
};

export default function DriversPage() {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [formData, setFormData] = useState(emptyDriver);
  const [saving, setSaving] = useState(false);

  const loadData = async () => {
    try {
      const data = await fetchApi("/drivers/");
      setDrivers(data);
    } catch (err) {
      console.error("Failed to fetch drivers:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const filteredDrivers = drivers.filter(d =>
    d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.mc_number.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const openCreate = () => {
    setFormData({ ...emptyDriver });
    setModalOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetchApi("/drivers/", {
        method: "POST",
        body: JSON.stringify({
          ...formData,
          insurance_expiry: formData.insurance_expiry || null,
        }),
      });
      setModalOpen(false);
      setLoading(true);
      loadData();
    } catch (err: any) {
      alert(err.message || "Failed to create driver");
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
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "var(--spacing-1)" }}>Driver Profiles</h2>
          <p style={{ color: "var(--text-secondary)" }}>Manage registered carriers and their contact information.</p>
        </div>
        <button className="btn-primary" onClick={openCreate}><Plus size={18} /> Add Driver</button>
      </div>

      <div className="glass-panel" style={{ padding: "var(--spacing-4)", display: "flex", gap: "var(--spacing-4)" }}>
        <div style={{ position: "relative", flex: 1 }}>
          <Search size={18} style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input type="text" className="input-field" placeholder="Search by name or MC number..."
            style={{ paddingLeft: "38px" }} value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
        </div>
      </div>

      {loading ? (
        <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>Loading drivers...</div>
      ) : filteredDrivers.length === 0 ? (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)", marginBottom: "var(--spacing-4)" }}>No drivers found. Register your first driver.</p>
          <button className="btn-primary" onClick={openCreate}><Plus size={18} /> Add Driver</button>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "var(--spacing-4)" }}>
          {filteredDrivers.map((driver) => (
            <div key={driver.id} className="glass-panel animate-fade-in" style={{ padding: "var(--spacing-5)", display: "flex", flexDirection: "column", gap: "var(--spacing-4)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <h3 style={{ fontSize: "1.125rem", fontWeight: 600 }}>{driver.name}</h3>
                  <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)", fontSize: "0.875rem" }}>{driver.mc_number}</span>
                </div>
                <span className={`badge ${driver.hos_status === 'available' ? 'badge-success' : driver.hos_status === 'on_duty' || driver.hos_status === 'driving' ? 'badge-info' : 'badge-neutral'}`}>
                  {driver.hos_status.replace(/_/g, " ").toUpperCase()}
                </span>
              </div>

              <div style={{ display: "flex", gap: "var(--spacing-2)", marginTop: "var(--spacing-2)" }}>
                <button className="btn-secondary" style={{ flex: 1 }}><Phone size={16} /> {driver.phone || "No Phone"}</button>
                <button className="btn-secondary" style={{ flex: 1 }}><Mail size={16} /> Email</button>
              </div>

              <div style={{ background: "var(--bg-tertiary)", padding: "var(--spacing-3)", borderRadius: "var(--radius-md)", display: "flex", justifyContent: "space-between", fontSize: "0.875rem" }}>
                <div style={{ color: "var(--text-secondary)" }}>Equipment:</div>
                <div style={{ fontWeight: 500 }}>{driver.equipment}</div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                <span>DOT: {driver.dot_number || "N/A"}</span>
                <button style={{ color: "var(--accent-primary)", display: "flex", alignItems: "center", gap: "4px" }}><FileText size={14} /> Docs</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Driver Modal */}
      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title="Register New Driver">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-4)" }}>
          <div style={fieldStyle}>
            <label style={labelStyle}>Driver Name *</label>
            <input type="text" className="input-field" placeholder="John Smith" value={formData.name} onChange={(e) => handleField("name", e.target.value)} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>MC Number *</label>
            <input type="text" className="input-field" placeholder="MC123456" value={formData.mc_number} onChange={(e) => handleField("mc_number", e.target.value)} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Equipment Type *</label>
            <select className="input-field" value={formData.equipment} onChange={(e) => handleField("equipment", e.target.value)}>
              <option>Dry Van</option>
              <option>Reefer</option>
              <option>Flatbed</option>
              <option>Step Deck</option>
              <option>Tanker</option>
            </select>
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>HOS Status</label>
            <select className="input-field" value={formData.hos_status} onChange={(e) => handleField("hos_status", e.target.value)}>
              <option value="available">Available</option>
              <option value="on_duty">On Duty</option>
              <option value="driving">Driving</option>
              <option value="off_duty">Off Duty</option>
              <option value="sleeper_berth">Sleeper Berth</option>
            </select>
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Phone Number</label>
            <input type="tel" className="input-field" placeholder="+1 (555) 123-4567" value={formData.phone} onChange={(e) => handleField("phone", e.target.value)} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Email</label>
            <input type="email" className="input-field" placeholder="john@carrier.com" value={formData.email} onChange={(e) => handleField("email", e.target.value)} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>DOT Number</label>
            <input type="text" className="input-field" placeholder="DOT-123456" value={formData.dot_number} onChange={(e) => handleField("dot_number", e.target.value)} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Insurance Expiry</label>
            <input type="date" className="input-field" value={formData.insurance_expiry} onChange={(e) => handleField("insurance_expiry", e.target.value)} />
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--spacing-3)", paddingTop: "var(--spacing-3)", borderTop: "1px solid var(--border)" }}>
          <button className="btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving || !formData.name || !formData.mc_number}>
            {saving ? "Registering..." : "Register Driver"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
