import { useCallback, useRef, useState, type DragEvent, type ReactNode } from "react";
import { formatBytes } from "../services/audio";

interface Props {
  onFile: (file: File) => void;
  accept?: string;
  label?: ReactNode;
  hint?: ReactNode;
  file?: File | null;
  disabled?: boolean;
  compact?: boolean;
}

/** Drag-and-drop / click-to-browse file picker. */
export default function FileDrop({ onFile, accept, label = "Drop a file here or click to browse", hint, file, disabled, compact }: Props) {
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const onDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setOver(false);
      if (disabled) return;
      const f = e.dataTransfer.files?.[0];
      if (f) onFile(f);
    },
    [onFile, disabled]
  );

  return (
    <div
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-md border border-dashed text-center transition-colors ${
        compact ? "px-3 py-3" : "px-4 py-8"
      } ${over ? "border-accent bg-accent/10" : "border-line bg-bg/40 hover:border-ink2"} ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
      {file ? (
        <div className="num text-sm">
          <span className="text-ink">{file.name}</span>
          <span className="ml-2 text-muted">{formatBytes(file.size)}</span>
        </div>
      ) : (
        <div className="text-sm text-ink2">{label}</div>
      )}
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}
