import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TOKEN_STORAGE_KEY } from "../config";
import { fakeJwt, ME, mockApi, renderApp, signIn } from "../test/utils";

afterEach(() => vi.unstubAllGlobals());
const unauthorized = { status: 401, body: { error: { code: "unauthorized", message: "Incorrect email or password." } } };

describe("login", () => {
  it("validates before calling the server", async () => {
    const { calls } = mockApi({});
    renderApp("/login");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(calls.filter((c) => c.path.endsWith("/auth/login"))).toHaveLength(0);
  });

  it("signs in against the API, stores the session and opens the dashboard", async () => {
    const token = fakeJwt(3600);
    const { calls } = mockApi({
      "POST /api/v1/auth/login": { body: { access_token: token, token_type: "bearer" } },
      "GET /api/v1/auth/me": { body: ME },
      "GET /api/v1/projects": { body: [] },
    });
    const user = userEvent.setup();
    renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBe(token);
    const login = calls.find((c) => c.path === "/api/v1/auth/login")!;
    expect(login.body).toEqual({ email: "ada@example.com", password: "correct-horse-battery" });
    expect(login.authorization).toBeNull();
    expect(calls.find((c) => c.path === "/api/v1/auth/me")!.authorization).toBe(`Bearer ${token}`);
  });

  it("shows the server's message for wrong credentials and stays on the page", async () => {
    mockApi({ "POST /api/v1/auth/login": unauthorized });
    const user = userEvent.setup();
    renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });
});

describe("registration", () => {
  it("checks that passwords match", async () => {
    const { calls } = mockApi({});
    const user = userEvent.setup();
    renderApp("/register");
    await user.type(await screen.findByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "long-enough-pw");
    await user.type(screen.getByLabelText("Confirm password"), "different-pw-1");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("maps a 409 to a friendly message on the email field", async () => {
    mockApi({ "POST /api/v1/auth/register": { status: 409, body: { error: { code: "conflict", message: "exists" } } } });
    const user = userEvent.setup();
    renderApp("/register");
    await user.type(await screen.findByLabelText("Email"), "taken@example.com");
    await user.type(screen.getByLabelText("Password"), "long-enough-pw");
    await user.type(screen.getByLabelText("Confirm password"), "long-enough-pw");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/already exists/)).toBeInTheDocument();
  });

  it("registers, then signs in automatically", async () => {
    const { calls } = mockApi({
      "POST /api/v1/auth/register": { status: 201, body: ME },
      "POST /api/v1/auth/login": { body: { access_token: fakeJwt(3600), token_type: "bearer" } },
      "GET /api/v1/auth/me": { body: ME },
      "GET /api/v1/projects": { body: [] },
    });
    const user = userEvent.setup();
    renderApp("/register");
    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "long-enough-pw");
    await user.type(screen.getByLabelText("Confirm password"), "long-enough-pw");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(calls.map((c) => c.path).slice(0, 2)).toEqual(["/api/v1/auth/register", "/api/v1/auth/login"]);
  });
});

describe("protected routes and session handling", () => {
  it("sends anonymous visitors to the login page", async () => {
    mockApi({});
    renderApp("/app/projects");
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  });

  it("restores a session by asking the server, then shows the app", async () => {
    signIn();
    mockApi({ "GET /api/v1/auth/me": { body: ME }, "GET /api/v1/projects": { body: [] } });
    renderApp("/app");
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByText("ada@example.com", { selector: "span[title='ada@example.com']" })).toBeInTheDocument();
  });

  it("rejects a locally-expired token without calling the API", async () => {
    signIn(-60);
    const { calls } = mockApi({});
    renderApp("/app");
    expect(await screen.findByText(/session expired/i)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  it("logs out and shows a notice when the server answers 401 mid-session", async () => {
    signIn();
    mockApi({ "GET /api/v1/auth/me": { body: ME }, "GET /api/v1/projects": { status: 401, body: { error: { code: "unauthorized", message: "Invalid or expired token." } } } });
    renderApp("/app");
    expect(await screen.findByText(/session expired/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  it("signs out on request and clears the stored token", async () => {
    signIn();
    mockApi({ "GET /api/v1/auth/me": { body: ME }, "GET /api/v1/projects": { body: [] } });
    const user = userEvent.setup();
    renderApp("/app");
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument());
    expect(sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });
});
