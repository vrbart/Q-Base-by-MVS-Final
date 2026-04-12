"""All-in-one CCBS multi-instance control UI."""

from __future__ import annotations


def render_multi_instance_ui_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Q-Base Multi-Instance Control</title>
  <style>
    :root {
      --bg: #071026;
      --bg2: #0f1f45;
      --ink: #e9f5ff;
      --muted: #9eb8d6;
      --edge: rgba(110, 191, 255, 0.34);
      --panel: rgba(8, 18, 44, 0.9);
      --ok: #8cff63;
      --warn: #ffcd5a;
      --bad: #ff768d;
      --accent: #58e4ff;
      --accent2: #8cff63;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body {
      color: var(--ink);
      font-family: "Space Grotesk", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 12% 8%, rgba(88,228,255,0.18), transparent 32%),
        radial-gradient(circle at 92% 3%, rgba(140,255,99,0.12), transparent 26%),
        linear-gradient(150deg, var(--bg), var(--bg2));
    }
    .shell {
      width: min(1480px, 100%);
      margin: 0 auto;
      padding: 16px;
      display: grid;
      gap: 12px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--edge);
      border-radius: 14px;
      box-shadow: 0 16px 34px rgba(0,0,0,0.32);
    }
    .hero {
      padding: 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    .hero h1 {
      margin: 0;
      font-size: 22px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .hero p {
      margin: 6px 0 0 0;
      color: var(--muted);
      font-size: 13px;
    }
    .hero-links {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .hero-links a {
      color: #012438;
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      padding: 8px 10px;
      border-radius: 999px;
      background: linear-gradient(120deg, var(--accent), #9ff2ff);
    }
    .hero-links a.alt {
      background: linear-gradient(120deg, var(--accent2), #beff96);
      color: #042607;
    }
    .app-grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 12px;
    }
    .controls {
      padding: 14px;
      display: grid;
      gap: 10px;
      align-content: start;
      position: sticky;
      top: 12px;
      height: fit-content;
    }
    .controls h2 {
      margin: 0;
      font-size: 16px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .muted {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .counter {
      font-size: 34px;
      font-weight: 800;
      letter-spacing: 0.04em;
      color: var(--accent2);
      margin-top: -2px;
    }
    label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
      margin-top: -4px;
    }
    .hint strong {
      color: var(--ink);
      font-weight: 700;
    }
    input, select, textarea, button {
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--edge);
      background: rgba(4, 11, 30, 0.92);
      color: var(--ink);
      padding: 9px 10px;
      font: inherit;
    }
    textarea { min-height: 96px; resize: vertical; }
    button {
      border: 0;
      cursor: pointer;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: #062033;
      background: linear-gradient(120deg, var(--accent), #9ff2ff);
    }
    button.alt {
      color: #042607;
      background: linear-gradient(120deg, var(--accent2), #beff96);
    }
    button.warn {
      color: #35040f;
      background: linear-gradient(120deg, #ffb0be, var(--bad));
    }
    .button-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .workspace {
      padding: 14px;
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .status {
      padding: 10px;
      border-radius: 10px;
      border: 1px solid var(--edge);
      background: rgba(6, 12, 29, 0.86);
      color: var(--muted);
      min-height: 44px;
      white-space: pre-wrap;
    }
    .status.ok { color: var(--ok); }
    .status.error { color: var(--bad); }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }
    .kpi {
      border: 1px solid rgba(110, 191, 255, 0.3);
      border-radius: 12px;
      background: rgba(4, 11, 30, 0.72);
      padding: 10px;
    }
    .kpi .label {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .kpi .value {
      margin-top: 4px;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: 0.03em;
    }
    h3 {
      margin: 0 0 8px 0;
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }
    .lane-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .lane-card {
      border: 1px solid rgba(110, 191, 255, 0.3);
      border-radius: 12px;
      background: rgba(4, 11, 30, 0.7);
      padding: 10px;
      display: grid;
      gap: 6px;
    }
    .lane-card.down {
      border-color: rgba(255, 118, 141, 0.45);
    }
    .lane-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-weight: 700;
    }
    .lane-pill {
      border-radius: 999px;
      font-size: 11px;
      padding: 3px 8px;
      color: #08220a;
      background: var(--ok);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .lane-card.down .lane-pill {
      color: #33020d;
      background: var(--bad);
    }
    .lane-meta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .grid2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      background: rgba(4, 10, 24, 0.64);
      border-radius: 10px;
      overflow: hidden;
    }
    th, td {
      padding: 7px 8px;
      border-bottom: 1px solid rgba(110, 191, 255, 0.18);
      text-align: left;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    details {
      border: 1px solid rgba(110, 191, 255, 0.28);
      border-radius: 12px;
      padding: 10px;
      background: rgba(4, 11, 30, 0.5);
    }
    summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 10px;
    }
    @media (max-width: 1140px) {
      .app-grid { grid-template-columns: 1fr; }
      .controls { position: static; }
      .lane-grid { grid-template-columns: 1fr 1fr; }
      .kpi-grid { grid-template-columns: 1fr 1fr; }
      .grid2, .button-row { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      .lane-grid,
      .kpi-grid { grid-template-columns: 1fr; }
      .shell { padding: 10px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="panel hero">
      <div>
        <h1>Q-Base Multi-Instance Control</h1>
        <p>Command deck for lane routing, optimizer selection, and token telemetry.</p>
      </div>
      <div class="hero-links">
        <a class="alt" href="/v3/ai3/ui">Legacy AI3 UI</a>
        <a href="/v3/chat-ui">Chat UI</a>
        <a href="/v3/foundry-ui">Foundry</a>
      </div>
    </header>

    <div class="app-grid">
      <aside class="panel controls">
        <h2>Runbook</h2>
        <div class="muted">Availability</div>
        <div id="counter" class="counter">0/0</div>

        <label for="token">Bearer Token (only if owner auto-auth is OFF)</label>
        <input id="token" placeholder="Paste bearer token (leave empty after running QB-doctor)" autocomplete="off" />
        <div class="hint">
          <strong>Local demo:</strong> run <code>QB-doctor.bat -OpenUi</code> first. It enables loopback owner auto-auth so you can leave this empty.
          <br/>
          <strong>Storage:</strong> if you do paste a token, it is saved only in this browser (localStorage), not in the repo.
        </div>

        <label for="askInput">Task Request (prefix with -1 / -2 / -3 to set lane priority)</label>
        <textarea id="askInput" placeholder="-1 build login page and backend auth endpoint&#10;-2 write docs and tests for auth flow"></textarea>
        <div class="hint"><strong>Prefix meaning:</strong> -1 highest priority lane, -2 medium, -3 lowest. You can also type <code>lane 4</code> or <code>#R2</code> if your profile supports it.</div>

        <label for="taskLabel">Task Name (optional, for history table)</label>
        <input id="taskLabel" placeholder="example: auth-mvp-pass-1" />

        <label for="applyUsage">Apply Token Usage to Telemetry?</label>
        <select id="applyUsage">
          <option value="true" selected>true</option>
          <option value="false">false</option>
        </select>

        <label for="parallel">Optimizer Parallelism (2-10)</label>
        <select id="parallel">
          <option value="2">2</option>
          <option value="3" selected>3</option>
          <option value="4">4</option>
          <option value="5">5</option>
          <option value="6">6</option>
          <option value="7">7</option>
          <option value="8">8</option>
          <option value="9">9</option>
          <option value="10">10</option>
        </select>

        <div class="button-row">
          <button id="refresh">Refresh</button>
          <button id="routeAsk" class="alt">Route Ask</button>
        </div>
        <div class="button-row">
          <button id="optimize" class="alt">Optimize</button>
          <button id="sync">Sync Workspaces</button>
        </div>
        <button id="launch" class="warn">Launch Lanes</button>
        <div class="muted">Tip: use <code>Refresh</code> and <code>Route Ask</code> repeatedly. Lane count comes from <code>config/codex_instances.json</code> (or <code>CCBS_CODEX_INSTANCES_CONFIG</code>).</div>
      </aside>

      <main class="panel workspace">
        <div id="status" class="status">Ready.</div>

        <section class="kpi-grid" aria-label="token telemetry">
          <article class="kpi">
            <div class="label">Availability</div>
            <div class="value" id="availabilityValue">0/0</div>
          </article>
          <article class="kpi">
            <div class="label">Daily Remaining</div>
            <div class="value" id="dailyRemaining">-</div>
          </article>
          <article class="kpi">
            <div class="label">Weekly Remaining</div>
            <div class="value" id="weeklyRemaining">-</div>
          </article>
          <article class="kpi">
            <div class="label">Paid Remaining</div>
            <div class="value" id="paidRemaining">-</div>
          </article>
        </section>

        <section>
          <h3>Lane Snapshot</h3>
          <div id="laneCards" class="lane-grid"></div>
        </section>

        <section class="grid2">
          <article>
            <h3>Last Route</h3>
            <table>
              <thead><tr><th>Lane</th><th>Directive</th><th>Task</th><th>Est Tokens</th></tr></thead>
              <tbody id="routeRows"></tbody>
            </table>
          </article>
          <article>
            <h3>Optimizer Decision</h3>
            <table>
              <thead><tr><th>Selected</th><th>Solver</th><th>Objective</th><th>Mode</th></tr></thead>
              <tbody id="decisionRows"></tbody>
            </table>
          </article>
        </section>

        <details open>
          <summary>Token Telemetry Table</summary>
          <table>
            <thead><tr><th>Window</th><th>Used</th><th>Budget</th><th>Remaining</th></tr></thead>
            <tbody id="tokenRows"></tbody>
          </table>
        </details>

        <details>
          <summary>App Capability Scan</summary>
          <table>
            <thead><tr><th>App</th><th>Installed</th><th>Multi</th><th>Score</th></tr></thead>
            <tbody id="appRows"></tbody>
          </table>
        </details>
      </main>
    </div>
  </div>

  <script>
    const tokenEl = document.getElementById('token');
    const statusEl = document.getElementById('status');
    const counterEl = document.getElementById('counter');
    const availabilityValueEl = document.getElementById('availabilityValue');
    const dailyRemainingEl = document.getElementById('dailyRemaining');
    const weeklyRemainingEl = document.getElementById('weeklyRemaining');
    const paidRemainingEl = document.getElementById('paidRemaining');
    const laneCardsEl = document.getElementById('laneCards');
    const appRows = document.getElementById('appRows');
    const decisionRows = document.getElementById('decisionRows');
    const routeRows = document.getElementById('routeRows');
    const tokenRows = document.getElementById('tokenRows');
    const parallelEl = document.getElementById('parallel');
    const askInputEl = document.getElementById('askInput');
    const taskLabelEl = document.getElementById('taskLabel');
    const applyUsageEl = document.getElementById('applyUsage');

    const TOKEN_STORAGE_KEY = 'ccbs_ai3_token';
    tokenEl.value = localStorage.getItem(TOKEN_STORAGE_KEY) || '';
    function persistToken() {
      const token = tokenEl.value.trim();
      if (token) {
        localStorage.setItem(TOKEN_STORAGE_KEY, token);
      } else {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
      }
    }
    tokenEl.addEventListener('input', persistToken);
    tokenEl.addEventListener('change', persistToken);

    function esc(value) {
      return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function authHeaders() {
      persistToken();
      const token = tokenEl.value.trim();
      return token ? { 'Authorization': 'Bearer ' + token } : {};
    }

    async function callJson(url, method='GET', body=null) {
      const headers = Object.assign({ 'Content-Type': 'application/json' }, authHeaders());
      const res = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined });
      const text = await res.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch (_err) { data = { raw: text }; }
      if (!res.ok) {
        throw new Error((data && data.detail) ? String(data.detail) : ('HTTP ' + res.status));
      }
      return data;
    }

	    function normalizeError(err) {
	      const msg = String(err && err.message ? err.message : err || 'unknown error');
	      if (msg.toLowerCase().includes('missing bearer token')) {
	        return "Auth required. Run `QB-doctor.bat -OpenUi` (enables loopback owner auto-auth), or paste a bearer token above and click Refresh.";
	      }
	      return msg;
	    }

    function setStatus(msg, kind='info') {
      statusEl.className = 'status' + (kind === 'error' ? ' error' : (kind === 'ok' ? ' ok' : ''));
      statusEl.textContent = msg;
    }

    function numericOrDash(value) {
      return value == null ? '-' : String(value);
    }

    function renderLanes(state) {
      const availability = String(state.availability_counter || '0/0');
      counterEl.textContent = availability;
      availabilityValueEl.textContent = availability;
      laneCardsEl.innerHTML = '';

      const lanes = Array.isArray(state.lanes) ? state.lanes : [];
      if (!lanes.length) {
        laneCardsEl.innerHTML = '<article class="lane-card down"><div class="lane-head"><strong>No lanes</strong><span class="lane-pill">down</span></div><div class="lane-meta">No lane metadata returned from runtime.</div></article>';
        return;
      }

      lanes.forEach((lane) => {
        const available = !!lane.available;
        const card = document.createElement('article');
        card.className = 'lane-card' + (available ? '' : ' down');
        card.innerHTML =
          '<div class="lane-head">' +
            '<strong>' + esc(lane.name || lane.instance_id || 'lane') + '</strong>' +
            '<span class="lane-pill">' + (available ? 'ready' : 'busy') + '</span>' +
          '</div>' +
          '<div class="lane-meta">Priority: ' + esc(lane.priority || '-') + '</div>' +
          '<div class="lane-meta">Directive: ' + esc(lane.directive || '-') + '</div>' +
          '<div class="lane-meta">Task: ' + esc(lane.active_task || '-') + '</div>';
        laneCardsEl.appendChild(card);
      });
    }

    function renderApps(payload) {
      appRows.innerHTML = '';
      (payload.apps || []).forEach((app) => {
        const tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + esc(app.name || '') + '</td>' +
          '<td>' + (app.installed ? 'yes' : 'no') + '</td>' +
          '<td>' + (app.supports_multi_instance ? 'yes' : 'no') + '</td>' +
          '<td>' + esc(app.ccbs_score || 0) + '</td>';
        appRows.appendChild(tr);
      });
    }

    function renderDecision(payload) {
      decisionRows.innerHTML = '';
      const selection = payload.selection || {};
      const selected = (selection.selected_tasks || []).join(', ');
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + esc(selected || '-') + '</td>' +
        '<td>' + esc(selection.solver_mode || '-') + '</td>' +
        '<td>' + esc(selection.objective_score == null ? '-' : selection.objective_score) + '</td>' +
        '<td>' + esc(selection.mode_requested || 'auto') + '</td>';
      decisionRows.appendChild(tr);
    }

    function renderRoute(payload) {
      routeRows.innerHTML = '';
      const lane = payload.lane_selected || {};
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + esc(lane.name || lane.instance_id || '-') + '</td>' +
        '<td>' + esc(payload.directive || lane.directive || '-') + '</td>' +
        '<td>' + esc(payload.task_assigned || '-') + '</td>' +
        '<td>' + esc(payload.estimated_tokens == null ? '-' : payload.estimated_tokens) + '</td>';
      routeRows.appendChild(tr);
    }

    function renderTokens(telemetry) {
      tokenRows.innerHTML = '';
      const daily = telemetry.daily || {};
      const weekly = telemetry.weekly || {};
      const paid = telemetry.paid || {};
      dailyRemainingEl.textContent = numericOrDash(daily.remaining_tokens);
      weeklyRemainingEl.textContent = numericOrDash(weekly.remaining_tokens);
      paidRemainingEl.textContent = numericOrDash(paid.remaining_tokens);

      const windows = [['daily', daily], ['weekly', weekly], ['paid', paid]];
      windows.forEach(([name, row]) => {
        const tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + esc(name) + '</td>' +
          '<td>' + esc(row.used_tokens == null ? '-' : row.used_tokens) + '</td>' +
          '<td>' + esc(row.budget_tokens == null ? '-' : row.budget_tokens) + '</td>' +
          '<td>' + esc(row.remaining_tokens == null ? 'n/a' : row.remaining_tokens) + '</td>';
        tokenRows.appendChild(tr);
      });
    }

    async function refreshAll() {
      setStatus('Loading multi-instance runtime...');
      try {
        const [runtime, apps] = await Promise.all([
          callJson('/v3/multi-instance/runtime'),
          callJson('/v3/multi-instance/apps'),
        ]);
        const state = runtime.state || {};
        renderLanes(state);
        renderApps(apps);
        renderTokens(runtime.token_telemetry || state.token_telemetry || {});
        setStatus('Runtime refreshed.', 'ok');
      } catch (err) {
        setStatus('Refresh failed: ' + normalizeError(err), 'error');
      }
    }

    document.getElementById('refresh').addEventListener('click', refreshAll);
    document.getElementById('sync').addEventListener('click', async () => {
      setStatus('Syncing workspaces...');
      try {
        const payload = await callJson('/v3/multi-instance/control', 'POST', { action: 'sync-workspaces' });
        renderLanes(payload.state || {});
        renderTokens((payload.state || {}).token_telemetry || {});
        setStatus('Sync complete. Created: ' + ((payload.created || []).join(', ') || 'none'), 'ok');
      } catch (err) {
        setStatus('Sync failed: ' + normalizeError(err), 'error');
      }
    });

    document.getElementById('launch').addEventListener('click', async () => {
      setStatus('Launching configured lanes...');
      try {
        const payload = await callJson('/v3/multi-instance/control', 'POST', { action: 'launch', confirmed: true });
        renderLanes(payload.state || {});
        renderTokens((payload.state || {}).token_telemetry || {});
        if (payload.ok) {
          setStatus('Launch complete.', 'ok');
        } else {
          setStatus('Launch failed: ' + String(payload.detail || payload.status || 'unknown'), 'error');
        }
      } catch (err) {
        setStatus('Launch failed: ' + normalizeError(err), 'error');
      }
    });

    document.getElementById('optimize').addEventListener('click', async () => {
      setStatus('Running optimizer...');
      try {
        const payload = await callJson('/v3/multi-instance/optimize', 'POST', {
          max_parallel: Number(parallelEl.value || '3'),
          mode: 'auto',
        });
        renderDecision(payload);
        renderLanes(payload.state || {});
        renderTokens((payload.state || {}).token_telemetry || {});
        setStatus('Optimizer completed.', 'ok');
      } catch (err) {
        setStatus('Optimizer failed: ' + normalizeError(err), 'error');
      }
    });

    document.getElementById('routeAsk').addEventListener('click', async () => {
      const message = String(askInputEl.value || '').trim();
      if (!message) {
        setStatus('Route Ask requires a message.', 'error');
        return;
      }
      setStatus('Routing ask...');
      try {
        const payload = await callJson('/v3/multi-instance/route', 'POST', {
          message,
          task_label: String(taskLabelEl.value || '').trim(),
          apply_usage: String(applyUsageEl.value || 'true') === 'true',
        });
        renderRoute(payload);
        renderLanes(payload.execution_view || {});
        renderTokens(payload.token_telemetry || {});
        setStatus('Routed to ' + ((payload.lane_selected || {}).name || 'lane') + '.', 'ok');
      } catch (err) {
        setStatus('Route failed: ' + normalizeError(err), 'error');
      }
    });

    refreshAll();
  </script>
</body>
</html>
"""
