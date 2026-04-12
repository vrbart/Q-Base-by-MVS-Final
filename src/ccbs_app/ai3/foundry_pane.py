"""Dedicated Foundry lane pane for ai3.

Renders a focused, self-contained page wired to /v3/chat/foundry-gate.
BLOCKED state: shows reason + next_actions + fix guidance.
READY state: shows model/provider info + prompt area for remote_allowed scope.
"""

from __future__ import annotations


def render_foundry_pane_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CCBS Foundry Lane</title>
  <style>
    :root {
      --bg-1: #070b1f;
      --bg-2: #0d1530;
      --ink: #e9f5ff;
      --muted: #9cc5df;
      --accent: #3cf2ff;
      --accent-2: #7aff57;
      --warn: #ffb347;
      --danger: #ff4f6a;
      --panel: rgba(10, 20, 46, 0.92);
      --border: rgba(60, 242, 255, 0.28);
      --border-ready: rgba(122, 255, 87, 0.40);
      --border-blocked: rgba(255, 79, 106, 0.40);
      --radius: 14px;
      --font: 'Segoe UI', system-ui, sans-serif;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; background: var(--bg-1); color: var(--ink); font-family: var(--font); font-size: 14px; }
    body { display: flex; flex-direction: column; min-height: 100vh; }

    header {
      padding: 14px 20px 10px;
      border-bottom: 1px solid var(--border);
      background: var(--bg-2);
    }
    header h1 { font-size: 1.1rem; color: var(--accent); letter-spacing: .04em; }
    header .sub { font-size: .78rem; color: var(--muted); margin-top: 2px; }

    .token-bar {
      padding: 8px 20px;
      background: var(--bg-2);
      border-bottom: 1px solid var(--border);
      display: flex; gap: 8px; align-items: center;
    }
    .token-bar input {
      flex: 1; background: transparent; border: 1px solid var(--border);
      color: var(--ink); padding: 5px 8px; border-radius: 6px; font-size: .82rem;
    }
    .token-bar button {
      background: transparent; border: 1px solid var(--border); color: var(--accent);
      padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: .82rem;
    }
    .token-bar button:hover { background: rgba(60,242,255,.08); }

    main { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 16px; max-width: 820px; width: 100%; }

    .gate-card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 18px 20px;
    }
    .gate-card.ready { border-color: var(--border-ready); }
    .gate-card.blocked { border-color: var(--border-blocked); }

    .gate-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .gate-badge {
      font-size: .72rem; font-weight: 700; letter-spacing: .06em; padding: 3px 9px;
      border-radius: 20px; text-transform: uppercase;
    }
    .gate-badge.ready { background: rgba(122,255,87,.15); color: var(--accent-2); border: 1px solid var(--accent-2); }
    .gate-badge.blocked { background: rgba(255,79,106,.13); color: var(--danger); border: 1px solid var(--danger); }
    .gate-badge.loading { background: rgba(60,242,255,.10); color: var(--accent); border: 1px solid var(--accent); }

    .gate-title { font-size: .92rem; font-weight: 600; color: var(--ink); }
    .gate-reason { font-size: .82rem; color: var(--warn); margin-bottom: 10px; line-height: 1.5; }
    .gate-meta { font-size: .78rem; color: var(--muted); margin-bottom: 10px; line-height: 1.6; }
    .gate-meta span { color: var(--accent); }

    .actions-list { list-style: none; display: flex; flex-direction: column; gap: 5px; }
    .actions-list li {
      font-size: .8rem; color: var(--muted); padding: 6px 10px;
      background: rgba(255,255,255,.03); border-radius: 6px; border: 1px solid rgba(255,255,255,.06);
    }
    .actions-list li code { color: var(--accent); font-family: 'Consolas', monospace; }

    .prompt-section { display: flex; flex-direction: column; gap: 10px; }
    .prompt-section label { font-size: .8rem; color: var(--muted); }
    textarea {
      background: rgba(255,255,255,.04); border: 1px solid var(--border);
      color: var(--ink); border-radius: 8px; padding: 10px 12px;
      font-size: .88rem; font-family: var(--font); resize: vertical; min-height: 100px;
      line-height: 1.5;
    }
    textarea:focus { outline: none; border-color: var(--accent); }

    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    button {
      background: transparent; border: 1px solid var(--accent); color: var(--accent);
      padding: 7px 16px; border-radius: 8px; cursor: pointer; font-size: .84rem;
      transition: background .15s;
    }
    button:hover { background: rgba(60,242,255,.10); }
    button:disabled { opacity: .4; cursor: default; }
    button.warn { border-color: var(--warn); color: var(--warn); }
    button.warn:hover { background: rgba(255,179,71,.10); }
    button.alt { border-color: var(--muted); color: var(--muted); }
    button.alt:hover { background: rgba(156,197,223,.08); }

    .status {
      font-size: .82rem; padding: 8px 12px; border-radius: 6px;
      border: 1px solid var(--border); min-height: 34px;
    }
    .status.error { border-color: var(--danger); color: var(--danger); background: rgba(255,79,106,.08); }
    .status.ok { border-color: var(--accent-2); color: var(--accent-2); background: rgba(122,255,87,.07); }

    .answer-box {
      background: rgba(255,255,255,.03); border: 1px solid var(--border); border-radius: 8px;
      padding: 12px 14px; font-size: .86rem; line-height: 1.6; white-space: pre-wrap;
      min-height: 60px; max-height: 380px; overflow-y: auto; color: var(--ink);
    }

    .loading-pulse { animation: pulse 1.2s ease-in-out infinite; }
    @keyframes pulse { 0%,100% { opacity:.4; } 50% { opacity:1; } }

    pre.trace {
      background: rgba(0,0,0,.25); border: 1px solid rgba(255,255,255,.07);
      border-radius: 6px; padding: 8px 10px; font-size: .75rem; font-family: 'Consolas', monospace;
      color: var(--muted); white-space: pre-wrap; max-height: 180px; overflow-y: auto;
    }
  </style>
</head>
<body>
  <header>
    <h1>CCBS Foundry Lane</h1>
    <div class="sub">ai3-foundry-gate-v1 &mdash; Binary gate: local tools must be ready before Foundry opens.</div>
  </header>
  <div class="token-bar">
    <label for="tokenInput" style="font-size:.78rem;color:var(--muted);white-space:nowrap;">Bearer Token</label>
    <input id="tokenInput" type="password" placeholder="Paste API token (optional in owner auto-auth mode)" autocomplete="off" />
    <button id="refreshBtn" type="button">Refresh Gate</button>
    <button id="openMainUiBtn" type="button" class="alt">Main UI</button>
  </div>
  <main>
    <div id="gateCard" class="gate-card">
      <div class="gate-header">
        <span id="gateBadge" class="gate-badge loading">Loading&hellip;</span>
        <span class="gate-title">Foundry Lane Gate</span>
      </div>
      <div id="gateReason" class="gate-reason" style="display:none;"></div>
      <div id="gateMeta" class="gate-meta"></div>
      <ul id="actionsList" class="actions-list" style="display:none;"></ul>
    </div>

    <div id="promptSection" class="gate-card prompt-section" style="display:none;">
      <label for="promptInput">Prompt (remote_allowed scope &mdash; Foundry model)</label>
      <textarea id="promptInput" placeholder="Ask the Foundry model..."></textarea>
      <div class="row">
        <button id="sendBtn" type="button">Send to Foundry</button>
        <button id="clearBtn" type="button" class="alt">Clear</button>
      </div>
      <div id="statusBox" class="status" style="display:none;"></div>
      <div id="answerBox" class="answer-box" style="display:none;"></div>
      <pre id="traceBox" class="trace" style="display:none;"></pre>
    </div>
  </main>

  <script>
    (function () {
      'use strict';

      const API_BASE = window.location.origin;

      function token() {
        const v = document.getElementById('tokenInput').value.trim();
        if (v) return v;
        try { return localStorage.getItem('ccbs_token') || ''; } catch { return ''; }
      }

      function saveToken(t) {
        try { if (t) localStorage.setItem('ccbs_token', t); } catch {}
      }

      async function api(path, opts) {
        const t = token();
        const headers = { 'Content-Type': 'application/json' };
        if (t) headers['Authorization'] = 'Bearer ' + t;
        const resp = await fetch(API_BASE + path, { ...opts, headers: { ...headers, ...(opts && opts.headers || {}) } });
        if (!resp.ok) {
          let msg = resp.statusText;
          try { const j = await resp.json(); msg = j.detail || j.error || msg; } catch {}
          throw new Error(msg);
        }
        return resp.json();
      }

      const gateCard = document.getElementById('gateCard');
      const gateBadge = document.getElementById('gateBadge');
      const gateReason = document.getElementById('gateReason');
      const gateMeta = document.getElementById('gateMeta');
      const actionsList = document.getElementById('actionsList');
      const promptSection = document.getElementById('promptSection');
      const statusBox = document.getElementById('statusBox');
      const answerBox = document.getElementById('answerBox');
      const traceBox = document.getElementById('traceBox');

      function setStatus(msg, kind) {
        statusBox.style.display = msg ? '' : 'none';
        statusBox.className = 'status' + (kind === 'error' ? ' error' : kind === 'ok' ? ' ok' : '');
        statusBox.textContent = msg || '';
      }

      async function loadGate() {
        gateBadge.textContent = 'Loading\u2026';
        gateBadge.className = 'gate-badge loading loading-pulse';
        gateReason.style.display = 'none';
        actionsList.style.display = 'none';
        promptSection.style.display = 'none';
        gateMeta.textContent = '';

        try {
          const data = await api('/v3/chat/foundry-gate');
          const fg = data.foundry_gate || {};
          const ready = !!fg.pane_enabled;

          gateCard.className = 'gate-card ' + (ready ? 'ready' : 'blocked');
          gateBadge.className = 'gate-badge ' + (ready ? 'ready' : 'blocked');
          gateBadge.textContent = ready ? 'READY' : 'BLOCKED';

          const metaParts = [];
          metaParts.push('Contract: ' + (fg.contract_version || 'ai3-foundry-gate-v1'));
          metaParts.push('Lane: ' + (fg.lane_id || 'foundry'));
          metaParts.push('Phase: ' + (fg.phase || 'future'));
          metaParts.push('Provider: ' + (fg.provider_id || 'remote2'));
          metaParts.push('Model: ' + (fg.configured_model || 'gpt-5-mini'));
          metaParts.push('Local tools ready: ' + (fg.local_tools_ready ? 'YES' : 'NO'));
          metaParts.push('Classical fallback required: ' + (fg.classical_fallback_required ? 'YES' : 'NO'));
          gateMeta.innerHTML = metaParts.map(s => {
            const [k, v] = s.split(': ');
            return '<span style="color:var(--muted)">' + k + ': </span><span>' + v + '</span>';
          }).join('&emsp;');

          if (!ready && fg.reason) {
            gateReason.textContent = fg.reason;
            gateReason.style.display = '';
          }

          const actions = Array.isArray(fg.next_actions) ? fg.next_actions : [];
          if (!ready && actions.length) {
            actionsList.innerHTML = '';
            for (const a of actions) {
              const li = document.createElement('li');
              li.innerHTML = 'Fix action: <code>' + String(a).replace(/</g, '&lt;') + '</code>';
              actionsList.appendChild(li);
            }
            actionsList.style.display = '';
          }

          if (ready) {
            promptSection.style.display = '';
            const t = document.getElementById('tokenInput').value.trim();
            if (t) saveToken(t);
          }
        } catch (err) {
          gateCard.className = 'gate-card blocked';
          gateBadge.className = 'gate-badge blocked';
          gateBadge.textContent = 'ERROR';
          gateReason.textContent = 'Failed to fetch gate state: ' + (err.message || String(err));
          gateReason.style.display = '';
        }
      }

      document.getElementById('refreshBtn').addEventListener('click', loadGate);
      document.getElementById('openMainUiBtn').addEventListener('click', () => {
        window.location.href = API_BASE + '/v3/ui';
      });

      document.getElementById('sendBtn').addEventListener('click', async () => {
        const msg = document.getElementById('promptInput').value.trim();
        if (!msg) { setStatus('Enter a prompt first.', 'error'); return; }
        document.getElementById('sendBtn').disabled = true;
        setStatus('Sending to Foundry\u2026', '');
        answerBox.style.display = 'none';
        traceBox.style.display = 'none';

        try {
          const result = await api('/v3/chat/send', {
            method: 'POST',
            body: JSON.stringify({
              message: msg,
              answer_scope: 'remote_allowed',
              top_k: 5,
              ui_surface: 'foundry-ui'
            })
          });
          setStatus('', '');
          const answer = result.answer || result.message || JSON.stringify(result);
          answerBox.textContent = answer;
          answerBox.style.display = '';
          const trace = result.trace || result.route_trace || null;
          if (trace) {
            traceBox.textContent = typeof trace === 'string' ? trace : JSON.stringify(trace, null, 2);
            traceBox.style.display = '';
          }
        } catch (err) {
          setStatus('Foundry send failed: ' + (err.message || String(err)), 'error');
        } finally {
          document.getElementById('sendBtn').disabled = false;
        }
      });

      document.getElementById('clearBtn').addEventListener('click', () => {
        document.getElementById('promptInput').value = '';
        answerBox.style.display = 'none';
        traceBox.style.display = 'none';
        setStatus('', '');
      });

      // Restore token from storage
      try {
        const stored = localStorage.getItem('ccbs_token');
        if (stored) document.getElementById('tokenInput').value = stored;
      } catch {}

      // Auto-load on open
      loadGate();
    })();
  </script>
</body>
</html>
"""
