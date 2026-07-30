import { GridIcon, NetGlyph, SlidersIcon } from "./icons";

export type Page = "dashboard" | "settings";

interface SidebarProps {
  page: Page;
  onNavigate: (page: Page) => void;
}

const NAV: { page: Page; label: string; icon: typeof GridIcon }[] = [
  { page: "dashboard", label: "Dashboard", icon: GridIcon },
  { page: "settings", label: "Settings", icon: SlidersIcon },
];

export default function Sidebar({ page, onNavigate }: SidebarProps) {
  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-hairline bg-panel">
      <div className="flex items-center gap-2.5 px-4 pb-5 pt-4">
        <NetGlyph className="h-7 w-7 text-ink-dim" />
        <div className="leading-tight">
          <div className="num text-[13px] font-semibold tracking-widest text-ink">MLCE</div>
          <div className="text-[10px] text-ink-dim">MLCryptoEngine</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1 px-2" aria-label="Primary">
        {NAV.map(({ page: target, label, icon: Icon }) => {
          const active = page === target;
          return (
            <button
              key={target}
              type="button"
              onClick={() => onNavigate(target)}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-2.5 rounded-md border-l-2 px-3 py-2 text-left text-[12.5px] transition-colors ${
                active
                  ? "border-cortex bg-panel2 text-ink"
                  : "border-transparent text-ink-dim hover:bg-panel2/60 hover:text-ink"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          );
        })}
      </nav>

      <div className="mt-auto space-y-2 px-4 pb-4">
        <div className="rounded-md border border-hairline bg-panel2/70 px-3 py-2">
          <div className="num text-[9px] font-semibold tracking-[0.16em] text-cortex">
            PHASE A
          </div>
          <div className="mt-0.5 text-[10px] leading-snug text-ink-dim">
            Data pipeline — public market data only, no trading logic.
          </div>
        </div>
        <div className="num px-1 text-[9px] text-ink-faint">v0.1.0</div>
      </div>
    </aside>
  );
}
