import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ME, mockApi, project, renderApp, signIn } from "../../test/utils";

afterEach(() => vi.unstubAllGlobals());
const base = { "GET /api/v1/auth/me": { body: ME } };

describe("Projects page", () => {
  it("lists the projects returned by the API", async () => {
    signIn();
    mockApi({ ...base, "GET /api/v1/projects": { body: [project(1, { name: "Churn", description: "Why users leave" }), project(2)] } });
    renderApp("/app/projects");
    expect(await screen.findByText("Churn")).toBeInTheDocument();
    expect(screen.getByText("Why users leave")).toBeInTheDocument();
    expect(screen.getByText("Project 2")).toBeInTheDocument();
  });

  it("shows an empty state, and an error state with retry", async () => {
    signIn();
    mockApi({ ...base, "GET /api/v1/projects": { body: [] } });
    const first = renderApp("/app/projects");
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    first.unmount();

    mockApi({ ...base, "GET /api/v1/projects": { status: 500, body: { error: { code: "internal_error", message: "An unexpected error occurred." } } } });
    renderApp("/app/projects");
    expect(await screen.findByRole("alert")).toHaveTextContent("An unexpected error occurred.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("creates a project through the API and shows it with a success message", async () => {
    signIn();
    const { calls } = mockApi({ ...base, "GET /api/v1/projects": { body: [] },
      "POST /api/v1/projects": (c) => ({ status: 201, body: { ...project(9), ...(c.body as object) } }) });
    const user = userEvent.setup();
    renderApp("/app/projects");
    await user.click(await screen.findByRole("button", { name: /Create your first project/ }));
    const dialog = await screen.findByRole("dialog", { name: "New project" });
    await user.type(within(dialog).getByLabelText("Project name"), "  Fraud model  ");
    await user.click(within(dialog).getByRole("button", { name: "Create project" }));

    expect(await screen.findByText("Project created.")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Fraud model" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ name: "Fraud model", description: null });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("blocks an empty name locally and shows server validation errors", async () => {
    signIn();
    const { calls } = mockApi({ ...base, "GET /api/v1/projects": { body: [project(1)] },
      "POST /api/v1/projects": { status: 422, body: { error: { code: "validation_error", message: "bad", details: { errors: [{ loc: ["body", "name"], msg: "String should have at most 120 characters" }] } } } } });
    const user = userEvent.setup();
    renderApp("/app/projects");
    await user.click(await screen.findByRole("button", { name: "New project" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(await within(dialog).findByText("Give your project a name.")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);

    await user.type(within(dialog).getByLabelText("Project name"), "Valid name");
    await user.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(await within(dialog).findByText(/at most 120 characters/)).toBeInTheDocument();
  });

  it("edits a project with PATCH", async () => {
    signIn();
    const { calls } = mockApi({ ...base, "GET /api/v1/projects": { body: [project(1, { name: "Old" })] },
      "PATCH /api/v1/projects/p1": (c) => ({ body: { ...project(1), ...(c.body as object) } }) });
    const user = userEvent.setup();
    renderApp("/app/projects");
    await user.click(await screen.findByRole("button", { name: "Edit Old" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit project" });
    const name = within(dialog).getByLabelText("Project name");
    await user.clear(name);
    await user.type(name, "New name");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("link", { name: "New name" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ name: "New name", description: null });
  });

  it("asks for confirmation before deleting, then calls DELETE", async () => {
    signIn();
    const { calls } = mockApi({ ...base, "GET /api/v1/projects": { body: [project(1, { name: "Doomed" }), project(2)] },
      "DELETE /api/v1/projects/p1": { status: 204 } });
    const user = userEvent.setup();
    renderApp("/app/projects");
    await user.click(await screen.findByRole("button", { name: "Delete Doomed" }));
    expect(calls.filter((c) => c.method === "DELETE")).toHaveLength(0);
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete project" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Doomed" })).not.toBeInTheDocument());
    expect(calls.filter((c) => c.method === "DELETE")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Project 2" })).toBeInTheDocument();
  });

  it("filters loaded projects by search text", async () => {
    signIn();
    mockApi({ ...base, "GET /api/v1/projects": { body: [project(1, { name: "Alpha" }), project(2, { name: "Beta" })] } });
    const user = userEvent.setup();
    renderApp("/app/projects");
    await screen.findByText("Alpha");
    await user.type(screen.getByLabelText("Search projects"), "bet");
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });
});

describe("Project detail and dashboard", () => {
  it("shows 'not found' for a project the API says does not exist (or isn't yours)", async () => {
    signIn();
    mockApi({ ...base, "GET /api/v1/projects/zzz": { status: 404, body: { error: { code: "not_found", message: "Project not found." } } } });
    renderApp("/app/projects/zzz");
    expect(await screen.findByText("Project not found")).toBeInTheDocument();
  });

  it("dashboard shows real counts, an honest 'coming soon' for ML features, and no chart when empty", async () => {
    signIn();
    mockApi({ ...base, "GET /api/v1/projects": { body: [] } });
    const empty = renderApp("/app");
    expect(await screen.findByText("Welcome to ModelMind")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Projects created per month/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("Coming soon").length).toBeGreaterThan(0);
    empty.unmount();

    mockApi({ ...base, "GET /api/v1/projects": { body: [project(1), project(2), project(3)] } });
    renderApp("/app");
    expect(await screen.findByRole("img", { name: /Projects created per month/ })).toBeInTheDocument();
    expect(screen.getByText("Projects", { selector: "p" }).parentElement).toHaveTextContent("3");
    expect(screen.queryByText(/accuracy|f1|rmse/i)).not.toBeInTheDocument(); // no ML metrics are displayed
  });

  it("coming-soon pages say the feature is not implemented", async () => {
    signIn();
    mockApi({ ...base });
    renderApp("/app/coming-soon/datatwin");
    expect(await screen.findByRole("heading", { name: "DataTwin" })).toBeInTheDocument();
    expect(screen.getByText(/not implemented yet/)).toBeInTheDocument();
  });
});
