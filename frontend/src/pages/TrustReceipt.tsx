import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { useToast } from "../components/ui/Toast";
import { ApiError } from "../api/client";
import { listExperiments } from "../api/experiments";
import {
  generateReceipt, getReceipt, getReproducibility, listReceipts, verifyReceipt,
  type ReceiptSummary, type Reproducibility, type TrustReceipt,
} from "../api/trust";

const STATUS_TONE: Record<string, "live" | "soon" | "info" | "warn"> = {
  reproducible: "live", partially_reproducible: "info", not_reproducible: "warn", verification_failed: "warn",
};

export default function TrustReceiptPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { notify } = useToast();
  const [experiments, setExperiments] = useState<{ id: string; name: string; status: string }[]>([]);
  const [expId, setExpId] = useState("");
  const [receipt, setReceipt] = useState<TrustReceipt | null>(null);
  const [receipts, setReceipts] = useState<ReceiptSummary[]>([]);
  const [repro, setRepro] = useState<Reproducibility | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!projectId) return;
    try {
      const [exps, recs] = await Promise.all([
        listExperiments(projectId, signal).catch(() => []),
        listReceipts(projectId).catch(() => ({ receipts: [] })),
      ]);
      if (signal?.aborted) return;
      setExperiments(exps.filter((e: any) => e.status === "completed"));
      setReceipts(recs.receipts);
      setStatus("ready");
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load receipts.");
      setStatus("error");
    }
  }, [projectId]);

  useEffect(() => { const c = new AbortController(); void load(c.signal); return () => c.abort(); }, [load]);

  const openExperiment = async (id: string) => {
    if (!projectId) return;
    setExpId(id); setReceipt(null); setRepro(null);
    try {
      const rec = await getReceipt(projectId, id);
      setReceipt(rec);
      setRepro(await getReproducibility(projectId, rec.receipt_id).catch(() => null));
    } catch { /* no receipt yet */ }
  };

  const generate = async () => {
    if (!projectId || !expId) return;
    setBusy(true);
    try {
      const r = await generateReceipt(projectId, expId);
      setReceipt(r);
      setRepro(await getReproducibility(projectId, r.receipt_id).catch(() => null));
      notify("success", `Receipt ${r.receipt_id} generated.`);
      void load();
    } catch (e) { notify("error", e instanceof ApiError ? e.message : "Generation failed."); }
    finally { setBusy(false); }
  };

  const verify = async () => {
    if (!projectId || !receipt) return;
    setBusy(true);
    try {
      const r = await verifyReceipt(projectId, receipt.receipt_id);
      setReceipt({ ...receipt, verifications: r.verifications });
      notify(r.verification.ok ? "success" : "error", r.verification.ok ? "Verification passed." : "Verification found discrepancies.");
    } catch (e) { notify("error", e instanceof ApiError ? e.message : "Verification failed."); }
    finally { setBusy(false); }
  };

  const downloadJson = () => {
    if (!receipt) return;
    const blob = new Blob([JSON.stringify(receipt.payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${receipt.receipt_id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (!projectId) return null;
  if (status === "loading") return <div className="py-16 text-center"><Spinner label="Loading…" /></div>;
  if (status === "error") return <ErrorBanner message={error ?? "Unavailable."} onRetry={() => void load()} />;

  const p = receipt?.payload;
  const ds = p?.dataset ?? {};
  const art = p?.artifact ?? {};
  const lastVerify = receipt?.verifications?.[receipt.verifications.length - 1];

  return (
    <>
      <PageHeader title="Trust Receipts" subtitle="Verifiable, immutable records of experiment lineage, configuration, artifacts and reproducibility evidence." />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-1">
          <Card className="p-4">
            <h2 className="text-sm font-semibold text-ivory-100">Experiments</h2>
            <select value={expId} onChange={(e) => void openExperiment(e.target.value)}
              className="mt-2 w-full rounded border border-surface-700 bg-surface-900 px-2 py-2 text-sm text-ivory-100">
              <option value="">Select completed experiment…</option>
              {experiments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
            {expId && (
              <button onClick={() => void generate()} disabled={busy}
                className="mt-2 w-full rounded bg-chartreuse-500 px-3 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
                {busy ? "Working…" : "Generate / view receipt"}
              </button>
            )}
          </Card>
          {receipts.length > 0 && (
            <Card className="p-4">
              <h2 className="text-sm font-semibold text-ivory-100">All receipts</h2>
              <div className="mt-2 space-y-1">
                {receipts.map((r) => (
                  <button key={r.receipt_id} onClick={() => { setExpId(r.experiment_id); void openExperiment(r.experiment_id); }}
                    className="block w-full rounded border border-surface-700 px-2 py-1.5 text-left text-xs text-ivory-200 hover:border-chartreuse-500/50">
                    {r.receipt_id} · {r.signed ? "signed" : "unsigned"} · {r.verification_count} verify
                  </button>
                ))}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4 lg:col-span-2">
          {!receipt ? (
            <Card className="p-6 text-sm text-surface-400">Select a completed experiment and generate a trust receipt.</Card>
          ) : (
            <>
              <Card className="p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-lg font-bold text-ivory-100">{receipt.receipt_id}</div>
                    <div className="text-xs text-surface-400">digest: <span className="font-mono">{receipt.digest.slice(0, 24)}…</span>{receipt.signature ? " · signed" : " · unsigned"}</div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => void navigator.clipboard.writeText(receipt.digest)} className="rounded border border-surface-600 px-2 py-1 text-xs text-ivory-200">Copy digest</button>
                    <button onClick={downloadJson} className="rounded border border-surface-600 px-2 py-1 text-xs text-ivory-200">JSON</button>
                    <button onClick={() => void verify()} disabled={busy} className="rounded bg-ivory-100 px-3 py-1 text-xs font-medium text-surface-950 disabled:opacity-50">Verify</button>
                  </div>
                </div>
                {repro && (
                  <div className="mt-3">
                    <Badge tone={STATUS_TONE[repro.status] ?? "soon"}>reproducibility: {repro.status}</Badge>
                    <div className="mt-2 space-y-0.5 text-[11px] text-surface-300">
                      {repro.checks.map((c) => <div key={c.check}>{c.status === "pass" ? "✓" : c.status === "fail" ? "✗" : "?"} {c.check} — {c.detail}</div>)}
                    </div>
                  </div>
                )}
                {lastVerify && (
                  <div className="mt-2 text-xs">
                    last verification {new Date(lastVerify.verified_at).toLocaleString()}: {lastVerify.ok ? "passed" : "FAILED"}
                  </div>
                )}
              </Card>

              <div className="grid gap-4 md:grid-cols-2">
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-ivory-100">Dataset integrity</h3>
                  <dl className="mt-2 space-y-1 text-xs">
                    <div className="flex justify-between"><dt className="text-surface-400">available</dt><dd>{String(!!ds.available)}</dd></div>
                    <div className="flex justify-between"><dt className="text-surface-400">checksum</dt><dd className="font-mono">{(ds.sha256_checksum ?? "—").slice(0, 16)}…</dd></div>
                    <div className="flex justify-between"><dt className="text-surface-400">file verified</dt><dd>{ds.file_checksum_verified == null ? "unverified" : String(ds.file_checksum_verified)}</dd></div>
                    <div className="flex justify-between"><dt className="text-surface-400">dimensions</dt><dd>{ds.row_count ?? "?"} × {ds.column_count ?? "?"}</dd></div>
                  </dl>
                </Card>
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-ivory-100">Artifact integrity</h3>
                  <dl className="mt-2 space-y-1 text-xs">
                    <div className="flex justify-between"><dt className="text-surface-400">exists</dt><dd>{String(!!art.exists)}</dd></div>
                    <div className="flex justify-between"><dt className="text-surface-400">sha256</dt><dd className="font-mono">{(art.sha256 ?? "—").slice(0, 16)}…</dd></div>
                    <div className="flex justify-between"><dt className="text-surface-400">size</dt><dd>{art.size_bytes ?? "—"} B</dd></div>
                  </dl>
                </Card>
              </div>

              <Card className="p-4">
                <h3 className="text-sm font-semibold text-ivory-100">Experiment evidence</h3>
                <div className="mt-2 text-xs text-surface-300">
                  seed {p?.configuration?.random_seed} · splits {JSON.stringify(p?.configuration?.splits)} · best model {p?.training?.best_model_name ?? "—"}
                  {" · "}preprocessing: {p?.configuration?.preprocessing_config
                    ? JSON.stringify(p.configuration.preprocessing_config)
                    : "not recorded (historical experiment — training defaults were used)"}
                </div>
                <div className="mt-2 space-y-1">
                  {(p?.model_results ?? []).map((m: any, i: number) => (
                    <div key={i} className="flex justify-between border-t border-surface-800 pt-1 text-xs">
                      <span className="text-ivory-200">{m.model_name}{m.is_selected ? " ★" : ""}</span>
                      <span className="text-surface-400">{m.status}{m.training_duration_ms ? ` · ${m.training_duration_ms}ms` : ""}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-2 text-[11px] text-surface-500">
                  explainability: {p?.explainability?.available
                    ? `available on demand — ${(p?.explainability?.methods ?? []).join(", ")}`
                    : (p?.explainability?.note ?? "unavailable")}
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  );
}
