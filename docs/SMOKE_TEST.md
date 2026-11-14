# Manual smoke-test checklist

Start backend and frontend (see README), open http://localhost:5173 in Chrome/Edge. Tick each line.

**Startup**
- [ ] Backend terminal shows a `startup` log line with `db_reachable=True migrations_current=True`.
- [ ] http://127.0.0.1:8000/api/v1/health returns `{"status":"ok","database":"up"}`.
- [ ] `python -m app.check_config` (in `backend\`) prints `migrations: up to date` and never prints SECRET_KEY.

**Landing and auth**
- [ ] `/` shows the landing page; "Available today" and "On the roadmap (Coming soon)" are separate.
- [ ] `/app` while signed out redirects to `/login`.
- [ ] Register with an invalid email, a 7-character password, and mismatched passwords: each shows a clear message, no request is sent.
- [ ] Register a valid account: you land on the Dashboard, signed in.
- [ ] Sign out; sign in with a wrong password: "Incorrect email or password."
- [ ] Register the same email again: "An account with this email already exists."
- [ ] Sign in correctly; reload the page: you stay signed in. Close the tab and reopen: you are signed out.

**Projects**
- [ ] Dashboard of a new account shows the empty state and "Coming soon" cards for Datasets and Experiments (no numbers, no charts).
- [ ] Create a project: success toast, appears in the list; the dashboard now shows a chart with real counts.
- [ ] Creating with an empty name is blocked with "Give your project a name."
- [ ] Edit the name/description; delete with the confirmation dialog (Esc cancels).
- [ ] Open a project: details page shows Datasets/Experiments marked "Coming soon".
- [ ] Sidebar "Coming soon" links open honest "not implemented yet" pages.

**Authorization and sessions**
- [ ] Register a second account in a private window: it does not see the first account's projects.
- [ ] Paste the first account's project URL in the second account: "Project not found".
- [ ] Stop the backend: pages show "Cannot reach the ModelMind API..." with a Retry button; restart and Retry works.
- [ ] Set `ACCESS_TOKEN_EXPIRE_MINUTES=1`, restart the backend, sign in, wait 60+ seconds: you are returned to login with "Your session expired."

**Responsive/accessibility**
- [ ] Narrow the window below 1024px: sidebar becomes a menu button; the dialog fills the width.
- [ ] Tab through the login form and a dialog with the keyboard; focus is always visible; Esc closes dialogs.

**Logs**
- [ ] The backend terminal shows request lines but no passwords, tokens or query strings.
