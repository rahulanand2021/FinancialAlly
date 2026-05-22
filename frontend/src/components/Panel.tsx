import { ReactNode } from "react";

interface PanelProps {
  title?: string;
  children?: ReactNode;
  className?: string;
  actions?: ReactNode;
}

export default function Panel({ title, children, className, actions }: PanelProps) {
  return (
    <section
      className={`bg-bg-panel border border-border-muted rounded-md flex flex-col overflow-hidden ${
        className ?? ""
      }`}
    >
      {(title || actions) && (
        <header className="flex items-center justify-between px-3 py-2 border-b border-border-muted">
          {title && (
            <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              {title}
            </h2>
          )}
          {actions}
        </header>
      )}
      <div className="flex-1 overflow-auto">{children}</div>
    </section>
  );
}
