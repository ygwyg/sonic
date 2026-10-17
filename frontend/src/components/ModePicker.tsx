import { MODES, type Mode } from "../lib/api";

export default function ModePicker({ value, onChange }: { value: Mode; onChange: (m: Mode) => void }) {
  return (
    <div className="segmented" role="radiogroup" aria-label="Speed">
      {MODES.map((m) => (
        <label key={m.id} className={m.id === value ? "is-on" : ""} title={m.hint}>
          <input type="radio" name="mode" value={m.id} checked={m.id === value} onChange={() => onChange(m.id)} />
          {m.label}
        </label>
      ))}
    </div>
  );
}
