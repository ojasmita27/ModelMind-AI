import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ME, mockApi, project, renderApp, signIn } from "../test/utils";

const base = { "GET /api/v1/auth/me": { body: ME } };

describe("ProjectExperiments", () => {
  it("does not auto-select the first column and requires explicit target selection", async () => {
    signIn();
    mockApi({
      ...base,
      "GET /api/v1/projects/p1": { body: project(1, { name: "Churn" }) },
      "GET /api/v1/projects/p1/datasets": {
        body: [{ id: "d1", project_id: "p1", name: "Customer data", description: null, created_at: "2026-01-01T00:00:00Z" }],
      },
      "GET /api/v1/projects/p1/datasets/d1": {
        body: {
          id: "d1",
          project_id: "p1",
          name: "Customer data",
          description: null,
          created_at: "2026-01-01T00:00:00Z",
          versions: [{
            id: "v1",
            dataset_id: "d1",
            version_number: 1,
            sha256_checksum: "abc",
            file_path: "datasets/d1/v1.csv",
            file_size_bytes: 512,
            row_count: 100,
            column_count: 4,
            job_status: "completed",
            job_error: null,
            job_started_at: "2026-01-01T00:00:00Z",
            job_completed_at: "2026-01-01T00:00:00Z",
            created_at: "2026-01-01T00:00:00Z",
          }],
        },
      },
      "GET /api/v1/projects/p1/experiments": { body: [] },
      "GET /api/v1/projects/p1/datasets/d1/preview": {
        body: {
          columns: ["age", "score", "status"],
          rows: [
            { age: "31", score: "12.4", status: "new" },
            { age: "45", score: "17.2", status: "active" },
          ],
        },
      },
      "GET /api/v1/projects/p1/datasets/d1/profile": {
        body: {
          row_count: 100,
          column_count: 3,
          columns: [
            { name: "age", type: "integer", missing_count: 0, missing_percentage: 0, unique_count: 20, sample_values: ["31", "45"] },
            { name: "score", type: "float", missing_count: 0, missing_percentage: 0, unique_count: 34, sample_values: ["12.4", "17.2"] },
            { name: "status", type: "string", missing_count: 0, missing_percentage: 0, unique_count: 2, sample_values: ["new", "active"] },
          ],
          duplicate_row_count: 0,
          duplicate_row_percentage: 0,
          constant_columns: [],
          warnings: [],
        },
      },
    });

    renderApp("/app/projects/p1/experiments");

    const targetSelect = await screen.findByLabelText("Target column");
    await waitFor(() => {
      const optionValues = Array.from((targetSelect as HTMLSelectElement).options).map((option) => option.textContent);
      expect(optionValues).toContain("status");
    });
    expect(targetSelect).toHaveValue("");
    expect(screen.queryByText(/auto-selected/i)).not.toBeInTheDocument();
  });
});
