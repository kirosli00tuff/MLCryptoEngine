import { useAppData } from "../state/AppData";
import { XIcon } from "./icons";

export default function Toasts() {
  const { toasts, dismissToast } = useAppData();
  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-72 flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="status"
          className={`pointer-events-auto flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5 text-[12px] shadow-lg backdrop-blur ${
            toast.kind === "success"
              ? "border-bid/30 bg-panel/95 text-ink"
              : "border-ask/40 bg-panel/95 text-ink"
          }`}
        >
          <div className="flex items-start gap-2">
            <span
              className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${
                toast.kind === "success" ? "bg-bid" : "bg-ask"
              }`}
            />
            <span className="leading-snug">{toast.text}</span>
          </div>
          <button
            type="button"
            aria-label="Dismiss notification"
            onClick={() => dismissToast(toast.id)}
            className="text-ink-faint transition-colors hover:text-ink"
          >
            <XIcon />
          </button>
        </div>
      ))}
    </div>
  );
}
