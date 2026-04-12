"""Dedicated fluid chat-only UI for ai3."""

from __future__ import annotations

from .ui_shared import redesign_enabled, render_surface_html

def render_chat_ui_html() -> str:
    if redesign_enabled():
        return render_surface_html("chat-ui")
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CCBS Chat Only</title>
  <style>
    :root {
      --bg-1: #070b1f;
      --bg-2: #101b3f;
      --ink: #e9f5ff;
      --muted: #9cc5df;
      --accent: #3cf2ff;
      --accent-2: #7aff57;
      --panel: rgba(10, 20, 46, 0.88);
      --border: rgba(60, 242, 255, 0.32);
      --user: rgba(33, 79, 48, 0.65);
      --assistant: rgba(18, 37, 68, 0.72);
      --radius: 16px;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Rajdhani", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 12% 12%, rgba(122,255,87,0.16), transparent 30%),
        radial-gradient(circle at 84% 10%, rgba(60,242,255,0.18), transparent 30%),
        linear-gradient(155deg, var(--bg-1), var(--bg-2));
    }

    .app {
      max-width: 1320px;
      margin: 0 auto;
      min-height: 100vh;
      padding: 16px;
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 14px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: 0 14px 38px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(255,255,255,0.06);
      backdrop-filter: blur(4px);
    }

    .sidebar {
      padding: 14px;
      display: grid;
      align-content: start;
      gap: 10px;
      position: sticky;
      top: 14px;
      height: fit-content;
    }

    .title {
      padding: 10px;
      border-radius: 12px;
      border: 1px solid rgba(122,255,87,0.35);
      background: linear-gradient(135deg, rgba(60,242,255,0.14), rgba(122,255,87,0.12));
    }
    .title h1 {
      margin: 0;
      font-size: 20px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .title p {
      margin: 6px 0 0 0;
      color: var(--muted);
      font-size: 13px;
    }

    .field { display: grid; gap: 6px; }
    .label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.09em;
    }

    input, select, textarea {
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(4, 12, 30, 0.86);
      color: var(--ink);
      padding: 9px 10px;
      font: inherit;
    }
    textarea { min-height: 90px; resize: vertical; }
    input:focus, select:focus, textarea:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(60,242,255,0.18);
    }

    .row { display: flex; gap: 8px; flex-wrap: wrap; }
    button {
      border: 0;
      border-radius: 11px;
      padding: 9px 12px;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      cursor: pointer;
      background: linear-gradient(120deg, var(--accent), #89f7ff);
      color: #001c2a;
    }
    button.alt {
      background: linear-gradient(120deg, var(--accent-2), #bcff88);
      color: #082009;
    }

    .main {
      padding: 14px;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 10px;
      min-height: 82vh;
    }

    .status {
      border: 1px solid var(--border);
      border-radius: 11px;
      background: rgba(6, 16, 36, 0.74);
      color: var(--muted);
      padding: 10px;
      min-height: 40px;
      font-size: 13px;
    }
    .feed {
      border: 1px solid rgba(60,242,255,0.25);
      border-radius: 13px;
      background: rgba(3, 8, 23, 0.72);
      padding: 10px;
      overflow: auto;
      display: grid;
      gap: 8px;
      align-content: start;
    }

    .msg {
      padding: 10px;
      border-radius: 12px;
      white-space: pre-wrap;
      line-height: 1.4;
    }
    .msg.user {
      border: 1px solid rgba(122,255,87,0.42);
      background: var(--user);
    }
    .msg.assistant {
      border: 1px solid rgba(60,242,255,0.4);
      background: var(--assistant);
    }

    .composer {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px;
      background: rgba(8, 18, 42, 0.84);
      display: grid;
      gap: 8px;
    }

    .small {
      color: var(--muted);
      font-size: 12px;
    }

    @media (max-width: 1040px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { position: static; }
      .main { min-height: 70vh; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar panel">
      <div class="title">
        <h1>Chat Only</h1>
        <p>Fluid ask-me-anything mode with owner profile personalization.</p>
      </div>

      <div class="field">
        <label class="label" for="token">Bearer Token</label>
        <input id="token" placeholder="optional in owner auto-auth mode" autocomplete="off" />
      </div>

      <div class="field">
        <label class="label" for="model">Model</label>
        <select id="model"></select>
      </div>

      <div class="row">
        <label class="small"><input id="offlineOnly" type="checkbox" checked /> Offline only</label>
        <label class="small"><input id="allowRemote" type="checkbox" /> Allow remote</label>
      </div>

      <div class="field">
        <label class="label" for="displayName">Display Name</label>
        <input id="displayName" placeholder="Owner name" />
      </div>
      <div class="field">
        <label class="label" for="avatarStyle">Avatar Style</label>
        <select id="avatarStyle">
          <option value="nft-core">NFT Core</option>
          <option value="samurai">Samurai</option>
          <option value="strategist">Strategist</option>
          <option value="guardian">Guardian</option>
        </select>
      </div>
      <div class="field">
        <label class="label" for="theme">Theme</label>
        <select id="theme">
          <option value="neon-deck">Neon Deck</option>
          <option value="cyber-lime">Cyber Lime</option>
          <option value="ocean-core">Ocean Core</option>
        </select>
      </div>
      <div class="field">
        <label class="label" for="tonePreset">Tone Preset</label>
        <select id="tonePreset">
          <option value="balanced">Balanced</option>
          <option value="concise">Concise</option>
          <option value="coach">Coach</option>
          <option value="architect">Architect</option>
        </select>
      </div>

      <div class="row">
        <button id="saveProfile" type="button">Save Profile</button>
        <button id="newThread" class="alt" type="button">New Thread</button>
      </div>
      <div class="small" id="threadInfo">Thread: auto</div>
    </aside>

    <section class="main panel">
      <div id="status" class="status">Ready. Pick a model and ask anything.</div>
      <div id="feed" class="feed"></div>
      <div class="composer">
        <textarea id="prompt" placeholder="Ask me anything..."></textarea>
        <div class="row">
          <button id="send" type="button">Send</button>
          <button id="saveToken" class="alt" type="button">Save Token</button>
        </div>
      </div>
    </section>
  </div>

  <script>
    const state = {
      threadId: '',
      catalog: [],
    };

    const tokenInput = document.getElementById('token');
    const modelSelect = document.getElementById('model');
    const offlineOnly = document.getElementById('offlineOnly');
    const allowRemote = document.getElementById('allowRemote');
    const displayName = document.getElementById('displayName');
    const avatarStyle = document.getElementById('avatarStyle');
    const theme = document.getElementById('theme');
    const tonePreset = document.getElementById('tonePreset');
    const threadInfo = document.getElementById('threadInfo');
    const statusBox = document.getElementById('status');
    const feed = document.getElementById('feed');
    const promptInput = document.getElementById('prompt');
    const sendBtn = document.getElementById('send');

    tokenInput.value = localStorage.getItem('ccbs_ai3_token') || '';

    function setStatus(text, tone = 'info') {
      statusBox.textContent = text;
      if (tone === 'error') statusBox.style.borderColor = 'rgba(255, 89, 122, 0.6)';
      else if (tone === 'ok') statusBox.style.borderColor = 'rgba(122,255,87,0.55)';
      else statusBox.style.borderColor = 'var(--border)';
    }

    function applyTheme(kind) {
      const root = document.documentElement;
      if (kind === 'cyber-lime') {
        root.style.setProperty('--accent', '#98ff44');
        root.style.setProperty('--accent-2', '#3cf2ff');
      } else if (kind === 'ocean-core') {
        root.style.setProperty('--accent', '#59c6ff');
        root.style.setProperty('--accent-2', '#7affd8');
      } else {
        root.style.setProperty('--accent', '#3cf2ff');
        root.style.setProperty('--accent-2', '#7aff57');
      }
    }

    function push(role, text) {
      const el = document.createElement('div');
      el.className = `msg ${role}`;
      el.textContent = text;
      feed.appendChild(el);
      feed.scrollTop = feed.scrollHeight;
    }

    async function api(path, options = {}) {
      const headers = Object.assign({}, options.headers || {}, { 'Content-Type': 'application/json' });
      const token = tokenInput.value.trim();
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(path, Object.assign({}, options, { headers }));
      const text = await res.text();
      let payload = {};
      try { payload = text ? JSON.parse(text) : {}; } catch (_err) { payload = { raw: text }; }
      if (!res.ok) throw new Error(payload.detail || payload.error || JSON.stringify(payload));
      return payload;
    }

    function selectedModel() {
      const key = modelSelect.value;
      return state.catalog.find((item) => item.key === key) || null;
    }

    function renderModelOptions(models) {
      modelSelect.innerHTML = '';
      for (const item of models) {
        const opt = document.createElement('option');
        opt.value = item.key;
        const flag = item.reachable ? 'online' : 'offline';
        const src = Array.isArray(item.sources) ? item.sources.join(',') : item.source || '';
        opt.textContent = `${item.provider} :: ${item.model} (${flag}; ${src})`;
        modelSelect.appendChild(opt);
      }
      if (!models.length) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'extractive :: extractive';
        modelSelect.appendChild(opt);
      }
    }

    async function loadCatalog() {
      const out = await api('/v3/chat/models');
      state.catalog = out.models || [];
      renderModelOptions(state.catalog);
      if (out.default_model_key) modelSelect.value = out.default_model_key;
    }

    async function loadProfile() {
      const out = await api('/v3/chat/profile');
      const p = out.profile || {};
      displayName.value = p.display_name || 'Owner';
      avatarStyle.value = p.avatar_style || 'nft-core';
      theme.value = p.theme || 'neon-deck';
      tonePreset.value = p.tone_preset || 'balanced';
      applyTheme(theme.value);
      if (p.preferred_model) modelSelect.value = p.preferred_model;
    }

    async function saveProfile() {
      const body = {
        display_name: displayName.value.trim(),
        avatar_style: avatarStyle.value,
        theme: theme.value,
        preferred_model: modelSelect.value,
        tone_preset: tonePreset.value,
      };
      const out = await api('/v3/chat/profile', { method: 'POST', body: JSON.stringify(body) });
      applyTheme((out.profile || {}).theme || theme.value);
      setStatus('profile saved', 'ok');
    }

    async function sendPrompt() {
      const text = promptInput.value.trim();
      if (!text) return;
      const model = selectedModel();
      sendBtn.disabled = true;
      push('user', text);
      setStatus('running...', 'info');
      try {
        const out = await api('/v3/chat/send', {
          method: 'POST',
          body: JSON.stringify({
            thread_id: state.threadId || '',
            message: text,
            model_key: model ? model.key : '',
            provider: model ? model.provider : '',
            model: model ? model.model : '',
            base_url: model ? model.base_url : '',
            offline_only: !!offlineOnly.checked,
            allow_remote: !!allowRemote.checked,
            top_k: 5,
          }),
        });
        state.threadId = out.thread_id || state.threadId;
        threadInfo.textContent = `Thread: ${state.threadId || 'auto'}`;
        const reply = (out.assistant_message && out.assistant_message.content) || out.answer || '';
        if (reply) push('assistant', reply);
        setStatus(`run ${out.run_status || 'completed'} via ${out.provider_used || 'local'}`, 'ok');
      } catch (err) {
        setStatus(`error: ${err.message}`, 'error');
      } finally {
        sendBtn.disabled = false;
      }
    }

    async function newThread() {
      state.threadId = '';
      threadInfo.textContent = 'Thread: auto';
      feed.innerHTML = '';
      setStatus('new thread session ready', 'ok');
    }

    document.getElementById('saveToken').addEventListener('click', () => {
      localStorage.setItem('ccbs_ai3_token', tokenInput.value.trim());
      setStatus('token saved', 'ok');
    });
    document.getElementById('saveProfile').addEventListener('click', () => saveProfile().catch((err) => setStatus(`error: ${err.message}`, 'error')));
    document.getElementById('send').addEventListener('click', () => sendPrompt());
    document.getElementById('newThread').addEventListener('click', () => newThread());
    theme.addEventListener('change', () => applyTheme(theme.value));
    promptInput.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') sendPrompt();
    });

    (async () => {
      try {
        await loadCatalog();
        await loadProfile();
        setStatus('chat-only mode ready', 'ok');
      } catch (err) {
        setStatus(`startup error: ${err.message}`, 'error');
      }
    })();
  </script>
</body>
</html>
"""
