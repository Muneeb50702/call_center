"use client";

import { createContext, useContext, useState, useCallback, useRef, useEffect } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from "lucide-react";

/* ── Types ── */
type ToastType = "success" | "error" | "warning" | "info";

interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
}

interface ToastContextType {
  addToast: (toast: Omit<Toast, "id">) => void;
  removeToast: (id: string) => void;
}

/* ── Context ── */
const ToastContext = createContext<ToastContextType | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

/* ── Icons ── */
const icons: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const colors: Record<ToastType, { bg: string; border: string; icon: string }> = {
  success: { bg: "rgba(16, 185, 129, 0.12)", border: "rgba(16, 185, 129, 0.3)", icon: "var(--success)" },
  error: { bg: "rgba(239, 68, 68, 0.12)", border: "rgba(239, 68, 68, 0.3)", icon: "var(--danger)" },
  warning: { bg: "rgba(245, 158, 11, 0.12)", border: "rgba(245, 158, 11, 0.3)", icon: "var(--warning)" },
  info: { bg: "rgba(59, 130, 246, 0.12)", border: "rgba(59, 130, 246, 0.3)", icon: "var(--accent-primary)" },
};

/* ── Single Toast ── */
function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const [exiting, setExiting] = useState(false);
  const duration = toast.duration ?? 4000;
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    timerRef.current = setTimeout(() => {
      setExiting(true);
      setTimeout(() => onRemove(toast.id), 300);
    }, duration);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [toast.id, duration, onRemove]);

  const handleClose = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setExiting(true);
    setTimeout(() => onRemove(toast.id), 300);
  };

  const Icon = icons[toast.type];
  const color = colors[toast.type];

  return (
    <div
      className={exiting ? "toast-exit" : "toast-enter"}
      style={{
        background: color.bg,
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: `1px solid ${color.border}`,
        borderRadius: "var(--radius-lg)",
        padding: "var(--spacing-3) var(--spacing-4)",
        display: "flex",
        alignItems: "flex-start",
        gap: "var(--spacing-3)",
        minWidth: "320px",
        maxWidth: "420px",
        boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <Icon size={20} color={color.icon} style={{ flexShrink: 0, marginTop: "2px" }} />
      <div style={{ flex: 1 }}>
        <p style={{ fontWeight: 600, fontSize: "0.9375rem", color: "var(--text-primary)" }}>{toast.title}</p>
        {toast.message && (
          <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "2px", lineHeight: 1.4 }}>
            {toast.message}
          </p>
        )}
      </div>
      <button onClick={handleClose} style={{ color: "var(--text-muted)", padding: "2px", flexShrink: 0 }}>
        <X size={16} />
      </button>
      {/* Progress bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          height: "3px",
          background: color.icon,
          borderRadius: "0 0 var(--radius-lg) var(--radius-lg)",
          animation: `toastProgress ${duration}ms linear forwards`,
        }}
      />
    </div>
  );
}

/* ── Provider ── */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((t: Omit<Toast, "id">) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    setToasts((prev) => [...prev, { ...t, id }]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast, removeToast }}>
      {children}
      {/* Toast Container */}
      <div
        style={{
          position: "fixed",
          top: "var(--spacing-6)",
          right: "var(--spacing-6)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--spacing-3)",
          zIndex: 9999,
          pointerEvents: "none",
        }}
      >
        {toasts.map((toast) => (
          <div key={toast.id} style={{ pointerEvents: "auto" }}>
            <ToastItem toast={toast} onRemove={removeToast} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
