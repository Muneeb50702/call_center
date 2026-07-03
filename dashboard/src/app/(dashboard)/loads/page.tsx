"use client";

import { useEffect, useState, useCallback } from "react";
import { Search, Plus, MapPin, Truck as TruckIcon, Pencil, Trash2 } from "lucide-react";
import { fetchApi } from "@/lib/api";
import Modal from "@/components/ui/Modal";

interface Load {
  id: string;
  origin: string;
  destination: string;
  weight_lbs: number;
  commodity: string;
  equipment_type: string;
  rate_per_mile: number;
  status: string;
  pickup_date: string;
  delivery_date: string;
}

const emptyLoad = {
  id: "", origin: "", destination: "", weight_lbs: 40000, commodity: "General Freight",
  equipment_type: "Dry Van", rate_per_mile: 2.50, status: "available",
  pickup_date: new Date().toISOString().split("T")[0],
  delivery_date: new Date(Date.now() + 86400000 * 2).toISOString().split("T")[0],
};

export default function LoadsPage() {
  const [loads, setLoads] = useState<Load[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [equipmentFilter, setEquipmentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingLoad, setEditingLoad] = useState<any>(null);
  const [formData, setFormData] = useState(emptyLoad);
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append("origin", searchQuery);
      if (equipmentFilter) params.append("equipment", equipmentFilter);
      if (statusFilter) params.append("status", statusFilter);
      const data = await fetchApi(`/loads/search?${params.toString()}`);
      setLoads(data);
    } catch (err) {
      console.error("Failed to fetch loads:", err);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, equipmentFilter, statusFilter]);

  useEffect(() => { loadData(); }, [loadData]);

  const openCreate = () => {
    setEditingLoad(null);
    setFormData({ ...emptyLoad, id: `L-${Math.random().toString(36).substring(2, 6).toUpperCase()}` });
    setModalOpen(true);
  };

  const openEdit = (load: Load) => {
    setEditingLoad(load);
    setFormData({
      id: load.id,
      origin: load.origin,
      destination: load.destination,
      weight_lbs: load.weight_lbs,
      commodity: load.commodity || "General Freight",
      equipment_type: load.equipment_type,
      rate_per_mile: load.rate_per_mile,
      status: load.status,
      pickup_date: load.pickup_date,
      delivery_date: load.delivery_date,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editingLoad) {
        // Update status (the only PATCH endpoint available)
        await fetchApi(`/loads/${editingLoad.id}/status?new_status=${formData.status}`, { method: "PATCH" });
      } else {
        // Create new load
        await fetchApi("/loads/", {
          method: "POST",
          body: JSON.stringify(formData),
        });
      }
      setModalOpen(false);
      loadData();
    } catch (err: any) {
      alert(err.message || "Failed to save load");
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
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "var(--spacing-1)" }}>Loads Management</h2>
          <p style={{ color: "var(--text-secondary)" }}>Manage freight inventory available for AI dispatching.</p>
        </div>
        <button className="btn-primary" onClick={openCreate}><Plus size={18} /> Add Load</button>
      </div>

      <div className="glass-panel" style={{ padding: "var(--spacing-4)", display: "flex", gap: "var(--spacing-4)" }}>
        <div style={{ position: "relative", flex: 1 }}>
          <Search size={18} style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input 
            type="text" className="input-field" placeholder="Search loads by origin..." 
            style={{ paddingLeft: "38px" }} value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") loadData(); }}
          />
        </div>
        <select className="input-field" style={{ width: "200px" }} value={equipmentFilter} onChange={(e) => setEquipmentFilter(e.target.value)}>
          <option value="">All Equipment</option>
          <option value="Dry Van">Dry Van</option>
          <option value="Reefer">Reefer</option>
          <option value="Flatbed">Flatbed</option>
        </select>
        <select className="input-field" style={{ width: "200px" }} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          <option value="available">Available</option>
          <option value="booked">Booked</option>
          <option value="in_transit">In Transit</option>
          <option value="delivered">Delivered</option>
        </select>
      </div>
      
      {loading ? (
        <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>Loading...</div>
      ) : loads.length === 0 ? (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)", marginBottom: "var(--spacing-4)" }}>No loads found. Create your first load to get started.</p>
          <button className="btn-primary" onClick={openCreate}><Plus size={18} /> Add Load</button>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(350px, 1fr))", gap: "var(--spacing-4)" }}>
          {loads.map((load) => (
            <div key={load.id} className="glass-panel animate-fade-in" style={{ padding: "var(--spacing-5)", display: "flex", flexDirection: "column", gap: "var(--spacing-4)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--accent-primary)" }}>{load.id}</span>
                <span className={`badge ${load.status === 'available' ? 'badge-success' : load.status === 'booked' ? 'badge-info' : 'badge-neutral'}`}>
                  {load.status.replace("_", " ").toUpperCase()}
                </span>
              </div>
              
              <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-3)" }}>
                <MapPin size={18} color="var(--text-muted)" />
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <span style={{ fontWeight: 600 }}>{load.origin}</span>
                  <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Pickup</span>
                </div>
                <div style={{ flex: 1, borderTop: "1px dashed var(--border-light)", margin: "0 var(--spacing-2)" }} />
                <div style={{ display: "flex", flexDirection: "column", textAlign: "right" }}>
                  <span style={{ fontWeight: 600 }}>{load.destination}</span>
                  <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Delivery</span>
                </div>
              </div>
              
              <div style={{ background: "var(--bg-tertiary)", padding: "var(--spacing-3)", borderRadius: "var(--radius-md)", display: "flex", justifyContent: "space-between", fontSize: "0.875rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "4px" }}><TruckIcon size={14} color="var(--text-muted)" /> {load.equipment_type}</div>
                <div>{Math.round(load.weight_lbs / 1000)}k lbs</div>
                <div style={{ fontWeight: 600, color: "var(--success)" }}>${load.rate_per_mile.toFixed(2)}/mi</div>
              </div>
              
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                <span>Dates: {load.pickup_date} – {load.delivery_date}</span>
                <button onClick={() => openEdit(load)} style={{ color: "var(--accent-primary)", fontWeight: 500, display: "flex", alignItems: "center", gap: "4px" }}>
                  <Pencil size={14} /> Edit
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create / Edit Modal */}
      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title={editingLoad ? "Edit Load" : "Add New Load"}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-4)" }}>
          <div style={fieldStyle}>
            <label style={labelStyle}>Load ID</label>
            <input type="text" className="input-field" value={formData.id} onChange={(e) => handleField("id", e.target.value)} disabled={!!editingLoad} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Equipment Type</label>
            <select className="input-field" value={formData.equipment_type} onChange={(e) => handleField("equipment_type", e.target.value)}>
              <option>Dry Van</option>
              <option>Reefer</option>
              <option>Flatbed</option>
              <option>Step Deck</option>
            </select>
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Origin (City, State)</label>
            <input type="text" className="input-field" placeholder="Chicago, IL" value={formData.origin} onChange={(e) => handleField("origin", e.target.value)} disabled={!!editingLoad} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Destination (City, State)</label>
            <input type="text" className="input-field" placeholder="Dallas, TX" value={formData.destination} onChange={(e) => handleField("destination", e.target.value)} disabled={!!editingLoad} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Weight (lbs)</label>
            <input type="number" className="input-field" value={formData.weight_lbs} onChange={(e) => handleField("weight_lbs", parseInt(e.target.value))} disabled={!!editingLoad} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Commodity</label>
            <input type="text" className="input-field" value={formData.commodity} onChange={(e) => handleField("commodity", e.target.value)} disabled={!!editingLoad} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Rate per Mile ($)</label>
            <input type="number" step="0.01" className="input-field" value={formData.rate_per_mile} onChange={(e) => handleField("rate_per_mile", parseFloat(e.target.value))} disabled={!!editingLoad} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Status</label>
            <select className="input-field" value={formData.status} onChange={(e) => handleField("status", e.target.value)}>
              <option value="available">Available</option>
              <option value="booked">Booked</option>
              <option value="in_transit">In Transit</option>
              <option value="delivered">Delivered</option>
            </select>
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Pickup Date</label>
            <input type="date" className="input-field" value={formData.pickup_date} onChange={(e) => handleField("pickup_date", e.target.value)} disabled={!!editingLoad} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>Delivery Date</label>
            <input type="date" className="input-field" value={formData.delivery_date} onChange={(e) => handleField("delivery_date", e.target.value)} disabled={!!editingLoad} />
          </div>
        </div>

        {editingLoad && (
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontStyle: "italic" }}>
            Only the status can be changed when editing. To modify other fields, create a new load.
          </p>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--spacing-3)", paddingTop: "var(--spacing-3)", borderTop: "1px solid var(--border)" }}>
          <button className="btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : editingLoad ? "Update Status" : "Create Load"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
