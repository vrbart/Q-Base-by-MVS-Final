"""Neon pixel-inspired GUI for ai3 runtime."""

from __future__ import annotations

from .ui_shared import redesign_enabled, render_surface_html

def render_ai3_gui_html() -> str:
    if redesign_enabled():
        return render_surface_html("ui")
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>CCBS ai3 Neon Console</title>
  <style>
    :root {
      --bg: #07081a;
      --bg-2: #0b0f2a;
      --ink: #d9eeff;
      --muted: #8ab4d8;
      --cyan: #2fe7ff;
      --electric: #55ff7a;
      --orange: #ff7d26;
      --pink: #ff35d8;
      --violet: #8d5dff;
      --frame: rgba(47, 231, 255, 0.28);
      --panel: rgba(10, 14, 36, 0.84);
      --danger: #ff5d6e;
      --ok: #46ff9a;
      --card-radius: 18px;
      --speed: 240ms;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: "Orbitron", "Rajdhani", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 18% 20%, rgba(141, 93, 255, 0.24), transparent 42%),
        radial-gradient(circle at 84% 14%, rgba(47, 231, 255, 0.18), transparent 35%),
        radial-gradient(circle at 50% 82%, rgba(85, 255, 122, 0.12), transparent 44%),
        linear-gradient(160deg, var(--bg), var(--bg-2));
      overflow-x: hidden;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image: radial-gradient(rgba(255,255,255,0.35) 0.6px, transparent 0.6px);
      background-size: 3px 3px;
      opacity: 0.18;
      mix-blend-mode: screen;
    }

    .app {
      max-width: 1300px;
      margin: 0 auto;
      padding: 20px;
      display: grid;
      gap: 18px;
      grid-template-columns: 350px 1fr;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--frame);
      border-radius: var(--card-radius);
      box-shadow: 0 0 0 1px rgba(255,255,255,0.06) inset, 0 14px 38px rgba(0,0,0,0.45);
      backdrop-filter: blur(6px);
    }

    .left {
      padding: 16px;
      display: grid;
      gap: 14px;
      align-content: start;
      position: sticky;
      top: 12px;
      height: fit-content;
    }

    .logo {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px;
      border-radius: 14px;
      background: linear-gradient(135deg, rgba(47,231,255,0.18), rgba(255,53,216,0.16));
      border: 1px solid rgba(47, 231, 255, 0.32);
    }

    .logo-badge {
      width: 52px;
      height: 52px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      color: #0c111f;
      font-size: 26px;
      font-weight: 900;
      background: radial-gradient(circle at 40% 30%, #e063ff, var(--pink));
      box-shadow: 0 0 18px rgba(255, 53, 216, 0.68);
    }

    h1 {
      margin: 0;
      font-size: 17px;
      line-height: 1.2;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .sub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.03em;
    }

    .field {
      display: grid;
      gap: 6px;
    }

    .label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
    }

    input, textarea {
      width: 100%;
      border: 1px solid rgba(47,231,255,0.35);
      background: rgba(6, 10, 26, 0.88);
      color: var(--ink);
      border-radius: 12px;
      padding: 10px 11px;
      font: inherit;
      transition: border-color var(--speed) ease, box-shadow var(--speed) ease;
    }

    textarea {
      min-height: 88px;
      resize: vertical;
    }

    input:focus, textarea:focus {
      outline: none;
      border-color: var(--cyan);
      box-shadow: 0 0 0 3px rgba(47, 231, 255, 0.2);
    }

    .row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    button {
      border: 0;
      border-radius: 11px;
      padding: 9px 12px;
      color: #061226;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      cursor: pointer;
      transition: transform var(--speed) ease, filter var(--speed) ease;
      background: linear-gradient(120deg, var(--cyan), #7cfbff);
    }

    button.alt {
      color: #011708;
      background: linear-gradient(120deg, var(--electric), #baff76);
    }

    button.warn {
      color: #220008;
      background: linear-gradient(120deg, #ff8b99, #ff6e82);
    }

    button:disabled {
      opacity: 0.6;
      cursor: wait;
      transform: none;
    }

    button:hover:not(:disabled) {
      transform: translateY(-1px);
      filter: brightness(1.05);
    }

    .toggle {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .main {
      display: grid;
      gap: 16px;
      align-content: start;
    }

    .hero {
      padding: 16px;
      overflow: hidden;
    }

    .cards {
      display: grid;
      grid-template-columns: repeat(3, minmax(120px, 1fr));
      gap: 14px;
      align-items: center;
    }

    .nft {
      position: relative;
      min-height: 210px;
      border-radius: 18px;
      border: 2px solid rgba(47,231,255,0.68);
      background:
        linear-gradient(140deg, rgba(10,15,45,0.95), rgba(19,34,74,0.78)),
        linear-gradient(60deg, rgba(85,255,122,0.38), rgba(141,93,255,0.32), rgba(255,125,38,0.34));
      box-shadow: 0 0 0 1px rgba(255,255,255,0.08) inset, 0 12px 36px rgba(0,0,0,0.4), 0 0 26px rgba(47,231,255,0.22);
      padding: 12px;
      display: grid;
      align-content: space-between;
      transform-origin: center;
      transition: transform var(--speed) ease, box-shadow var(--speed) ease;
      animation: cardFloat 6.4s ease-in-out infinite;
    }

    .nft:nth-child(1) { border-color: rgba(255,125,38,0.7); animation-delay: 0.0s; }
    .nft:nth-child(2) { border-color: rgba(255,53,216,0.8); animation-delay: 0.2s; }
    .nft:nth-child(3) { border-color: rgba(255,125,38,0.7); animation-delay: 0.4s; }
    .nft:nth-child(4) { border-color: rgba(85,255,122,0.85); animation-delay: 0.6s; }
    .nft:nth-child(5) { border-color: rgba(85,255,122,0.85); animation-delay: 0.8s; }

    .nft:hover {
      transform: translateY(-4px) scale(1.01);
      box-shadow: 0 16px 40px rgba(0,0,0,0.45), 0 0 36px rgba(47,231,255,0.34);
    }

    .nft.center {
      min-height: 250px;
      border-radius: 999px;
      border-color: rgba(255,53,216,0.9);
      place-items: center;
      text-align: center;
      animation: pulseCore 2.6s ease-in-out infinite;
      background:
        radial-gradient(circle at center, rgba(255, 53, 216, 0.26), rgba(10,15,45,0.92) 60%),
        linear-gradient(130deg, rgba(47,231,255,0.18), rgba(255,53,216,0.2));
    }

    .icon {
      width: 84px;
      height: 84px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      font-size: 48px;
      font-weight: 900;
      color: #020710;
      background: radial-gradient(circle at 30% 24%, #fff36f, #8dff4f 50%, #45e365 100%);
      border: 6px solid #101522;
      margin: 0 auto;
      image-rendering: pixelated;
    }

    .nft.center .icon {
      width: 100px;
      height: 100px;
      font-size: 56px;
      background: radial-gradient(circle at 38% 28%, #ff67f4, #ff35d8 60%, #b42df2 100%);
      color: #071128;
    }

    .nft-id {
      font-size: 12px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #cde8ff;
      opacity: 0.9;
      text-align: center;
    }

    .nft-name {
      margin-top: 8px;
      font-size: 13px;
      text-align: center;
      letter-spacing: 0.06em;
      color: #f4fbff;
    }

    .console {
      padding: 14px;
      display: grid;
      gap: 12px;
      min-height: 430px;
      grid-template-rows: auto auto 1fr;
    }

    .status {
      padding: 10px 11px;
      border-radius: 10px;
      border: 1px solid rgba(47,231,255,0.34);
      background: rgba(5, 15, 33, 0.64);
      color: var(--muted);
      font-size: 12px;
      min-height: 42px;
    }

    .feed {
      border: 1px solid rgba(47,231,255,0.25);
      border-radius: 12px;
      padding: 10px;
      background: rgba(5, 9, 25, 0.58);
      overflow: auto;
      min-height: 220px;
      max-height: 360px;
      display: grid;
      gap: 8px;
      align-content: start;
    }

    .msg {
      border-radius: 10px;
      padding: 9px 10px;
      font-size: 13px;
      line-height: 1.4;
      white-space: pre-wrap;
    }

    .msg.user {
      border: 1px solid rgba(85,255,122,0.42);
      background: rgba(8, 38, 17, 0.55);
    }

    .msg.assistant {
      border: 1px solid rgba(47,231,255,0.42);
      background: rgba(6, 19, 35, 0.58);
    }

    .steps {
      border: 1px solid rgba(255,53,216,0.28);
      border-radius: 12px;
      padding: 10px;
      background: rgba(19, 8, 28, 0.42);
      min-height: 100px;
      font-size: 12px;
      color: var(--muted);
      overflow: auto;
      max-height: 180px;
    }

    .step-ok { color: var(--ok); }
    .step-warn { color: #ffd678; }
    .step-fail { color: var(--danger); }

    @keyframes cardFloat {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-4px); }
    }

    @keyframes pulseCore {
      0%, 100% { box-shadow: 0 0 22px rgba(255,53,216,0.4), 0 0 0 1px rgba(255,255,255,0.12) inset; }
      50% { box-shadow: 0 0 38px rgba(255,53,216,0.6), 0 0 0 1px rgba(255,255,255,0.16) inset; }
    }

    @media (max-width: 1080px) {
      .app { grid-template-columns: 1fr; }
      .left { position: static; }
    }

    @media (max-width: 760px) {
      .cards { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .nft.center { grid-column: 1 / -1; min-height: 220px; }
    }
  </style>
</head>
<body>
  <div class=\"app\">
    <section class=\"left panel\">
      <div class=\"logo\">
        <div class=\"logo-badge\">✕</div>
        <div>
          <h1>CCBS ai3 Command Deck</h1>
          <div class=\"sub\">Neon fluid GUI inspired by your NFT card style</div>
        </div>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"token\">Bearer Token (optional in owner auto-auth mode)</label>
        <input id=\"token\" placeholder=\"paste API token (optional)\" autocomplete=\"off\" />
      </div>

      <div class=\"row\">
        <button id=\"saveToken\" type=\"button\">Save Token</button>
        <button id=\"newThread\" class=\"alt\" type=\"button\">New Thread</button>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"threadId\">Thread ID</label>
        <input id=\"threadId\" placeholder=\"auto-created\" readonly />
      </div>

      <label class=\"toggle\"><input id=\"offlineOnly\" type=\"checkbox\" checked /> Offline-only (local only)</label>
      <label class=\"toggle\"><input id=\"allowRemote\" type=\"checkbox\" /> Allow remote escalation</label>

      <div class=\"field\">
        <label class=\"label\" for=\"prompt\">Prompt</label>
        <textarea id=\"prompt\" placeholder=\"Ask ai3 a question...\"></textarea>
      </div>

      <div class=\"row\">
        <button id=\"send\" type=\"button\">Run</button>
        <button id=\"approveAll\" class=\"warn\" type=\"button\">Approve Pending</button>
      </div>
    </section>

    <section class=\"main\">
      <div class=\"hero panel\">
        <div class=\"cards\">
          <article class=\"nft\"><div class=\"icon\">⚔</div><div class=\"nft-name\">Strategist</div><div class=\"nft-id\">#137</div></article>
          <article class=\"nft center\"><div class=\"icon\">✕</div><div class=\"nft-name\">Core Agent</div><div class=\"nft-id\">#49</div></article>
          <article class=\"nft\"><div class=\"icon\">⛩</div><div class=\"nft-name\">Guardian</div><div class=\"nft-id\">#166</div></article>
          <article class=\"nft\"><div class=\"icon\">💼</div><div class=\"nft-name\">Ops</div><div class=\"nft-id\">#50</div></article>
          <article class=\"nft\"><div class=\"icon\">🌿</div><div class=\"nft-name\">Retriever</div><div class=\"nft-id\">#35</div></article>
        </div>
      </div>

      <div class=\"console panel\">
        <div id=\"status\" class=\"status\">Ready. Create a thread or send a prompt.</div>
        <div id=\"feed\" class=\"feed\"></div>
        <div id=\"steps\" class=\"steps\">No run yet.</div>
      </div>
    </section>
  </div>

  <script>
    const tokenInput = document.getElementById('token');
    const threadInput = document.getElementById('threadId');
    const promptInput = document.getElementById('prompt');
    const statusBox = document.getElementById('status');
    const feed = document.getElementById('feed');
    const steps = document.getElementById('steps');
    const offlineOnly = document.getElementById('offlineOnly');
    const allowRemote = document.getElementById('allowRemote');
    const sendBtn = document.getElementById('send');

    const state = {
      threadId: '',
      pendingApprovals: [],
    };

    tokenInput.value = localStorage.getItem('ccbs_ai3_token') || '';

    function setStatus(text, tone = 'info') {
      statusBox.textContent = text;
      statusBox.style.borderColor = tone === 'error' ? 'rgba(255,93,110,0.5)' : tone === 'ok' ? 'rgba(70,255,154,0.45)' : 'rgba(47,231,255,0.34)';
    }

    function pushMessage(role, text) {
      const el = document.createElement('div');
      el.className = `msg ${role}`;
      el.textContent = text;
      feed.appendChild(el);
      feed.scrollTop = feed.scrollHeight;
    }

    function renderSteps(runData) {
      const run = runData?.run || {};
      const rows = runData?.steps || [];
      if (!rows.length) {
        steps.textContent = run.status ? `run ${run.run_id} status=${run.status}` : 'No run steps yet.';
        return;
      }
      const lines = [`run ${run.run_id} status=${run.status}`];
      for (const row of rows) {
        const mark = row.status === 'completed' ? 'step-ok' : row.status === 'requires_action' ? 'step-warn' : 'step-fail';
        lines.push(`${row.step_index}. ${row.step_type} :: %${mark}%${row.status}%`);
      }
      steps.innerHTML = lines
        .map((line) => line.replace(/%(step-[a-z]+)%(.+?)%/g, '<span class="$1">$2</span>'))
        .join('<br/>');
    }

    async function api(path, options = {}) {
      const token = tokenInput.value.trim();
      const headers = Object.assign({}, options.headers || {}, { 'Content-Type': 'application/json' });
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const res = await fetch(path, Object.assign({}, options, { headers }));
      const text = await res.text();
      let payload = {};
      try { payload = text ? JSON.parse(text) : {}; } catch (err) { payload = { raw: text }; }
      if (!res.ok) {
        throw new Error(payload.detail || payload.error || JSON.stringify(payload));
      }
      return payload;
    }

    async function ensureThread() {
      if (state.threadId) return state.threadId;
      const out = await api('/v3/threads', {
        method: 'POST',
        body: JSON.stringify({ title: 'GUI Session', tags: ['gui', 'neon'] }),
      });
      state.threadId = out.thread.thread_id;
      threadInput.value = state.threadId;
      setStatus(`thread created: ${state.threadId}`, 'ok');
      return state.threadId;
    }

    async function newThread() {
      state.threadId = '';
      state.pendingApprovals = [];
      feed.innerHTML = '';
      steps.textContent = 'No run yet.';
      await ensureThread();
    }

    async function sendPrompt() {
      const prompt = promptInput.value.trim();
      if (!prompt) return;

      sendBtn.disabled = true;
      setStatus('running...', 'info');
      pushMessage('user', prompt);

      try {
        const threadId = await ensureThread();
        await api(`/v3/threads/${threadId}/messages`, {
          method: 'POST',
          body: JSON.stringify({ role: 'user', content: prompt }),
        });

        const runOut = await api('/v3/runs', {
          method: 'POST',
          body: JSON.stringify({
            thread_id: threadId,
            execute: true,
            top_k: 5,
            offline_only: !!offlineOnly.checked,
            allow_remote: !!allowRemote.checked,
          }),
        });

        state.pendingApprovals = runOut.requires_action || [];
        renderSteps(runOut);

        const assistant = runOut.assistant_message?.content || runOut.taskmaster?.answer || '';
        if (assistant) pushMessage('assistant', assistant);

        if (state.pendingApprovals.length) {
          setStatus(`run paused for approval (${state.pendingApprovals.length} pending)`, 'error');
        } else {
          setStatus(`run ${runOut.run?.status || 'completed'}`, 'ok');
        }
      } catch (err) {
        setStatus(`error: ${err.message}`, 'error');
      } finally {
        sendBtn.disabled = false;
      }
    }

    async function approveAll() {
      if (!state.pendingApprovals.length) {
        setStatus('no pending approvals', 'info');
        return;
      }
      setStatus('approving pending tool calls...', 'info');
      try {
        let lastRun = null;
        for (const row of state.pendingApprovals) {
          const out = await api(`/v3/tool-calls/${row.tool_call_id}/approvals`, {
            method: 'POST',
            body: JSON.stringify({ decision: 'approved', resume: true, allow_remote: !!allowRemote.checked }),
          });
          if (out.run_id) {
            lastRun = out;
          }
        }
        state.pendingApprovals = [];
        if (lastRun && lastRun.run) {
          renderSteps({ run: lastRun.run, steps: lastRun.steps || [] });
          setStatus(`run resumed: ${lastRun.run.status}`, 'ok');
        } else {
          setStatus('approvals applied', 'ok');
        }
      } catch (err) {
        setStatus(`approval error: ${err.message}`, 'error');
      }
    }

    document.getElementById('saveToken').addEventListener('click', () => {
      localStorage.setItem('ccbs_ai3_token', tokenInput.value.trim());
      setStatus('token saved in browser storage', 'ok');
    });
    document.getElementById('newThread').addEventListener('click', () => newThread().catch((err) => setStatus(`error: ${err.message}`, 'error')));
    document.getElementById('send').addEventListener('click', () => sendPrompt());
    document.getElementById('approveAll').addEventListener('click', () => approveAll());

    promptInput.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') sendPrompt();
    });
  </script>
</body>
</html>
"""
