import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { ApiError } from "../api/client";
import { getExperiment } from "../api/experiments";
import {
  getWhatIfSchema,
  whatIfCounterfactual,
  whatIfPredict,
  type CounterfactualResult,
  type WhatIfPrediction,
  type WhatIfSchema,
} from "../api/whatif";

export default function WhatIf() {
  const { projectId, experimentId } = useParams<{ projectId: string; experimentId: string }>();
  if (!projectId || !experimentId) return null;

  const [schema, setSchema] = useState<WhatIfSchema | null>(null);
  const [experimentName, setExperimentName] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [predicting, setPredicting] = useState(false);
  const [prediction, setPrediction] = useState<WhatIfPrediction | null>(null);

  const [cfTarget, setCfTarget] = useState("");
  const [cfMin, setCfMin] = useState("");
  const [cfMax, setCfMax] = useState("");
  const [immutable, setImmutable] = useState<Set<string>>(new Set());
  const [counterfactual, setCounterfactual] = useState<CounterfactualResult | null>(null);
  const [cfBusy, setCfBusy] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    setStatus("loading");
    setError(null);
    try {
      const [s, exp] = await Promise.all([
        getWhatIfSchema(projectId, experimentId, signal),
        getExperiment(projectId, experimentId, signal).catch(() => null),
      ]);
      if (signal?.aborted) return;
      setSchema(s);
      setExperimentName(exp?.name ?? "");
      // Seed inputs with observed medians / first category for a usable default.
      const seed: Record<string, string> = {};
      for (const f of s.features) {
        if (f.type === "numeric" && f.min != null && f.max != null) {
          seed[f.name] = String(Number((f.median ?? (f.min + f.max) / 2).toFixed(4)));
        } else if (f.categories?.length) {
          seed[f.name] = f.categories[0];
        } else {
          seed[f.name] = "";
        }
      }
      setValues(seed);
      setStatus("ready");
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load What-If schema.");
      setStatus("error");
    }
  }, [projectId, experimentId]);

  useEffect(() => {
    const c = new AbortController();
    void load(c.signal);
    return () => c.abort();
  }, [load]);

  const payload = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      const spec = schema?.features.find((f) => f.name === k);
      out[k] = spec?.type === "numeric" ? (v === "" ? null : Number(v)) : v;
    }
    return out;
  }, [values, schema]);

  const runPredict = async () => {
    setPredicting(true);
    setError(null);
    try {
      setPrediction(await whatIfPredict(projectId, experimentId, payload));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Prediction failed.");
    } finally {
      setPredicting(false);
    }
  };

  const buildGoal = (): Record<string, unknown> => {
    if (!schema) return {};
    if (schema.task_type === "classification") {
      return cfTarget ? { class: cfTarget } : {};
    }
    const goal: Record<string, unknown> = {};
    if (cfTarget !== "") goal.value = Number(cfTarget);
    if (cfMin !== "") goal.min = Number(cfMin);
    if (cfMax !== "") goal.max = Number(cfMax);
    return goal;
  };

  const runCounterfactual = async () => {
    setCfBusy(true);
    setError(null);
    try {
      const res = await whatIfCounterfactual(projectId, experimentId, payload, buildGoal(), {
        immutable: [...immutable],
      });
      setCounterfactual(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Counterfactual search failed.");
    } finally {
      setCfBusy(false);
    }
  };

  if (status === "loading") return <div className="py-16 text-center"><Spinner label="Loading model schema…" /></div>;
  if (status === "error" || !schema)
    return <ErrorBanner message={error ?? "What-If unavailable for this experiment."} onRetry={() => { const c = new AbortController(); void load(c.signal); }} />;

  const fmt = (v: unknown) => (v === null || v === undefined ? "—" : typeof v === "number" ? Number(v.toFixed(4)) : String(v));

  return (
    <>
      <p className="mb-3 text-sm">
        <Link to={`/app/projects/${projectId}/experiments/${experimentId}`} className="text-ivory-300 hover:text-ivory-50">&larr; Experiment</Link>
      </p>
      <PageHeader
        title={`What-If — ${experimentName || "Experiment"}`}
        subtitle={`${schema.task_type} · target: ${schema.target_column}. Inputs are raw source features — preprocessing is applied by the persisted pipeline. Predictions are model estimates, not causal claims.`}
      />

      {error && <div className="mb-4"><ErrorBanner message={error} /></div>}

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Inputs */}
        <Card className="p-5 lg:col-span-2">
          <h2 className="text-sm font-semibold text-ivory-100">Feature inputs</h2>
          <div className="mt-4 space-y-3">
            {schema.features.map((f) => (
              <div key={f.name}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <label className="text-ivory-200">{f.name}</label>
                  <label className="flex items-center gap-1 text-surface-400">
                    <input type="checkbox" checked={immutable.has(f.name)}
                      onChange={(e) => setImmutable((s) => { const n = new Set(s); e.target.checked ? n.add(f.name) : n.delete(f.name); return n; })}
                      title="Immutable (excluded from counterfactual search)" className="accent-chartreuse-500" />
                    lock
                  </label>
                </div>
                {f.type === "numeric" ? (
                  <input type="number" step="any" value={values[f.name] ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                    className="w-full rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm text-ivory-100" />
                ) : (
                  <select value={values[f.name] ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                    className="w-full rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm text-ivory-100">
                    {(f.categories ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                )}
                {f.type === "numeric" && f.min != null && f.max != null && (
                  <div className="mt-0.5 text-[10px] text-surface-500">observed range [{fmt(f.min)}, {fmt(f.max)}]</div>
                )}
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <button onClick={() => void runPredict()} disabled={predicting}
              className="flex-1 rounded bg-ivory-100 px-3 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
              {predicting ? "Predicting…" : "Run What-If"}
            </button>
            <button onClick={() => setValues(Object.fromEntries(schema.features.map((f) => [f.name, f.type === "numeric" && f.min != null && f.max != null ? String(Number((f.median ?? (f.min + f.max) / 2).toFixed(4))) : (f.categories?.[0] ?? "")])))}
              className="rounded border border-surface-700 px-3 py-2 text-sm text-ivory-200">
              Reset
            </button>
          </div>
        </Card>

        {/* Results */}
        <div className="space-y-6 lg:col-span-3">
          {prediction && (
            <Card className="p-5">
              <h2 className="text-sm font-semibold text-ivory-100">Prediction</h2>
              <div className="mt-3 text-2xl font-bold text-chartreuse-300">{fmt(prediction.output.prediction)}</div>
              {prediction.output.probabilities && (
                <div className="mt-3 space-y-1">
                  {Object.entries(prediction.output.probabilities).map(([cls, p]) => (
                    <div key={cls} className="flex items-center gap-2 text-xs">
                      <span className="w-20 truncate text-ivory-200">{cls}</span>
                      <div className="h-3 flex-1 rounded bg-surface-800">
                        <div className="h-3 rounded bg-chartreuse-500/70" style={{ width: `${p * 100}%` }} />
                      </div>
                      <span className="w-12 text-right text-surface-300">{(p * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}

          <Card className="p-5">
            <h2 className="text-sm font-semibold text-ivory-100">Counterfactual search</h2>
            <p className="mt-1 text-xs text-surface-400">
              Finds minimal feature changes that flip the model's prediction. Model-space explanation — not a guaranteed real-world outcome.
            </p>
            <div className="mt-3 flex flex-wrap items-end gap-3">
              {schema.task_type === "classification" ? (
                <label className="text-xs text-ivory-200">
                  Target class
                  <select value={cfTarget} onChange={(e) => setCfTarget(e.target.value)}
                    className="mt-1 block rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm">
                    <option value="">Select…</option>
                    {(schema.classes ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </label>
              ) : (
                <>
                  <label className="text-xs text-ivory-200">Target value
                    <input type="number" step="any" value={cfTarget} onChange={(e) => setCfTarget(e.target.value)}
                      className="mt-1 block w-28 rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm" />
                  </label>
                  <label className="text-xs text-ivory-200">or range
                    <span className="mt-1 flex gap-1">
                      <input type="number" step="any" placeholder="min" value={cfMin} onChange={(e) => setCfMin(e.target.value)}
                        className="w-24 rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm" />
                      <input type="number" step="any" placeholder="max" value={cfMax} onChange={(e) => setCfMax(e.target.value)}
                        className="w-24 rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm" />
                    </span>
                  </label>
                </>
              )}
              <button onClick={() => void runCounterfactual()} disabled={cfBusy || (schema.task_type === "classification" && !cfTarget)}
                className="rounded bg-chartreuse-500 px-4 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
                {cfBusy ? "Searching…" : "Generate counterfactuals"}
              </button>
            </div>

            {counterfactual && (
              <div className="mt-4 space-y-4">
                <p className="text-xs text-surface-400">
                  {counterfactual.candidates_evaluated} candidates evaluated · {counterfactual.counterfactuals.length} found · immutable: {counterfactual.immutable_features.join(", ") || "none"}
                </p>
                {counterfactual.counterfactuals.length === 0 && (
                  <p className="text-sm text-amber-200">No counterfactual found within the search budget. Try relaxing immutable features or a different target.</p>
                )}
                {counterfactual.counterfactuals.map((cf, i) => (
                  <div key={i} className="rounded border border-surface-700 bg-surface-900 p-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-ivory-100">Candidate {i + 1}</span>
                      <span className="text-surface-400">distance {cf.distance} · feasibility {(cf.feasibility * 100).toFixed(0)}%</span>
                    </div>
                    <div className="mt-1 text-sm">
                      prediction: <span className="text-chartreuse-300">{fmt(cf.prediction.prediction)}</span>
                      {cf.prediction.probabilities && (
                        <span className="ml-2 text-xs text-surface-400">
                          ({Object.entries(cf.prediction.probabilities).map(([k, v]) => `${k}: ${(v * 100).toFixed(0)}%`).join(", ")})
                        </span>
                      )}
                    </div>
                    <table className="mt-2 w-full text-xs">
                      <thead>
                        <tr className="text-left text-surface-400">
                          <th className="py-1 pr-2">Feature</th><th className="py-1 pr-2">Original</th><th className="py-1">Counterfactual</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(cf.changed_features).map(([name, ch]) => (
                          <tr key={name} className="border-t border-surface-800">
                            <td className="py-1 pr-2 text-ivory-200">{name}</td>
                            <td className="py-1 pr-2 text-surface-400">{fmt(ch.from)}</td>
                            <td className="py-1 text-chartreuse-200">{fmt(ch.to)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
