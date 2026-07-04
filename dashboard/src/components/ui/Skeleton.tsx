"use client";

/**
 * Skeleton loader components for premium loading states.
 * Replaces plain "Loading..." text with animated shimmer placeholders.
 */

interface SkeletonProps {
  width?: string;
  height?: string;
  borderRadius?: string;
  style?: React.CSSProperties;
}

export function Skeleton({ width = "100%", height = "1rem", borderRadius = "var(--radius-md)", style }: SkeletonProps) {
  return (
    <div
      className="skeleton-shimmer"
      style={{
        width,
        height,
        borderRadius,
        background: "var(--bg-tertiary)",
        position: "relative",
        overflow: "hidden",
        ...style,
      }}
    />
  );
}

/** Card-shaped skeleton for KPI panels */
export function SkeletonCard({ style }: { style?: React.CSSProperties }) {
  return (
    <div
      className="glass-panel"
      style={{
        padding: "var(--spacing-6)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-3)",
        ...style,
      }}
    >
      <Skeleton width="40%" height="0.875rem" />
      <Skeleton width="60%" height="2rem" />
      <Skeleton width="30%" height="0.75rem" />
    </div>
  );
}

/** Row-shaped skeleton for table rows */
export function SkeletonRow({ columns = 5, style }: { columns?: number; style?: React.CSSProperties }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: "var(--spacing-4)",
        padding: "var(--spacing-3) var(--spacing-4)",
        borderBottom: "1px solid var(--border)",
        ...style,
      }}
    >
      {Array.from({ length: columns }).map((_, i) => (
        <Skeleton key={i} height="1rem" width={i === 0 ? "80%" : "60%"} />
      ))}
    </div>
  );
}

/** Table skeleton with header + rows */
export function SkeletonTable({ rows = 5, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="glass-panel" style={{ overflow: "hidden" }}>
      {/* Header */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${columns}, 1fr)`,
          gap: "var(--spacing-4)",
          padding: "var(--spacing-3) var(--spacing-4)",
          background: "var(--bg-tertiary)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton key={i} height="0.75rem" width="70%" />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} columns={columns} />
      ))}
    </div>
  );
}

/** Grid of skeleton cards */
export function SkeletonCardGrid({ count = 4 }: { count?: number }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "var(--spacing-4)" }}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
