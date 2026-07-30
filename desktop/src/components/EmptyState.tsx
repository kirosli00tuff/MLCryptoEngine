import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  hint: string;
  action?: ReactNode;
}

/** Designed empty state: every panel invites the next action instead of erroring. */
export default function EmptyState({ icon, title, hint, action }: EmptyStateProps) {
  return (
    <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-hairline px-6 py-8 text-center">
      <div className="text-ink-faint">{icon}</div>
      <div className="text-[12px] font-medium text-ink-dim">{title}</div>
      <div className="max-w-[320px] text-[11px] leading-relaxed text-ink-faint">{hint}</div>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
