interface CompactInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

/** Single-line labeled input with dark theme styling. */
export function CompactInput({
  label,
  value,
  onChange,
  placeholder,
  className,
}: CompactInputProps) {
  return (
    <label className={`flex items-center gap-2 ${className ?? ""}`}>
      <span
        className="shrink-0 text-[11px]"
        style={{ color: "var(--color-text-4)" }}
      >
        {label}
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="focus-ring min-w-0 flex-1 rounded-md px-2 py-1 text-xs outline-none"
        style={{
          background:
            "linear-gradient(180deg, oklch(0.985 0.004 285 / 0.82), oklch(0.968 0.005 285 / 0.75))",
          border: "1px solid var(--color-hairline-soft)",
          color: "var(--color-text)",
          boxShadow: "inset 0 1px 0 oklch(0.35 0.02 265 / 0.04)",
        }}
      />
    </label>
  );
}
