import React from "react";
import { etiTheme } from "../../eti/theme";

export function Card({ title, right, children, style }) {
  return (
    <section
      style={{
        background: `linear-gradient(180deg, ${etiTheme.colors.card}, rgba(18, 35, 58, 0.72))`,
        border: `1px solid ${etiTheme.colors.borderSoft}`,
        borderRadius: etiTheme.radius.xl,
        boxShadow: etiTheme.shadow.card,
        overflow: "hidden",
        ...style,
      }}
    >
      {(title || right) && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            padding: "14px 16px",
            borderBottom: `1px solid ${etiTheme.colors.borderSoft}`,
          }}
        >
          <div style={{ color: etiTheme.colors.text, fontWeight: 800, fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase" }}>
            {title}
          </div>
          <div>{right}</div>
        </div>
      )}
      <div style={{ padding: "16px" }}>{children}</div>
    </section>
  );
}

export function Button({ variant = "secondary", size = "md", leftIcon, children, onClick, disabled, style, title }) {
  const v = variant;
  const sizes = {
    sm: { pad: "8px 12px", fontSize: 12, radius: 10 },
    md: { pad: "10px 14px", fontSize: 13, radius: 12 },
  };
  const s = sizes[size] || sizes.md;
  const base = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderRadius: s.radius,
    padding: s.pad,
    fontWeight: 800,
    fontSize: s.fontSize,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    cursor: disabled ? "not-allowed" : "pointer",
    userSelect: "none",
    opacity: disabled ? 0.5 : 1,
    transition: "transform 0.08s ease, filter 0.15s ease, border-color 0.15s ease",
  };
  const variants = {
    primary: {
      background: `linear-gradient(135deg, ${etiTheme.colors.blue}, #1f4ed8)`,
      border: `1px solid rgba(47, 122, 248, 0.55)`,
      color: "#fff",
      boxShadow: etiTheme.shadow.glow,
    },
    secondary: {
      background: "rgba(15, 27, 45, 0.75)",
      border: `1px solid ${etiTheme.colors.border}`,
      color: etiTheme.colors.text,
    },
    ghost: {
      background: "transparent",
      border: `1px solid ${etiTheme.colors.borderSoft}`,
      color: etiTheme.colors.text2,
    },
    danger: {
      background: "rgba(255, 77, 79, 0.1)",
      border: "1px solid rgba(255, 77, 79, 0.35)",
      color: etiTheme.colors.critical,
    },
  };
  const st = { ...base, ...(variants[v] || variants.secondary), ...style };

  return (
    <button
      type="button"
      title={title}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={st}
      onMouseDown={(e) => {
        if (disabled) return;
        e.currentTarget.style.transform = "translateY(1px)";
      }}
      onMouseUp={(e) => {
        e.currentTarget.style.transform = "translateY(0px)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0px)";
      }}
    >
      {leftIcon}
      {children}
    </button>
  );
}

export function Pill({ label, color = "blue" }) {
  const map = {
    blue: { bg: "rgba(47, 122, 248, 0.14)", border: "rgba(47, 122, 248, 0.3)", text: etiTheme.colors.blue },
    cyan: { bg: "rgba(33, 212, 253, 0.12)", border: "rgba(33, 212, 253, 0.28)", text: etiTheme.colors.cyan },
    success: { bg: "rgba(47, 208, 122, 0.12)", border: "rgba(47, 208, 122, 0.28)", text: etiTheme.colors.success },
    warn: { bg: "rgba(246, 195, 67, 0.12)", border: "rgba(246, 195, 67, 0.28)", text: etiTheme.colors.warn },
    critical: { bg: "rgba(255, 77, 79, 0.12)", border: "rgba(255, 77, 79, 0.28)", text: etiTheme.colors.critical },
    neutral: { bg: "rgba(159, 176, 199, 0.10)", border: "rgba(159, 176, 199, 0.20)", text: etiTheme.colors.text2 },
  };
  const s = map[color] || map.neutral;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px 10px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 800,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        background: s.bg,
        border: `1px solid ${s.border}`,
        color: s.text,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

export function Segmented({ value, options, onChange }) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: 4,
        borderRadius: 12,
        border: `1px solid ${etiTheme.colors.borderSoft}`,
        background: "rgba(0,0,0,0.18)",
      }}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            style={{
              padding: "8px 10px",
              borderRadius: 10,
              border: `1px solid ${active ? etiTheme.colors.border : "transparent"}`,
              background: active ? "rgba(47, 122, 248, 0.12)" : "transparent",
              color: active ? etiTheme.colors.text : etiTheme.colors.text2,
              fontSize: 12,
              fontWeight: 800,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function CheckboxPill({ checked, label, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 10px",
        borderRadius: 12,
        border: `1px solid ${checked ? etiTheme.colors.border : etiTheme.colors.borderSoft}`,
        background: checked ? "rgba(47, 122, 248, 0.10)" : "rgba(0,0,0,0.10)",
        color: checked ? etiTheme.colors.text : etiTheme.colors.text2,
        fontSize: 12,
        fontWeight: 800,
        letterSpacing: "0.06em",
        cursor: "pointer",
      }}
    >
      <span
        style={{
          width: 14,
          height: 14,
          borderRadius: 4,
          border: `1px solid ${checked ? etiTheme.colors.blue : etiTheme.colors.borderSoft}`,
          background: checked ? etiTheme.colors.blue : "transparent",
          boxShadow: checked ? etiTheme.shadow.glow : "none",
        }}
      />
      {label}
    </button>
  );
}

