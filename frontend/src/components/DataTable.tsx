import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T, index: number) => ReactNode;
  align?: "left" | "right";
  className?: string;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey?: (row: T, index: number) => string | number;
  maxHeight?: number;
  empty?: ReactNode;
  dense?: boolean;
}

/** Scrollable, monospace-valued table. */
export default function DataTable<T>({ columns, rows, rowKey, maxHeight = 360, empty = "No rows.", dense = false }: Props<T>) {
  const pad = dense ? "px-2 py-1" : "px-3 py-1.5";
  return (
    <div className="w-full overflow-auto rounded-md border border-line" style={{ maxHeight }}>
      <table className="w-full min-w-max border-collapse text-xs">
        <thead className="sticky top-0 z-10 bg-panel2 text-[11px] uppercase tracking-wider text-muted">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`${pad} whitespace-nowrap font-medium ${c.align === "right" ? "text-right" : "text-left"} ${c.className ?? ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className={`${pad} text-muted`}>
                {empty}
              </td>
            </tr>
          )}
          {rows.map((r, i) => (
            <tr key={rowKey ? rowKey(r, i) : i} className="border-t border-line/60 hover:bg-panel2/50">
              {columns.map((c) => (
                <td key={c.key} className={`${pad} num whitespace-nowrap ${c.align === "right" ? "text-right" : "text-left"} ${c.className ?? ""}`}>
                  {c.render(r, i)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
