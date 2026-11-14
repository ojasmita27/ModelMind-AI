"""AI Research Copilot: grounded Q&A over real project data.

Answers are generated from retrieved project context (dataset profiles,
experiments, metrics, registry, what-if runs). When GEMINI_API_KEY is set,
the context digest is sent to Gemini for free-form answers; otherwise a
deterministic grounded summarizer answers suggested question types.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import (
    Dataset, DatasetVersion, Experiment, ExperimentModelResult,
    ModelVersion, RegisteredModel, WhatIfRun,
)
from app.services.projects import get_owned_project

MAX_CONTEXT_CHARS = 12000
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "30"))


def gather_context(db: Session, project_id: uuid.UUID) -> dict[str, Any]:
    """Retrieve real project data. All rows belong to the project."""
    ctx: dict[str, Any] = {"project_id": str(project_id), "datasets": [], "experiments": [], "models": [], "whatif": []}

    datasets = db.scalars(select(Dataset).where(Dataset.project_id == project_id)).all()
    for d in datasets:
        versions = db.scalars(select(DatasetVersion).where(DatasetVersion.dataset_id == d.id).order_by(DatasetVersion.version_number.desc())).all()
        ctx["datasets"].append({
            "id": str(d.id), "name": d.name,
            "versions": [{
                "id": str(v.id), "version_number": v.version_number, "row_count": v.row_count,
                "column_count": v.column_count, "job_status": v.job_status,
                "source": v.source,
                "transformation_log": v.transformation_log if isinstance(v.transformation_log, list) else None,
            } for v in versions[:5]],
        })

    experiments = db.scalars(select(Experiment).where(Experiment.project_id == project_id).order_by(Experiment.created_at.desc()).limit(20)).all()
    for e in experiments:
        results = db.scalars(select(ExperimentModelResult).where(ExperimentModelResult.experiment_id == e.id)).all()
        ctx["experiments"].append({
            "id": str(e.id), "name": e.name, "status": e.status, "task_type": e.task_type,
            "target_column": e.target_column, "model_names": list(e.model_names or []),
            "metrics": e.metrics or {},
            "models": [{
                "name": r.model_name, "status": r.status,
                "validation_metrics": r.validation_metrics, "test_metrics": r.test_metrics,
                "is_selected": r.is_selected, "error": r.error,
            } for r in results],
        })

    models = db.scalars(select(RegisteredModel).where(RegisteredModel.project_id == project_id)).all()
    for m in models:
        versions = db.scalars(select(ModelVersion).where(ModelVersion.model_id == m.id).order_by(ModelVersion.version_number.desc())).all()
        ctx["models"].append({
            "id": str(m.id), "name": m.name, "task_type": m.task_type,
            "versions": [{"id": str(v.id), "version_number": v.version_number, "algorithm": v.algorithm,
                          "lifecycle_status": v.lifecycle_status, "validation": v.validation} for v in versions[:10]],
        })

    whatif = db.scalars(select(WhatIfRun).join(Experiment, WhatIfRun.experiment_id == Experiment.id)
                        .where(Experiment.project_id == project_id).order_by(WhatIfRun.created_at.desc()).limit(10)).all()
    ctx["whatif"] = [{"kind": w.kind, "input": w.input_data, "output": w.output_data} for w in whatif]
    return ctx


def _digest(ctx: dict[str, Any]) -> str:
    import json
    text = json.dumps(ctx, default=str)
    return text[:MAX_CONTEXT_CHARS]


def _grounded_answer(question: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """Deterministic grounded answers for common research questions."""
    q = question.lower()
    refs: list[dict[str, str]] = []
    statements: list[str] = []
    limitations: list[str] = []

    completed = [e for e in ctx["experiments"] if e["status"] == "completed"]
    datasets = ctx["datasets"]

    if any(k in q for k in ("best model", "performed best", "which model")) and completed:
        for e in completed[:3]:
            sel = [m for m in e["models"] if m.get("is_selected")]
            if sel:
                m = sel[0]
                vm = m.get("validation_metrics") or {}
                score = vm.get("f1_macro") or vm.get("accuracy") or vm.get("r2")
                statements.append(f"Experiment '{e['name']}' selected {m['name']}"
                                  + (f" with validation score {score:.4f}" if isinstance(score, (int, float)) else "")
                                  + " (selected on validation metrics only).")
                refs.append({"type": "experiment", "id": e["id"], "label": e["name"]})
        if not statements:
            statements.append("No completed experiment has a selected model recorded.")
            limitations.append("Selection metrics unavailable.")
    elif "overfit" in q or "overfitting" in q:
        for e in completed[:5]:
            for m in e["models"]:
                vm, tm = m.get("validation_metrics") or {}, m.get("test_metrics") or {}
                if vm and tm:
                    vk = "f1_macro" if "f1_macro" in vm else ("accuracy" if "accuracy" in vm else "r2")
                    if vk in vm and vk in tm:
                        gap = abs(float(vm[vk]) - float(tm[vk]))
                        if gap > 0.15:
                            statements.append(f"{e['name']} / {m['name']}: validation {vk}={vm[vk]:.3f} vs test {vk}={tm[vk]:.3f} — possible overfitting signal (gap {gap:.3f}).")
                            refs.append({"type": "experiment", "id": e["id"], "label": e["name"]})
        if not statements:
            statements.append("No completed experiments with both validation and test metrics are available to assess overfitting.")
            limitations.append("Insufficient metric pairs for overfit analysis.")
    elif "ready for production" in q or "production" in q:
        for m in ctx["models"][:5]:
            for v in m["versions"][:3]:
                val = v.get("validation") or {}
                statements.append(f"{m['name']} v{v['version_number']} ({v['algorithm']}): lifecycle={v['lifecycle_status']}, "
                                  f"validation={'passed' if val.get('ok') else ('failed' if val else 'not run')}. "
                                  + ("Not ready." if not val.get("ok") else "Validation passed; promotion is a lifecycle decision, not deployment."))
                refs.append({"type": "model", "id": v["id"], "label": f"{m['name']} v{v['version_number']}"})
        if not statements:
            statements.append("No registered models found in this project.")
    elif "dataset" in q and ("suitable" in q or "quality" in q or "missing" in q):
        for d in datasets[:5]:
            for v in d["versions"][:1]:
                log = v.get("transformation_log") or []
                statements.append(f"Dataset '{d['name']}' v{v['version_number']}: {v['row_count']} rows × {v['column_count']} cols, source={v['source']}"
                                  + (f", {len(log)} transformation(s) applied" if log else ", no cleaning transformations"))
                refs.append({"type": "dataset", "id": v["id"], "label": d["name"]})
        if not statements:
            statements.append("No datasets found in this project.")
    elif "feature" in q and ("important" in q or "contribute" in q or "shap" in q):
        found = False
        for e in completed:
            met = e.get("metrics") or {}
            if met.get("feature_importance"):
                statements.append(f"Experiment '{e['name']}' stored feature importance: {met['feature_importance']}.")
                refs.append({"type": "experiment", "id": e["id"], "label": e["name"]})
                found = True
        if not found:
            statements.append("No SHAP or feature-importance results are stored for this project's experiments.")
            limitations.append("Explainability data unavailable.")
    else:
        # Generic grounded summary.
        n_exp = len(completed)
        n_ds = len(datasets)
        n_mod = sum(len(m["versions"]) for m in ctx["models"])
        statements.append(f"Project context: {n_ds} dataset(s), {len(ctx['experiments'])} experiment(s) ({n_exp} completed), {n_mod} registered model version(s), {len(ctx['whatif'])} what-if run(s).")
        limitations.append("Ask about best model, overfitting, dataset quality, features, production readiness, or preprocessing for a grounded answer.")

    return {
        "answer": "\n".join(statements) if statements else "No relevant project data available.",
        "statements": statements,
        "evidence": refs,
        "limitations": limitations,
        "mode": "grounded_rules",
    }


def _call_gemini(question: str, digest: str) -> dict[str, Any] | None:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    try:
        import httpx
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
        prompt = (
            "You are a research copilot for an ML workbench. Answer ONLY from the provided project context. "
            "Never invent metrics or results; state when data is unavailable. Do not claim causation.\n\n"
            f"CONTEXT:\n{digest}\n\nQUESTION: {question}"
        )
        r = httpx.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=GEMINI_TIMEOUT)
        if r.status_code != 200:
            return {"error": f"provider_error_{r.status_code}", "mode": "gemini"}
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return {"answer": text, "mode": "gemini", "evidence": [], "limitations": ["LLM-generated; verify against stored results."]}
    except Exception as exc:
        return {"error": f"provider_unavailable: {exc}", "mode": "gemini"}


def ask(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, question: str) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    if not question or not question.strip():
        raise AppError(422, "validation_error", "Question must not be empty.")
    if len(question) > 2000:
        raise AppError(422, "validation_error", "Question too long (max 2000 chars).")
    ctx = gather_context(db, project_id)
    digest = _digest(ctx)
    gemini = _call_gemini(question.strip(), digest)
    if gemini and "answer" in gemini:
        return {"project_id": str(project_id), "question": question.strip(), "context_digest_chars": len(digest), **gemini}
    grounded = _grounded_answer(question.strip(), ctx)
    grounded["project_id"] = str(project_id)
    grounded["question"] = question.strip()
    grounded["context_digest_chars"] = len(digest)
    if gemini and gemini.get("error"):
        grounded["provider_note"] = gemini["error"]
    return grounded


def research_report(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID | None) -> dict[str, Any]:
    """Structured report from stored results only; missing sections labeled."""
    get_owned_project(db, owner_id, project_id)
    ctx = gather_context(db, project_id)
    sections: list[dict[str, Any]] = []

    sections.append({"title": "Research objective", "status": "info",
                     "content": "Report generated from stored experiment and dataset records."})

    ds_text = "; ".join(
        f"{d['name']} ({len(d['versions'])} version(s))" for d in ctx["datasets"]
    ) or "No datasets recorded."
    sections.append({"title": "Datasets", "status": "ok" if ctx["datasets"] else "missing", "content": ds_text})

    exps = ctx["experiments"]
    if exps:
        lines = []
        for e in exps[:10]:
            best = e["metrics"].get("best_model_name")
            lines.append(f"{e['name']}: {e['task_type']}, target={e['target_column']}, status={e['status']}"
                         + (f", best={best}" if best else ""))
        sections.append({"title": "Experiments", "status": "ok", "content": "\n".join(lines)})
    else:
        sections.append({"title": "Experiments", "status": "missing", "content": "No experiments recorded."})

    if ctx["models"]:
        lines = [f"{m['name']} ({m['task_type']}): " +
                 ", ".join(f"v{v['version_number']}={v['lifecycle_status']}" for v in m["versions"][:5])
                 for m in ctx["models"]]
        sections.append({"title": "Registered models", "status": "ok", "content": "\n".join(lines)})
    else:
        sections.append({"title": "Registered models", "status": "missing", "content": "No models registered."})

    sections.append({"title": "Explainability", "status": "missing" if not ctx["whatif"] else "ok",
                     "content": f"{len(ctx['whatif'])} what-if run(s) recorded." if ctx["whatif"] else "No SHAP or what-if explanations stored."})

    sections.append({"title": "Limitations", "status": "info",
                     "content": "Metrics are validation/test estimates from stored experiments; counterfactuals are model-space explanations, not causal claims. Missing sections indicate unavailable evidence, not zero performance."})

    from datetime import datetime, timezone
    return {"project_id": str(project_id), "sections": sections,
            "generated_at": datetime.now(timezone.utc).isoformat()}
