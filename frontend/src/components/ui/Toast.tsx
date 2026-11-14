import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Icon } from "../icons";

type Kind = "success" | "error";
interface ToastItem { id: number; kind: Kind; message: string }
const ToastContext = createContext<{ notify: (kind: Kind, message: string) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: number) => setItems((cur) => cur.filter((t) => t.id !== id)), []);
  const notify = useCallback((kind: Kind, message: string) => {
    const id = Date.now() + Math.random();
    setItems((cur) => [...cur, { id, kind, message }]);
    setTimeout(() => dismiss(id), 5000);
  }, [dismiss]);
  const value = useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} className={`pointer-events-auto flex items-start gap-3 rounded-lg border p-3 text-sm shadow-lg ${t.kind === "success" ? "border-ok-400/40 bg-ink-850 text-ink-50" : "border-danger-500/50 bg-ink-850 text-red-200"}`}>
            <Icon name={t.kind === "success" ? "check" : "alert"} className={`mt-0.5 h-4.5 w-4.5 shrink-0 ${t.kind === "success" ? "text-ok-400" : "text-danger-400"}`} />
            <span className="flex-1">{t.message}</span>
            <button type="button" aria-label="Dismiss notification" onClick={() => dismiss(t.id)} className="text-ink-400 hover:text-ink-50"><Icon name="close" className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
