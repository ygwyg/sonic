import { MODES, type Mode } from "../lib/api";

export default function ModePicker({ value, onChange }: { value: Mode; onChange: (m: Mode) => void }) {
  const hint = MODES.find((m) => m.id === value)!.hint;
  return (
    <fieldset className="modes">
      <legend className="quiet">Speed</legend>
      <div className="segmented" role="radiogroup">
        {MODES.map((m) => (
          <label key={m.id} className={m.id === value ? "is-on" : ""}>
            <input type="radio" name="mode" value={m.id} checked={m.id === value} onChange={() => onChange(m.id)} />
            {m.label}
          </label>
        ))}
      </div>
      <p className="quiet">{hint}</p>
    </fieldset>
  );
}
