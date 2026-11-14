import { useState } from "react";
import { useParams } from "react-router-dom";
import { Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { ApiError } from "../api/client";
import { askCopilot, getResearchReport, type CopilotAnswer, type ResearchReport } from "../api/copilot";

const SUGGESTED = [
  "Which model performed best and why?",
  "Is my dataset suitable for this prediction task?",
  "Are there signs of overfitting?",
  "Which features contribute most to the prediction?",
  "Is my registered model ready for production?",
];

export default function Copilot() {
  const { projectId } = useParams<{ projectId: string }>();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<(CopilotAnswer & { ts: number })[]>([]);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [reportBusy, setReportBusy] = useState(false);

  if (!projectId) return null;

  const ask = async (q: string) => {
    if (!q.trim()) return;
    setBusy(true); setError(null);
    try {
      const a = await askCopilot(projectId, q.trim());
      setHistory((h) => [...h, { ...a, ts: Date.now() }]);
      setQuestion("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Copilot request failed.");
    } finally { setBusy(false); }
  };

  const genReport = async () => {
    setReportBusy(true); setError(null);
    try { setReport(await getResearchReport(projectId)); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Report generation failed."); }
    finally { setReportBusy(false); }
  };

  return (
    <>
      <PageHeader title="Research Copilot" subtitle="Answers are grounded in your project's stored datasets, experiments, metrics and registry — not generic advice." />
      {error && <div className="mb-4"><ErrorBanner message={error} /></div>}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-1">
          <h2 className="text-sm font-semibold text-ivory-100">Suggested questions</h2>
          <div className="mt-2 space-y-1">
            {SUGGESTED.map((q) => (
              <button key={q} onClick={() => void ask(q)} disabled={busy}
                className="block w-full rounded border border-surface-700 px-2 py-1.5 text-left text-xs text-ivory-200 hover:border-chartreuse-500/50 disabled:opacity-50">
                {q}
              </button>
            ))}
          </div>
          <button onClick={() => void genReport()} disabled={reportBusy}
            className="mt-4 w-full rounded bg-ivory-100 px-3 py-2 text-xs font-medium text-surface-950 disabled:opacity-50">
            {reportBusy ? "Generating…" : "Generate research report"}
          </button>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          {history.length === 0 && !busy && (
            <Card className="p-6 text-sm text-surface-400">Ask a research question about this project.</Card>
          )}
          {history.map((a) => (
            <Card key={a.ts} className="p-4">
              <div className="text-xs font-medium text-ivory-300">Q: {a.question}</div>
              <div className="mt-2 whitespace-pre-wrap text-sm text-ivory-100">{a.answer}</div>
              {a.evidence && a.evidence.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {a.evidence.map((ev, i) => (
                    <span key={i} className="rounded bg-surface-800 px-1.5 py-0.5 text-[10px] text-chartreuse-300">
                      {ev.type}: {ev.label}
                    </span>
                  ))}
                </div>
              )}
              {a.limitations && a.limitations.length > 0 && (
                <div className="mt-1 text-[11px] text-surface-400">limitations: {a.limitations.join("; ")}</div>
              )}
              <div className="mt-1 text-[10px] text-surface-500">mode: {a.mode}{a.provider_note ? ` · ${a.provider_note}` : ""}</div>
            </Card>
          ))}
          {busy && <Card className="p-4"><Spinner label="Analyzing project data…" /></Card>}

          {report && (
            <Card className="p-4">
              <h2 className="text-sm font-semibold text-ivory-100">Research report</h2>
              <div className="mt-3 space-y-3">
                {report.sections.map((s) => (
                  <div key={s.title}>
                    <div className="text-xs font-medium text-ivory-200">
                      {s.title} <span className="text-surface-500">({s.status})</span>
                    </div>
                    <div className="mt-0.5 whitespace-pre-wrap text-xs text-surface-300">{s.content}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <div className="flex gap-2">
            <input value={question} onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void ask(question)}
              placeholder="Ask about your data, experiments, or models…"
              className="flex-1 rounded border border-surface-700 bg-surface-900 px-3 py-2 text-sm text-ivory-100" />
            <button onClick={() => void ask(question)} disabled={busy || !question.trim()}
              className="rounded bg-chartreuse-500 px-4 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
              Ask
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
