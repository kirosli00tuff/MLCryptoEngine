import { useEffect, useState } from "react";

import { EyeIcon, EyeOffIcon, ShieldIcon } from "../components/icons";
import Toggle from "../components/Toggle";
import { fmtBytes } from "../lib/format";
import type { ApiCredentials, Settings } from "../lib/types";
import { useAppData } from "../state/AppData";

function SectionCard({
  title,
  children,
  description,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="panel p-5">
      <h2 className="panel-title">{title}</h2>
      {description ? (
        <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">{description}</p>
      ) : null}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function SecretField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <label className="block">
      <span className="text-[11px] text-ink-dim">{label}</span>
      <span className="mt-1 flex items-center gap-1.5">
        <input
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="not set"
          autoComplete="off"
          spellCheck={false}
          className="num w-full rounded-md border border-hairline bg-panel2 px-2.5 py-1.5 text-[11.5px] text-ink placeholder:text-ink-faint"
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? `Hide ${label}` : `Show ${label}`}
          className="rounded p-1.5 text-ink-faint transition-colors hover:text-ink"
        >
          {visible ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </span>
    </label>
  );
}

export default function SettingsPage() {
  const { settings, saveSettings, repoInfo, inventory, inTauri } = useAppData();
  const [draft, setDraft] = useState<Settings | null>(null);

  useEffect(() => {
    if (settings && draft === null) {
      setDraft(JSON.parse(JSON.stringify(settings)) as Settings);
    }
  }, [settings, draft]);

  if (!draft) {
    return (
      <div className="p-8 text-[12px] text-ink-dim">
        {inTauri ? "Loading settings…" : "Settings need the desktop shell (`make desktop`)."}
      </div>
    );
  }

  const dirty = settings !== null && JSON.stringify(draft) !== JSON.stringify(settings);
  const setApi = (patch: Partial<ApiCredentials>) =>
    setDraft({ ...draft, api: { ...draft.api, ...patch } });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-5 pb-24">
      <SectionCard
        title="Repository"
        description="Where the MLCryptoEngine repo lives. Leave empty to auto-detect by walking up from the app's working directory."
      >
        <label className="block">
          <span className="text-[11px] text-ink-dim">Repository path</span>
          <input
            type="text"
            value={draft.repo_root ?? ""}
            onChange={(e) =>
              setDraft({
                ...draft,
                repo_root: e.target.value.trim() === "" ? null : e.target.value,
              })
            }
            placeholder={repoInfo?.repo_root ?? "/path/to/MLCryptoEngine"}
            spellCheck={false}
            className="num mt-1 w-full rounded-md border border-hairline bg-panel2 px-2.5 py-1.5 text-[11.5px] text-ink placeholder:text-ink-faint"
          />
        </label>
        {repoInfo ? (
          <p className="num mt-2 text-[10px] text-ink-faint">resolved: {repoInfo.repo_root}</p>
        ) : null}
      </SectionCard>

      <SectionCard title="Venues" description="Which public feeds the recorder captures when it starts.">
        <div className="divide-y divide-hairline">
          <Toggle
            checked={draft.record_kraken}
            onChange={(v) => setDraft({ ...draft, record_kraken: v })}
            label="Kraken spot"
            description="WS v2 book (depth 100) + trades — matching engine at Equinix London"
          />
          <Toggle
            checked={draft.record_coinbase}
            onChange={(v) => setDraft({ ...draft, record_coinbase: v })}
            label="Coinbase Advanced Trade"
            description="level2 + market_trades + heartbeats — engine in AWS us-east-1"
          />
        </div>
      </SectionCard>

      <SectionCard
        title="API keys"
        description="For later phases (account data, Databento market data). Stage 1 records public feeds only and never uses these."
      >
        <div className="mb-4 flex gap-2.5 rounded-md border border-amberx/25 bg-amberx/8 p-3">
          <ShieldIcon className="mt-0.5 h-4 w-4 shrink-0 text-amberx" />
          <p className="text-[10.5px] leading-relaxed text-ink-dim">
            Keys are stored locally in your OS config directory and never enter the
            repository. Use <span className="text-ink">read-only</span> keys — never grant
            trade or withdraw permission to anything this project uses.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <SecretField
            label="Kraken API key"
            value={draft.api.kraken_api_key}
            onChange={(v) => setApi({ kraken_api_key: v })}
          />
          <SecretField
            label="Kraken API secret"
            value={draft.api.kraken_api_secret}
            onChange={(v) => setApi({ kraken_api_secret: v })}
          />
          <SecretField
            label="Coinbase API key"
            value={draft.api.coinbase_api_key}
            onChange={(v) => setApi({ coinbase_api_key: v })}
          />
          <SecretField
            label="Coinbase API secret"
            value={draft.api.coinbase_api_secret}
            onChange={(v) => setApi({ coinbase_api_secret: v })}
          />
          <SecretField
            label="Databento API key"
            value={draft.api.databento_api_key}
            onChange={(v) => setApi({ databento_api_key: v })}
          />
        </div>
      </SectionCard>

      <SectionCard title="Storage" description="Read-only view of where data lives.">
        <dl className="num space-y-1.5 text-[11px]">
          <div className="flex justify-between gap-4">
            <dt className="text-ink-faint">data directory</dt>
            <dd className="truncate text-ink-dim">{repoInfo?.data_dir ?? "—"}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-ink-faint">logs directory</dt>
            <dd className="truncate text-ink-dim">{repoInfo?.logs_dir ?? "—"}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-ink-faint">raw + processed on disk</dt>
            <dd className="text-ink-dim">
              {inventory
                ? fmtBytes(inventory.raw_total_bytes + inventory.processed_total_bytes)
                : "—"}
            </dd>
          </div>
        </dl>
      </SectionCard>

      <div className="fixed bottom-0 left-52 right-0 border-t border-hairline bg-void/90 px-5 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <span className="text-[10.5px] text-ink-faint">
            {dirty ? "Unsaved changes" : "All changes saved"}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!dirty}
              onClick={() =>
                settings && setDraft(JSON.parse(JSON.stringify(settings)) as Settings)
              }
              className="rounded-md px-3 py-1.5 text-[11.5px] text-ink-dim transition-colors hover:text-ink disabled:opacity-40"
            >
              Discard
            </button>
            <button
              type="button"
              disabled={!dirty || !inTauri}
              onClick={() => void saveSettings(draft)}
              className="rounded-md bg-cortex/90 px-4 py-1.5 text-[11.5px] font-medium text-void transition-colors hover:bg-cortex disabled:cursor-not-allowed disabled:opacity-40"
            >
              Save changes
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
