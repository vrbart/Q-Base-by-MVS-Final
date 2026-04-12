"""Shared HTML/CSS/JS renderer for ui and chat-ui surfaces."""

from __future__ import annotations

import os


def _flag_enabled(name: str, default: bool = True) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _shared_css() -> str:
    return """
    :root {
      --bg-1: #07091b;
      --bg-2: #0d1536;
      --bg-3: #0a1028;
      --ink: #e8f5ff;
      --muted: #93bdd9;
      --cyan: #3df0ff;
      --lime: #8eff5f;
      --pink: #ff4ddb;
      --orange: #ff9c47;
      --panel: rgba(10, 18, 46, 0.9);
      --border: rgba(61, 240, 255, 0.35);
      --status-bg: rgba(7, 14, 35, 0.76);
      --status-border: rgba(61, 240, 255, 0.34);
      --deck-bg: rgba(12, 18, 45, 0.76);
      --deck-border: rgba(255, 77, 219, 0.28);
      --feed-bg: rgba(5, 10, 28, 0.7);
      --feed-border: rgba(61, 240, 255, 0.24);
      --composer-bg: rgba(9, 18, 45, 0.84);
      --composer-border: rgba(61, 240, 255, 0.28);
      --terminal-pane-bg: rgba(3, 8, 24, 0.76);
      --terminal-output-bg: rgba(1, 5, 16, 0.92);
      --terminal-output-ink: #bce9ff;
      --ops-bg: rgba(25, 10, 33, 0.46);
      --steps-border: rgba(255, 77, 219, 0.26);
      --card-details-bg: rgba(7, 14, 34, 0.72);
      --card-details-border: rgba(142, 255, 95, 0.24);
      --msg-user-bg: rgba(14, 49, 22, 0.52);
      --msg-user-border: rgba(142, 255, 95, 0.44);
      --msg-assistant-bg: rgba(8, 26, 49, 0.58);
      --msg-assistant-border: rgba(61, 240, 255, 0.42);
      --dialog-bg: rgba(6, 12, 32, 0.95);
      --radius: 16px;
      --speed: 220ms;
      --danger: #ff7085;
      --ok: #77ff93;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: "Rajdhani", "Orbitron", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 12% 10%, rgba(255, 77, 219, 0.20), transparent 36%),
        radial-gradient(circle at 85% 15%, rgba(61, 240, 255, 0.18), transparent 32%),
        radial-gradient(circle at 55% 85%, rgba(142, 255, 95, 0.12), transparent 46%),
        linear-gradient(160deg, var(--bg-1), var(--bg-2) 45%, var(--bg-3));
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.12;
      background-image: radial-gradient(rgba(255,255,255,0.5) 0.7px, transparent 0.7px);
      background-size: 3px 3px;
    }

    .app {
      max-width: 1460px;
      margin: 0 auto;
      padding: 16px;
      min-height: 100vh;
      display: grid;
      gap: 14px;
      align-items: start;
    }

    body[data-surface="ui"] .app { grid-template-columns: 320px minmax(0, 1fr) 320px; }
    body[data-surface="chat-ui"] .app { grid-template-columns: 300px minmax(0, 1fr); }

    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: 0 14px 36px rgba(0,0,0,0.38), inset 0 0 0 1px rgba(255,255,255,0.06);
      backdrop-filter: blur(5px);
    }

    .controls {
      padding: 14px;
      display: grid;
      gap: 10px;
      position: sticky;
      top: 12px;
      max-height: calc(100vh - 24px);
      overflow: auto;
    }

    .title {
      border-radius: 12px;
      border: 1px solid color-mix(in srgb, var(--pink) 42%, transparent);
      background: linear-gradient(
        135deg,
        color-mix(in srgb, var(--cyan) 24%, transparent),
        color-mix(in srgb, var(--pink) 26%, transparent)
      );
      padding: 10px;
    }

    h1 {
      margin: 0;
      font-size: 20px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      line-height: 1.15;
    }

    .sub {
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.04em;
    }

    .field { display: grid; gap: 6px; }

    .label {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.11em;
    }

    input, select, textarea {
      width: 100%;
      border: 1px solid var(--border);
      background: rgba(5, 11, 28, 0.9);
      color: var(--ink);
      border-radius: 12px;
      padding: 9px 10px;
      font: inherit;
      transition: border-color var(--speed) ease, box-shadow var(--speed) ease;
    }

    textarea { min-height: 92px; resize: vertical; }

    input:focus, select:focus, textarea:focus {
      outline: none;
      border-color: var(--cyan);
      box-shadow: 0 0 0 3px rgba(61, 240, 255, 0.19);
    }

    .row { display: flex; gap: 8px; flex-wrap: wrap; }

    button, .btn {
      border: 0;
      border-radius: 11px;
      padding: 9px 12px;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      cursor: pointer;
      transition: transform var(--speed) ease, filter var(--speed) ease;
      background: linear-gradient(120deg, var(--cyan), #9ff7ff);
      color: #041a2e;
      min-height: 38px;
    }

    button.alt, .btn.alt {
      background: linear-gradient(120deg, var(--lime), #c6ff88);
      color: #072009;
    }

    button.warn, .btn.warn {
      background: linear-gradient(120deg, #ff94a2, #ff7085);
      color: #2d0710;
    }

    button.smiles, .btn.smiles {
      background: linear-gradient(120deg, #ff74c9, #ffa25f);
      color: #2a071f;
    }

    button:hover:not(:disabled), .btn:hover:not(:disabled) {
      transform: translateY(-1px);
      filter: brightness(1.04);
    }

    button:disabled, .btn:disabled {
      opacity: 0.62;
      cursor: wait;
      transform: none;
    }

    .toggle {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: var(--muted);
    }

    .main {
      padding: 14px;
      display: grid;
      gap: 10px;
      min-height: 86vh;
      grid-template-rows: auto auto minmax(220px, 1fr) auto;
    }

    .status {
      border: 1px solid var(--status-border);
      border-radius: 11px;
      background: var(--status-bg);
      color: var(--muted);
      min-height: 42px;
      padding: 10px;
      font-size: 13px;
    }

    .status-bar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
    }

    .status-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .deck {
      border: 1px solid var(--deck-border);
      border-radius: 13px;
      background: var(--deck-bg);
      padding: 10px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(126px, 1fr));
      gap: 10px;
    }

    .smyles-panel {
      border: 1px solid color-mix(in srgb, var(--pink) 30%, transparent);
      border-radius: 13px;
      background: linear-gradient(
        160deg,
        color-mix(in srgb, var(--bg-2) 86%, transparent),
        color-mix(in srgb, var(--bg-1) 92%, transparent)
      );
      padding: 10px;
      display: grid;
      gap: 8px;
    }

    .smyles-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(92px, 1fr));
      gap: 8px;
    }

    .smyle-tile {
      border: 1px solid color-mix(in srgb, var(--cyan) 30%, transparent);
      border-radius: 11px;
      overflow: hidden;
      background: rgba(6, 14, 35, 0.86);
    }

    .smyle-tile img {
      width: 100%;
      height: 68px;
      object-fit: cover;
      display: block;
      filter: saturate(1.08) contrast(1.04);
    }

    .smyle-tile .caption {
      padding: 6px 7px;
      color: var(--muted);
      font-size: 10px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .role-card {
      position: relative;
      width: 100%;
      min-height: 174px;
      border-radius: 14px;
      border: 2px solid color-mix(in srgb, var(--cyan) 50%, transparent);
      background:
        linear-gradient(
          150deg,
          color-mix(in srgb, var(--bg-2) 88%, transparent),
          color-mix(in srgb, var(--bg-1) 92%, transparent)
        );
      color: #e6f8ff;
      text-align: left;
      display: grid;
      align-content: end;
      gap: 6px;
      padding: 10px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.36);
      transform: translate(var(--jitter-x, 0px), var(--jitter-y, 0px)) rotate(var(--tilt, 0deg));
      transition: transform var(--speed) ease, box-shadow var(--speed) ease, border-color var(--speed) ease;
      overflow: hidden;
      isolation: isolate;
    }

    .role-card::before {
      content: "";
      position: absolute;
      inset: 0;
      z-index: -2;
      background-image: var(--card-image, none);
      background-size: cover;
      background-position: center;
      opacity: 0.96;
      filter: saturate(1.10) contrast(1.06);
    }

    .role-card .role-art {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      z-index: -2;
      opacity: 0.98;
      filter: saturate(1.10) contrast(1.06);
      pointer-events: none;
      user-select: none;
      display: none;
    }

    .role-card .role-art.fallback {
      z-index: -3;
      opacity: 0.95;
    }

    .role-card::after {
      content: "";
      position: absolute;
      inset: 0;
      z-index: -1;
      background: linear-gradient(
        180deg,
        color-mix(in srgb, var(--bg-1) 18%, transparent),
        color-mix(in srgb, var(--bg-1) 78%, transparent)
      );
    }

    .role-card.has-image .icon-chip {
      display: none;
    }

    .role-card .icon-chip {
      position: absolute;
      top: 8px;
      left: 8px;
      width: 34px;
      height: 34px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      font-size: 18px;
      background: color-mix(in srgb, var(--bg-1) 82%, transparent);
      border: 1px solid color-mix(in srgb, var(--ink) 26%, transparent);
    }

    .role-card .role-name {
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .role-card .role-mode {
      font-size: 11px;
      color: #b9daef;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }

    .role-card .role-desc {
      font-size: 11px;
      color: #d7e8f7;
      line-height: 1.35;
      letter-spacing: 0.01em;
      text-transform: none;
      max-height: 2.7em;
      overflow: hidden;
    }

    .role-card:hover {
      transform: translate(var(--jitter-x, 0px), calc(var(--jitter-y, 0px) - 2px)) rotate(var(--tilt, 0deg));
      box-shadow: 0 12px 28px rgba(0,0,0,0.46), 0 0 calc(18px + var(--pulse, 0px)) color-mix(in srgb, var(--cyan) 22%, transparent);
    }

    .role-card[aria-pressed="true"] {
      border-color: var(--role-accent, var(--pink));
      box-shadow: 0 12px 32px rgba(0,0,0,0.48), 0 0 24px color-mix(in srgb, var(--role-accent, var(--pink)) 52%, transparent);
    }

    .role-card.core {
      border-width: 3px;
      min-height: 188px;
    }

    .feed {
      border: 1px solid var(--feed-border);
      border-radius: 12px;
      background: var(--feed-bg);
      padding: 10px;
      overflow: auto;
      display: grid;
      gap: 8px;
      align-content: start;
    }

    .msg {
      border-radius: 11px;
      padding: 10px;
      font-size: 14px;
      line-height: 1.42;
      white-space: pre-wrap;
    }

    .msg.user {
      border: 1px solid var(--msg-user-border);
      background: var(--msg-user-bg);
    }

    .msg.assistant {
      border: 1px solid var(--msg-assistant-border);
      background: var(--msg-assistant-bg);
    }

    .composer {
      border: 1px solid var(--composer-border);
      border-radius: 12px;
      background: var(--composer-bg);
      padding: 10px;
      display: grid;
      gap: 8px;
    }

    .mode-switch {
      align-items: center;
      gap: 8px;
    }

    .mode-switch button[aria-pressed="true"] {
      box-shadow: 0 0 0 2px rgba(61, 240, 255, 0.26) inset;
      filter: saturate(1.08);
    }

    .terminal-pane {
      border: 1px solid var(--feed-border);
      border-radius: 10px;
      background: var(--terminal-pane-bg);
      padding: 10px;
      display: grid;
      gap: 8px;
    }

    .terminal-output {
      margin: 0;
      min-height: 180px;
      max-height: 360px;
      overflow: auto;
      border: 1px solid var(--feed-border);
      border-radius: 9px;
      background: var(--terminal-output-bg);
      color: var(--terminal-output-ink);
      padding: 10px;
      font-size: 12px;
      line-height: 1.35;
      font-family: "Consolas", "Cascadia Mono", "Fira Code", monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .dock-hidden {
      display: none !important;
    }

    .ops {
      padding: 12px;
      display: grid;
      gap: 10px;
      align-content: start;
      max-height: calc(100vh - 24px);
      overflow: auto;
      position: sticky;
      top: 12px;
    }

    .ops-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }

    .steps {
      border: 1px solid var(--steps-border);
      border-radius: 11px;
      background: var(--ops-bg);
      color: var(--muted);
      min-height: 120px;
      max-height: 320px;
      overflow: auto;
      padding: 10px;
      font-size: 12px;
    }

    .ops-collapsed .ops-content,
    .ops-collapsed .drawer-content { display: none; }

    #opsPanel { display: none; }
    #opsDrawer { display: none; }
    body[data-surface="ui"] #opsPanel { display: grid; }
    body[data-surface="chat-ui"] #opsDrawer { display: grid; }

    .small {
      color: var(--muted);
      font-size: 12px;
    }

    #cardDetails {
      display: grid;
      gap: 8px;
      border: 1px solid var(--card-details-border);
      background: var(--card-details-bg);
    }

    #scopePanel {
      display: grid;
      gap: 8px;
      border: 1px solid var(--feed-border);
      background: color-mix(in srgb, var(--panel) 75%, transparent);
      padding: 10px;
    }

    #scopePanel .scope-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: end;
    }

    #scopePanel .scope-note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }

    .live-console {
      display: grid;
      gap: 8px;
      border: 1px solid var(--feed-border);
      border-radius: 10px;
      background: color-mix(in srgb, var(--panel) 72%, transparent);
      padding: 10px;
    }

    .live-console.collapsed .live-console-body {
      display: none;
    }

    .live-console-head {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
    }

    .live-console-tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .live-console-tabs button[aria-pressed="true"] {
      box-shadow: 0 0 0 2px rgba(61, 240, 255, 0.24) inset;
    }

    .live-console-body pre {
      margin: 0;
      min-height: 100px;
      max-height: 240px;
      overflow: auto;
      border: 1px solid var(--feed-border);
      border-radius: 8px;
      background: var(--terminal-output-bg);
      color: var(--terminal-output-ink);
      padding: 10px;
      font-size: 12px;
      line-height: 1.35;
      font-family: "Consolas", "Cascadia Mono", "Fira Code", monospace;
      white-space: pre-wrap;
    }

    dialog.panel {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--dialog-bg);
      color: var(--ink);
      width: min(560px, 92vw);
      padding: 14px;
    }

    dialog::backdrop {
      background: rgba(0, 0, 0, 0.56);
      backdrop-filter: blur(2px);
    }

    .language-modal-form {
      display: grid;
      gap: 10px;
    }

    .language-modal-summary {
      white-space: pre-wrap;
      line-height: 1.35;
    }

    .language-modal-grid {
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .language-modal-grid .field {
      min-width: 0;
    }

    .language-modal-trace {
      min-height: 130px;
      max-height: 240px;
    }

    .step-ok { color: var(--ok); }
    .step-warn { color: #ffd080; }
    .step-fail { color: var(--danger); }

    @media (max-width: 1240px) {
      body[data-surface="ui"] .app { grid-template-columns: 300px minmax(0, 1fr); }
      body[data-surface="ui"] #opsPanel {
        grid-column: 1 / -1;
        position: static;
        max-height: none;
      }
      body[data-surface="ui"] .ops { position: static; }
    }

    @media (max-width: 1040px) {
      .app { grid-template-columns: 1fr !important; }
      .controls, .ops { position: static; max-height: none; }
      .role-card { min-height: 154px; }
      .role-card.core { min-height: 164px; }
    }

    @media (max-width: 760px) {
      .language-modal-grid {
        grid-template-columns: minmax(0, 1fr);
      }
    }

    @media (prefers-reduced-motion: reduce) {
      * { animation: none !important; transition: none !important; }
      .role-card { transform: none !important; }
    }
    """


def _shared_js() -> str:
    return """
    <script>
      const state = {
        surface: document.body.dataset.surface || 'ui',
        threadId: '',
        catalog: [],
        cards: [],
        activeRole: 'core',
        roleVariantIndex: {},
        pendingApprovals: [],
        opsCollapsed: true,
        interfaceMode: 'ask',
        offlineMode: 'guided',
        me: {},
        offlineCapabilities: null,
        terminalPresets: [],
        terminalProfiles: [],
        answerScope: 'repo_grounded',
        scopeConfirmed: false,
        scopePromptMode: 'always',
        liveOutputMode: 'collapsed',
        apiEvents: [],
        languageCatalog: [],
        languageDecision: null,
        languageMode: 'auto',
        manualLanguage: '',
        languageStorageMode: 'auto',
        languageExternalEnrichment: false,
      };

      const tokenInput = document.getElementById('token');
      const modelSelect = document.getElementById('model');
      const offlineOnly = document.getElementById('offlineOnly');
      const allowRemote = document.getElementById('allowRemote');
      const offlineModeSelect = document.getElementById('offlineMode');
      const profileScopeInput = document.getElementById('profileScope');
      const displayName = document.getElementById('displayName');
      const avatarStyle = document.getElementById('avatarStyle');
      const themeSelect = document.getElementById('theme');
      const tonePreset = document.getElementById('tonePreset');
      const languageModeSelect = document.getElementById('languageMode');
      const manualLanguageInput = document.getElementById('manualLanguage');
      const languageStorageModeSelect = document.getElementById('languageStorageMode');
      const languageExternalToggle = document.getElementById('languageExternalEnrichment');
      const refreshLanguageCatalogBtn = document.getElementById('refreshLanguageCatalog');
      const languageCatalogCount = document.getElementById('languageCatalogCount');
      const openLanguageDecisionBtn = document.getElementById('openLanguageDecision');
      const languageDecisionStatus = document.getElementById('languageDecisionStatus');
      const cardPack = document.getElementById('cardPack');
      const threadInput = document.getElementById('threadId');
      const threadInfo = document.getElementById('threadInfo');
      const statusBox = document.getElementById('status');
      const roleDeck = document.getElementById('roleDeck');
      const smylesStrip = document.getElementById('smylesStrip');
      const promptInput = document.getElementById('prompt');
      const sendBtn = document.getElementById('send');
      const feed = document.getElementById('feed');
      const roleHintInput = document.getElementById('roleHint');
      const topKInput = document.getElementById('topK');
      const steps = document.getElementById('steps');
      const drawerSteps = document.getElementById('drawerSteps');
      const opsToggle = document.getElementById('opsToggle');
      const drawerToggle = document.getElementById('drawerToggle');
      const smilesRefreshBtn = document.getElementById('smilesRefresh');
      const smilesRefreshTopBtn = document.getElementById('smilesRefreshTop');
      const browserResetBtn = document.getElementById('browserReset');
      const browserResetTopBtn = document.getElementById('browserResetTop');
      const openSmileEditorBtn = document.getElementById('openSmileEditor');
      const useBearerProfileBtn = document.getElementById('useBearerProfile');
      const offlineCapabilitiesBox = document.getElementById('offlineCapabilities');
      const cardExplain = document.getElementById('cardExplain');
      const roleQuickActions = document.getElementById('roleQuickActions');
      const answerScopeSelect = document.getElementById('answerScope');
      const scopePromptModeSelect = document.getElementById('scopePromptMode');
      const scopeStatus = document.getElementById('scopeStatus');
      const scopeConfirmBtn = document.getElementById('scopeConfirm');
      const scopePanel = document.getElementById('scopePanel');
      const modeSwitchRow = document.getElementById('interfaceModeRow');
      const modeAskBtn = document.getElementById('modeAsk');
      const modeTerminalBtn = document.getElementById('modeTerminal');
      const openChatPopoutTerminalBtn = document.getElementById('openChatPopoutTerminal');
      const openDeckPopoutTerminalBtn = document.getElementById('openDeckPopoutTerminal');
      const askPane = document.getElementById('askPane');
      const terminalPane = document.getElementById('terminalPane');
      const terminalPresetSelect = document.getElementById('terminalPreset');
      const terminalProfileSelect = document.getElementById('terminalProfile');
      const terminalCommandInput = document.getElementById('terminalCommand');
      const terminalExecBtn = document.getElementById('terminalExec');
      const terminalRunBtn = document.getElementById('terminalRun');
      const terminalOpenProfileBtn = document.getElementById('terminalOpenProfile');
      const runLanguageCatalogTestBtn = document.getElementById('runLanguageCatalogTest');
      const runNotebookPresetBtn = document.getElementById('runNotebookPreset');
      const runCppPresetBtn = document.getElementById('runCppPreset');
      const fixAllCapsBtn = document.getElementById('fixAllCaps');
      const repairCppBtn = document.getElementById('repairCpp');
      const repairNotebookBtn = document.getElementById('repairNotebook');
      const startLmStudioBtn = document.getElementById('startLmStudio');
      const terminalAuditBtn = document.getElementById('terminalAudit');
      const terminalOutput = document.getElementById('terminalOutput');
      const openTerminalPopoutBtn = document.getElementById('openTerminalPopout');
      const openTaskWindowBtn = document.getElementById('openTaskWindow');
      const openChatPopoutBtn = document.getElementById('openChatPopout');
      const openDeckPopoutBtn = document.getElementById('openDeckPopout');
      const openCommandDeckBtn = document.getElementById('openCommandDeck');
      const openChatOnlyBtn = document.getElementById('openChatOnly');
      const openAdminUiBtn = document.getElementById('openAdminUi');
      const confirmModal = document.getElementById('confirmModal');
      const confirmTitle = document.getElementById('confirmTitle');
      const confirmBody = document.getElementById('confirmBody');
      const confirmOk = document.getElementById('confirmOk');
      const confirmCancel = document.getElementById('confirmCancel');
      const languageDecisionModal = document.getElementById('languageDecisionModal');
      const languageDecisionSummary = document.getElementById('languageDecisionSummary');
      const languageDecisionTrace = document.getElementById('languageDecisionTrace');
      const modalSelectedLanguage = document.getElementById('modalSelectedLanguage');
      const modalSelectedRoute = document.getElementById('modalSelectedRoute');
      const modalLanguageMode = document.getElementById('modalLanguageMode');
      const modalScopeRecommendation = document.getElementById('modalScopeRecommendation');
      const modalTopLanguages = document.getElementById('modalTopLanguages');
      const modalDecisionConfidence = document.getElementById('modalDecisionConfidence');
      const modalHybridMode = document.getElementById('modalHybridMode');
      const copyDecisionTraceBtn = document.getElementById('copyDecisionTrace');
      const liveOutput = document.getElementById('liveOutput');
      const liveOutputToggle = document.getElementById('liveOutputToggle');
      const liveOutputTabSummary = document.getElementById('liveOutputTabSummary');
      const liveOutputTabRaw = document.getElementById('liveOutputTabRaw');
      const liveOutputSummary = document.getElementById('liveOutputSummary');
      const liveOutputRaw = document.getElementById('liveOutputRaw');
      const messageLog = [];
      let liveLogPopoutWindow = null;
      let taskWindowPopout = null;
      let chatPopoutWindow = null;
      let deckPopoutWindow = null;
      let taskWindowBusy = false;
      let terminalPresetsLoaded = false;
      let terminalProfilesLoaded = false;

      function createLoadSeed() {
        return (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function')
          ? globalThis.crypto.randomUUID()
          : `${Date.now()}-${Math.random()}`;
      }
      let loadSeed = createLoadSeed();

      const threadStoreKey = `ccbs_ai3_thread_${state.surface}`;
      tokenInput.value = localStorage.getItem('ccbs_ai3_token') || '';
      state.threadId = localStorage.getItem(threadStoreKey) || '';
      if (threadInput) threadInput.value = state.threadId;
      if (threadInfo) threadInfo.textContent = `Thread: ${state.threadId || 'auto'}`;

      function asBool(value, fallback = false) {
        if (typeof value === 'boolean') return value;
        if (value === null || value === undefined) return fallback;
        const raw = String(value).trim().toLowerCase();
        if (['1','true','yes','on'].includes(raw)) return true;
        if (['0','false','no','off'].includes(raw)) return false;
        return fallback;
      }

      function normalizeOfflineMode(value, fallback = 'guided') {
        const raw = String(value || '').trim().toLowerCase();
        if (raw === 'off' || raw === 'guided' || raw === 'strict') return raw;
        return fallback;
      }

      function normalizeAnswerScope(value, fallback = 'repo_grounded') {
        const raw = String(value || '').trim().toLowerCase();
        if (raw === 'repo_grounded' || raw === 'general_local' || raw === 'remote_allowed') return raw;
        return fallback;
      }

      function normalizeScopePromptMode(value, fallback = 'always') {
        const raw = String(value || '').trim().toLowerCase();
        if (raw === 'always' || raw === 'manual') return raw;
        return fallback;
      }

      function normalizeLiveOutputMode(value, fallback = 'collapsed') {
        const raw = String(value || '').trim().toLowerCase();
        if (raw === 'collapsed' || raw === 'summary' || raw === 'raw') return raw;
        return fallback;
      }

      function normalizeLanguageMode(value, fallback = 'auto') {
        const raw = String(value || '').trim().toLowerCase();
        if (raw === 'auto' || raw === 'manual') return raw;
        return fallback;
      }

      function normalizeLanguageStorageMode(value, fallback = 'auto') {
        const raw = String(value || '').trim().toLowerCase();
        if (raw === 'auto' || raw === 'json' || raw === 'sqlite' || raw === 'parquet' || raw === 'feather') return raw;
        return fallback;
      }

      function formatDecisionConfidence(value) {
        if (typeof value === 'number' && Number.isFinite(value)) return value.toFixed(3);
        const raw = String(value || '').trim();
        return raw || 'n/a';
      }

      function collectTopLanguages(decision, limit = 3) {
        const ranking = Array.isArray(decision && decision.language_rankings) ? decision.language_rankings : [];
        const top = [];
        for (const row of ranking) {
          const name = String((row && row.language) || '').trim();
          if (!name) continue;
          top.push(name);
          if (top.length >= limit) break;
        }
        return top;
      }

      async function copyTextToClipboard(text) {
        const value = String(text || '');
        if (!value) return false;
        if (globalThis.navigator && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
          await navigator.clipboard.writeText(value);
          return true;
        }
        const area = document.createElement('textarea');
        area.value = value;
        area.style.position = 'fixed';
        area.style.opacity = '0';
        area.style.pointerEvents = 'none';
        document.body.appendChild(area);
        area.focus();
        area.select();
        let copied = false;
        try {
          copied = document.execCommand('copy');
        } catch (_err) {
          copied = false;
        }
        document.body.removeChild(area);
        return copied;
      }

      function applyOfflineMode(mode, forceDefaults = false) {
        const next = normalizeOfflineMode(mode, state.offlineMode || 'guided');
        state.offlineMode = next;
        if (offlineModeSelect) offlineModeSelect.value = next;
        if (next === 'strict') {
          offlineOnly.checked = true;
          allowRemote.checked = false;
          offlineOnly.disabled = true;
          allowRemote.disabled = true;
          syncTaskWindowDefaults();
          syncChatPopoutFeed();
          syncDeckPopout();
          return;
        }
        offlineOnly.disabled = false;
        allowRemote.disabled = false;
        if (next === 'guided' && forceDefaults) {
          offlineOnly.checked = true;
          allowRemote.checked = false;
        }
        updateScopePolicyForMode();
        syncTaskWindowDefaults();
        syncChatPopoutFeed();
        syncDeckPopout();
      }

      function scopeLabel(scope) {
        const key = normalizeAnswerScope(scope, state.answerScope);
        if (key === 'repo_grounded') return 'Repo Grounded';
        if (key === 'general_local') return 'General Local';
        return 'Remote Allowed';
      }

      function scopeDescription(scope) {
        const key = normalizeAnswerScope(scope, state.answerScope);
        if (key === 'repo_grounded') return 'Repository-first local answers with stronger citation expectations.';
        if (key === 'general_local') return 'Local models and local context, broader than repo-only.';
        return 'Remote-capable answers when policy/offline mode allows it.';
      }

      function remoteFoundryGateState() {
        const gate = state.offlineCapabilities && (state.offlineCapabilities.foundry_gate || state.offlineCapabilities.binary_gate);
        if (gate && typeof gate === 'object') return gate;
        return {
          local_tools_ready: false,
          continue_or_stop: false,
          reason: 'Optimize all local tools and the repo venv before continuing to Remote Allowed or Foundry lanes.',
        };
      }

      function remoteFoundryGateOpen() {
        const gate = remoteFoundryGateState();
        return !!gate.continue_or_stop;
      }

      function remoteFoundryGateReason() {
        const gate = remoteFoundryGateState();
        return String(gate.reason || 'Optimize all local tools and the repo venv before continuing to Remote Allowed or Foundry lanes.').trim();
      }

      function updateScopePolicyForMode() {
        if (!answerScopeSelect) return;
        const remoteOpt = answerScopeSelect.querySelector('option[value="remote_allowed"]');
        const strict = state.offlineMode === 'strict';
        const gateOpen = remoteFoundryGateOpen();
        const remoteEnabled = !strict && gateOpen;
        if (remoteOpt) {
          remoteOpt.disabled = !remoteEnabled;
          remoteOpt.textContent = strict
            ? 'Remote Allowed (blocked in strict)'
            : (gateOpen ? 'Remote Allowed' : 'Remote Allowed (optimize local tools first)');
        }
        if (!remoteEnabled && normalizeAnswerScope(answerScopeSelect.value, state.answerScope) === 'remote_allowed') {
          answerScopeSelect.value = 'repo_grounded';
          state.answerScope = 'repo_grounded';
          state.scopeConfirmed = false;
        }
        renderScopeStatus();
      }

      function renderScopeStatus() {
        if (!scopeStatus) return;
        const name = scopeLabel(state.answerScope);
        const desc = scopeDescription(state.answerScope);
        const confirmed = state.scopeConfirmed ? 'confirmed' : 'not confirmed';
        scopeStatus.textContent = `${name}: ${desc} (${confirmed})`;
      }

      function setScope(scope, confirmed = false) {
        state.answerScope = normalizeAnswerScope(scope, state.answerScope || 'repo_grounded');
        if (answerScopeSelect) answerScopeSelect.value = state.answerScope;
        state.scopeConfirmed = !!confirmed;
        renderScopeStatus();
        syncTaskWindowDefaults();
        syncChatPopoutFeed();
      }

      function confirmScopeSelection() {
        state.answerScope = normalizeAnswerScope(answerScopeSelect ? answerScopeSelect.value : state.answerScope, state.answerScope || 'repo_grounded');
        state.scopeConfirmed = true;
        renderScopeStatus();
        if (scopePromptModeSelect && normalizeScopePromptMode(scopePromptModeSelect.value, state.scopePromptMode) === 'always') {
          setStatus(`Scope router locked: ${scopeLabel(state.answerScope)}`, 'ok');
        }
      }

      function openNeonCompass(focus = true) {
        if (scopePanel) scopePanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        if (focus && answerScopeSelect) answerScopeSelect.focus();
        setStatus('Scope router ready. Pick scope and apply before send.', 'info');
      }

      async function confirmAction(opts = {}) {
        const title = String(opts.title || 'Confirm action');
        const body = String(opts.body || 'Proceed with this action?');
        if (!confirmModal || typeof confirmModal.showModal !== 'function') {
          return window.confirm(`${title}\n\n${body}`);
        }
        confirmTitle.textContent = title;
        confirmBody.textContent = body;
        if (confirmOk) confirmOk.textContent = String(opts.confirmLabel || 'Run');
        if (confirmCancel) confirmCancel.textContent = String(opts.cancelLabel || 'Cancel');
        return new Promise((resolve) => {
          const done = () => {
            confirmModal.removeEventListener('close', done);
            resolve(String(confirmModal.returnValue || '') === 'confirm');
          };
          confirmModal.addEventListener('close', done);
          confirmModal.showModal();
        });
      }

      function explainMode(mode) {
        if (mode === 'strict') return 'Strict offline: remote/network actions are blocked server-side.';
        if (mode === 'off') return 'Off: remote operations allowed based on role and permissions.';
        return 'Guided offline: safe defaults on, but you can still override manually.';
      }

      function hash32(str) {
        let h = 2166136261 >>> 0;
        for (let i = 0; i < str.length; i += 1) {
          h ^= str.charCodeAt(i);
          h = Math.imul(h, 16777619);
        }
        return h >>> 0;
      }

      function boundedFloat(seed, min, max) {
        const n = (hash32(seed) % 1000000) / 1000000;
        return min + (max - min) * n;
      }

      function boundedInt(seed, maxExclusive) {
        const cap = Number(maxExclusive || 0);
        if (!Number.isFinite(cap) || cap <= 0) return 0;
        return hash32(seed) % Math.floor(cap);
      }

      function setStatus(text, tone = 'info') {
        statusBox.textContent = text;
        if (tone === 'error') {
          statusBox.style.borderColor = 'color-mix(in srgb, var(--danger) 70%, transparent)';
        } else if (tone === 'ok') {
          statusBox.style.borderColor = 'color-mix(in srgb, var(--ok) 65%, transparent)';
        } else {
          statusBox.style.borderColor = 'var(--status-border)';
        }
      }

      function setLiveOutputMode(mode, persist = false) {
        state.liveOutputMode = normalizeLiveOutputMode(mode, state.liveOutputMode || 'collapsed');
        if (!liveOutput) return;
        liveOutput.classList.toggle('collapsed', state.liveOutputMode === 'collapsed');
        if (liveOutputTabSummary) liveOutputTabSummary.setAttribute('aria-pressed', String(state.liveOutputMode === 'summary'));
        if (liveOutputTabRaw) liveOutputTabRaw.setAttribute('aria-pressed', String(state.liveOutputMode === 'raw'));
        if (liveOutputSummary) liveOutputSummary.style.display = state.liveOutputMode === 'summary' ? 'block' : 'none';
        if (liveOutputRaw) liveOutputRaw.style.display = state.liveOutputMode === 'raw' ? 'block' : 'none';
        if (persist) {
          saveProfile().catch((err) => setStatus(`profile warning: ${err.message}`, 'error'));
        }
      }

      function summarizeEvent(event) {
        const kind = String((event && event.kind) || '');
        const payload = (event && event.payload) || {};
        const when = String((event && event.created_at) || '').replace('T', ' ').replace('Z', ' UTC');
        if (kind === 'chat.send.request') {
          return `[${when}] send -> role=${payload.active_role}/${payload.effective_role} scope=${payload.answer_scope} mode=${payload.offline_mode}`;
        }
        if (kind === 'chat.send.result') {
          const conf = payload.confidence && payload.confidence.label ? payload.confidence.label : 'n/a';
          return `[${when}] result -> status=${payload.run_status} ok=${payload.ok} provider=${payload.provider_used} confidence=${conf}`;
        }
        if (kind === 'terminal.run') {
          return `[${when}] preset ${payload.preset_id} -> exit=${payload.exit_code} ok=${payload.ok}`;
        }
        if (kind === 'terminal.run_stream.start') {
          return `[${when}] stream start ${payload.preset_id} run=${payload.run_id}`;
        }
        if (kind === 'terminal.run_stream.finish') {
          return `[${when}] stream finish ${payload.preset_id} -> exit=${payload.exit_code} ok=${payload.ok}`;
        }
        if (kind === 'terminal.exec') {
          return `[${when}] exec "${payload.command || ''}" -> exit=${payload.exit_code} ok=${payload.ok}`;
        }
        if (kind === 'terminal.audit') {
          return `[${when}] audit -> ok=${payload.ok} mode=${payload.offline_mode}`;
        }
        if (kind === 'terminal.open_profile') {
          return `[${when}] open profile ${payload.profile_id} pid=${payload.pid || 'n/a'}`;
        }
        if (kind === 'chat.role_select') {
          return `[${when}] role ${payload.role_id} xp=${payload.xp}`;
        }
        if (kind === 'capability.remediate') {
          return `[${when}] capability ${payload.action_id} -> status=${payload.status} ok=${payload.ok}`;
        }
        return `[${when}] ${kind}`;
      }

      function renderLiveOutput() {
        if (liveOutputSummary) {
          const lines = (state.apiEvents || []).map((row) => summarizeEvent(row));
          liveOutputSummary.textContent = lines.length ? lines.join('\\n') : 'No API events yet.';
        }
        if (liveOutputRaw) {
          const lines = (state.apiEvents || []).map((row) => JSON.stringify(row));
          liveOutputRaw.textContent = lines.length ? lines.join('\\n') : 'No API events yet.';
        }
      }

      async function loadApiEvents() {
        const out = await api('/v3/chat/api-events?limit=120');
        state.apiEvents = Array.isArray(out.events) ? out.events : [];
        renderLiveOutput();
      }

      async function loadIdentity() {
        const out = await api('/v3/chat/me');
        state.me = out || {};
        if (profileScopeInput) {
          const scope = String((out && out.profile_scope) || (out && out.username) || 'default');
          const role = String((out && out.role) || '');
          const mode = String((out && out.auth_mode) || '');
          profileScopeInput.value = role ? `${scope} (${role}; ${mode || 'auth'})` : scope;
        }
      }

      function renderOfflineCapabilities(payload) {
        if (!offlineCapabilitiesBox) return;
        const p = payload || {};
        const checks = p.checks || {};
        const local = p.local_models || {};
        const windowsCpp = p.windows_cpp || {};
        const wslCpp = p.wsl_cpp || {};
        const pyNotebook = p.python_notebook || {};
        const lm = p.lm_studio || {};
        const ollama = p.ollama || {};
        const binaryGate = p.binary_gate || {};
        const foundryGate = p.foundry_gate || {};
        const fixes = Array.isArray(p.fix_actions) ? p.fix_actions : [];
        const lines = [];
        lines.push(`Mode: ${p.active_offline_mode || state.offlineMode}`);
        lines.push(`Overall ready: ${p.overall_ready ? 'YES' : 'NO'}`);
        lines.push(`Remote/Foundry gate: ${binaryGate.continue_or_stop ? 'OPEN' : 'CLOSED'}`);
        if (binaryGate.reason) lines.push(`Gate note: ${binaryGate.reason}`);
        lines.push(`Foundry lane: ${foundryGate.pane_enabled ? 'READY' : 'BLOCKED'}`);
        if (foundryGate.reason) lines.push(`Foundry note: ${foundryGate.reason}`);
        lines.push(`Local models reachable: ${Number(local.reachable || 0)}/${Number(local.total || 0)}`);
        lines.push(`Windows C++: ${windowsCpp.status || 'unknown'}`);
        lines.push(`WSL C++: ${wslCpp.status || 'unknown'}`);
        lines.push(`Notebook runtime: ${pyNotebook.status || 'unknown'}`);
        lines.push(`LM Studio: ${lm.status || 'unknown'} (${lm.model_count || 0} models)`);
        lines.push(`Ollama: ${ollama.status || 'unknown'} (${ollama.model_count || 0} models)`);
        if (checks.python) {
          lines.push(`Python: ${checks.python.ok ? 'OK' : 'MISSING'} ${checks.python.path || ''}`.trim());
          if (checks.python.interpreter_mismatch) {
            lines.push(`Interpreter mismatch: app=${checks.python.app_python || 'n/a'} launcher=${checks.python.launcher_python || 'n/a'}`);
          }
        }
        if (checks.notebook) {
          const missing = Array.isArray(checks.notebook.missing) ? checks.notebook.missing : [];
          lines.push(`Notebook deps: ${checks.notebook.ok ? 'OK' : `MISSING ${missing.join(', ')}`}`);
        }
        if (checks.cpp) {
          lines.push(`C++ toolchain: ${checks.cpp.ok ? 'OK' : 'MISSING compiler/cmake'}`);
        }
        if (checks.vscode) {
          const miss = Array.isArray(checks.vscode.missing_managed) ? checks.vscode.missing_managed : [];
          lines.push(`VS Code managed ext: ${checks.vscode.ok ? 'OK' : `MISSING ${miss.length}`}`);
        }
        if (fixes.length) {
          lines.push('');
          lines.push('Fix actions:');
          for (const row of fixes.slice(0, 6)) {
            lines.push(`- ${row.action_id}: ${row.label}`);
          }
        }
        offlineCapabilitiesBox.textContent = lines.join('\\n');
      }

      async function loadOfflineCapabilities() {
        const out = await api('/v3/chat/offline-capabilities');
        state.offlineCapabilities = out || null;
        if (out && out.active_offline_mode) {
          applyOfflineMode(out.active_offline_mode, false);
        }
        renderOfflineCapabilities(out || {});
      }

      function cardByRole(roleId) {
        return (state.cards || []).find((row) => String(row.role_id || '') === String(roleId || '')) || null;
      }

      function roleDifferenceText(card) {
        const roleId = String((card && card.role_id) || '').trim().toLowerCase();
        const effective = String((card && card.behavior && card.behavior.effective_role) || (card && card.utility_mode) || roleId).trim().toLowerCase();
        if (roleId === 'ranger') {
          return 'Ranger is the scope-routing lane. Select scope before send; guardian-style safety defaults apply.';
        }
        if (roleId === 'scientist') {
          return 'Scientist runs retrieval-focused analysis with deeper evidence behavior and larger top-k floors.';
        }
        if (roleId === 'samurai') {
          return 'Samurai lane translates verbal intent into implementation plans and runnable code steps.';
        }
        if (effective === 'guardian') return 'Safety-first lane. Forces strict offline and disables remote escalation.';
        if (effective === 'retriever') return 'Evidence lane. Uses deeper retrieval defaults and larger top-k floors.';
        if (effective === 'ops') return 'Operations lane. Optimized for approvals and workflow control.';
        if (effective === 'hacker') return 'Code-only lane. Prioritizes commands, code, and technical execution over general chatter.';
        if (effective === 'strategist') return 'Planning lane. Focuses on decomposition and execution sequencing.';
        return 'Balanced lane. General-purpose responses and coding/planning flow.';
      }

      function roleQuickActionsFor(card) {
        const roleId = String((card && card.role_id) || '').trim().toLowerCase();
        const effective = String((card && card.behavior && card.behavior.effective_role) || (card && card.utility_mode) || roleId).trim().toLowerCase();
        const base = [{ id: 'new_thread', label: 'New Thread', type: 'local' }];
        if (roleId === 'ranger') {
          return [
            { id: 'open_compass', label: 'Open Scope Router', type: 'local' },
            { id: 'set_strict', label: 'Set Strict Offline', type: 'local' },
            ...base,
          ];
        }
        if (roleId === 'scientist') {
          return [
            { id: 'set_deep_trace', label: 'Deep Trace', type: 'local' },
            { id: 'run_notebook_check', label: 'Notebook Check', type: 'preset', preset_id: 'ccbs_notebook_doctor' },
            ...base,
          ];
        }
        if (effective === 'guardian') return [{ id: 'set_strict', label: 'Set Strict Offline', type: 'local' }, ...base];
        if (roleId === 'hacker' || effective === 'hacker') {
          return [
            { id: 'switch_terminal', label: 'Hacker Terminal', type: 'local' },
            { id: 'fix_all_caps', label: 'Fix All Capabilities', type: 'capability', action_id: 'fix_all_capabilities' },
            { id: 'run_language_catalog_test', label: 'Language Catalog Test', type: 'preset', preset_id: 'ccbs_language_catalog_test' },
            { id: 'repair_cpp', label: 'Repair C++', type: 'capability', action_id: 'repair_cpp' },
            { id: 'repair_notebook', label: 'Repair Notebook Runtime', type: 'capability', action_id: 'repair_notebook_runtime' },
            { id: 'start_lm_studio', label: 'Start LM Studio', type: 'capability', action_id: 'start_lm_studio' },
            { id: 'open_profile', label: 'Open Terminal', type: 'profile' },
            { id: 'run_notebook_check', label: 'Notebook Check', type: 'preset', preset_id: 'ccbs_notebook_doctor' },
            { id: 'run_cpp_smoke', label: 'C++ Smoke', type: 'preset', preset_id: 'ccbs_cpp_compile_smoke' },
            { id: 'run_audit', label: 'Preset Audit', type: 'audit' },
            ...base,
          ];
        }
        if (effective === 'retriever') return [{ id: 'set_deep_trace', label: 'Deep Trace', type: 'local' }, ...base];
        if (effective === 'ops') return [{ id: 'expand_ops', label: 'Expand Ops', type: 'local' }, { id: 'run_audit', label: 'Preset Audit', type: 'audit' }, ...base];
        return [
          { id: 'run_notebook_check', label: 'Notebook Check', type: 'preset', preset_id: 'ccbs_notebook_doctor' },
          { id: 'run_cpp_smoke', label: 'C++ Smoke', type: 'preset', preset_id: 'ccbs_cpp_compile_smoke' },
          ...base,
        ];
      }

      function applyTheme(kind) {
        const root = document.documentElement;
        const themes = {
          'neon-deck': {
            '--bg-1': '#07091b',
            '--bg-2': '#0d1536',
            '--bg-3': '#0a1028',
            '--ink': '#e8f5ff',
            '--muted': '#93bdd9',
            '--cyan': '#3df0ff',
            '--lime': '#8eff5f',
            '--pink': '#ff4ddb',
            '--orange': '#ff9c47',
            '--panel': 'rgba(10, 18, 46, 0.9)',
            '--border': 'rgba(61, 240, 255, 0.35)',
            '--status-bg': 'rgba(7, 14, 35, 0.76)',
            '--status-border': 'rgba(61, 240, 255, 0.34)',
            '--deck-bg': 'rgba(12, 18, 45, 0.76)',
            '--deck-border': 'rgba(255, 77, 219, 0.28)',
            '--feed-bg': 'rgba(5, 10, 28, 0.7)',
            '--feed-border': 'rgba(61, 240, 255, 0.24)',
            '--composer-bg': 'rgba(9, 18, 45, 0.84)',
            '--composer-border': 'rgba(61, 240, 255, 0.28)',
            '--terminal-pane-bg': 'rgba(3, 8, 24, 0.76)',
            '--terminal-output-bg': 'rgba(1, 5, 16, 0.92)',
            '--terminal-output-ink': '#bce9ff',
            '--ops-bg': 'rgba(25, 10, 33, 0.46)',
            '--steps-border': 'rgba(255, 77, 219, 0.26)',
            '--card-details-bg': 'rgba(7, 14, 34, 0.72)',
            '--card-details-border': 'rgba(142, 255, 95, 0.24)',
            '--msg-user-bg': 'rgba(14, 49, 22, 0.52)',
            '--msg-user-border': 'rgba(142, 255, 95, 0.44)',
            '--msg-assistant-bg': 'rgba(8, 26, 49, 0.58)',
            '--msg-assistant-border': 'rgba(61, 240, 255, 0.42)',
            '--dialog-bg': 'rgba(6, 12, 32, 0.95)',
            '--danger': '#ff7085',
            '--ok': '#77ff93',
          },
          'cyber-lime': {
            '--bg-1': '#07170c',
            '--bg-2': '#103822',
            '--bg-3': '#0e2b1a',
            '--ink': '#edffec',
            '--muted': '#aad5b0',
            '--cyan': '#99ff45',
            '--lime': '#3df0ff',
            '--pink': '#ff58b9',
            '--orange': '#ffd164',
            '--panel': 'rgba(11, 30, 18, 0.9)',
            '--border': 'rgba(153, 255, 69, 0.35)',
            '--status-bg': 'rgba(10, 24, 16, 0.78)',
            '--status-border': 'rgba(153, 255, 69, 0.34)',
            '--deck-bg': 'rgba(12, 31, 20, 0.78)',
            '--deck-border': 'rgba(255, 88, 185, 0.24)',
            '--feed-bg': 'rgba(7, 20, 14, 0.72)',
            '--feed-border': 'rgba(61, 240, 255, 0.26)',
            '--composer-bg': 'rgba(10, 25, 17, 0.86)',
            '--composer-border': 'rgba(153, 255, 69, 0.3)',
            '--terminal-pane-bg': 'rgba(8, 20, 14, 0.8)',
            '--terminal-output-bg': 'rgba(3, 12, 8, 0.94)',
            '--terminal-output-ink': '#d8ffd9',
            '--ops-bg': 'rgba(27, 14, 20, 0.52)',
            '--steps-border': 'rgba(255, 88, 185, 0.3)',
            '--card-details-bg': 'rgba(10, 22, 15, 0.76)',
            '--card-details-border': 'rgba(61, 240, 255, 0.24)',
            '--msg-user-bg': 'rgba(19, 54, 25, 0.56)',
            '--msg-user-border': 'rgba(153, 255, 69, 0.45)',
            '--msg-assistant-bg': 'rgba(12, 32, 35, 0.58)',
            '--msg-assistant-border': 'rgba(61, 240, 255, 0.42)',
            '--dialog-bg': 'rgba(8, 24, 15, 0.95)',
            '--danger': '#ff7a96',
            '--ok': '#7dff9e',
          },
          'ocean-core': {
            '--bg-1': '#07122a',
            '--bg-2': '#0b2748',
            '--bg-3': '#081d39',
            '--ink': '#eaf6ff',
            '--muted': '#a1c6dd',
            '--cyan': '#55d0ff',
            '--lime': '#66ffe1',
            '--pink': '#7e9dff',
            '--orange': '#8ad2ff',
            '--panel': 'rgba(8, 24, 50, 0.9)',
            '--border': 'rgba(85, 208, 255, 0.35)',
            '--status-bg': 'rgba(8, 20, 44, 0.78)',
            '--status-border': 'rgba(85, 208, 255, 0.34)',
            '--deck-bg': 'rgba(10, 23, 49, 0.78)',
            '--deck-border': 'rgba(126, 157, 255, 0.28)',
            '--feed-bg': 'rgba(6, 18, 38, 0.72)',
            '--feed-border': 'rgba(85, 208, 255, 0.26)',
            '--composer-bg': 'rgba(8, 22, 45, 0.86)',
            '--composer-border': 'rgba(85, 208, 255, 0.3)',
            '--terminal-pane-bg': 'rgba(5, 16, 36, 0.8)',
            '--terminal-output-bg': 'rgba(2, 10, 25, 0.94)',
            '--terminal-output-ink': '#cbeeff',
            '--ops-bg': 'rgba(22, 15, 44, 0.5)',
            '--steps-border': 'rgba(126, 157, 255, 0.34)',
            '--card-details-bg': 'rgba(8, 20, 42, 0.76)',
            '--card-details-border': 'rgba(102, 255, 225, 0.24)',
            '--msg-user-bg': 'rgba(16, 44, 56, 0.56)',
            '--msg-user-border': 'rgba(102, 255, 225, 0.44)',
            '--msg-assistant-bg': 'rgba(11, 35, 61, 0.58)',
            '--msg-assistant-border': 'rgba(85, 208, 255, 0.42)',
            '--dialog-bg': 'rgba(6, 18, 39, 0.95)',
            '--danger': '#ff7a96',
            '--ok': '#7dffc9',
          },
        };
        const tokens = themes[String(kind || '').trim().toLowerCase()] || themes['neon-deck'];
        for (const [key, value] of Object.entries(tokens)) {
          root.style.setProperty(key, String(value));
        }
      }

      function setOpsCollapsed(flag, persist = false) {
        state.opsCollapsed = !!flag;
        document.body.classList.toggle('ops-collapsed', state.opsCollapsed);
        if (opsToggle) opsToggle.setAttribute('aria-expanded', String(!state.opsCollapsed));
        if (drawerToggle) drawerToggle.setAttribute('aria-expanded', String(!state.opsCollapsed));
        if (persist) saveProfile().catch((err) => setStatus(`profile warning: ${err.message}`, 'error'));
      }

      function pushMessage(role, text) {
        const normalizedRole = String(role || '').trim().toLowerCase() === 'user' ? 'user' : 'assistant';
        const normalizedText = String(text || '');
        messageLog.push({ role: normalizedRole, text: normalizedText, ts: Date.now() });
        if (messageLog.length > 400) {
          messageLog.splice(0, messageLog.length - 400);
        }
        const el = document.createElement('div');
        el.className = `msg ${normalizedRole}`;
        el.textContent = normalizedText;
        feed.appendChild(el);
        feed.scrollTop = feed.scrollHeight;
        syncChatPopoutFeed();
      }

      function clearFeed() {
        feed.innerHTML = '';
        messageLog.splice(0, messageLog.length);
        syncChatPopoutFeed();
      }

      function setInterfaceMode(mode, announce = true) {
        const next = String(mode || 'ask').trim().toLowerCase() === 'terminal' ? 'terminal' : 'ask';
        if (next === 'terminal' && String(state.activeRole || '') !== 'hacker') {
          if (announce) setStatus('Terminal mode is available when Hacker role is active.', 'info');
          return;
        }
        state.interfaceMode = next;
        const showTerminal = next === 'terminal';
        if (askPane) askPane.classList.toggle('dock-hidden', showTerminal);
        if (terminalPane) terminalPane.classList.toggle('dock-hidden', !showTerminal);
        if (modeAskBtn) modeAskBtn.setAttribute('aria-pressed', String(!showTerminal));
        if (modeTerminalBtn) modeTerminalBtn.setAttribute('aria-pressed', String(showTerminal));
        if (showTerminal) {
          const jobs = [];
          if (!terminalPresetsLoaded) jobs.push(loadTerminalPresets());
          if (!terminalProfilesLoaded) jobs.push(loadTerminalProfiles());
          if (jobs.length) {
            Promise.all(jobs).catch((err) => setStatus(`terminal setup error: ${err.message}`, 'error'));
          }
        }
        if (announce) setStatus(showTerminal ? 'hacker terminal mode ready' : 'ask mode ready', 'ok');
      }

      function setHackerInterfaceVisible(enabled) {
        const show = !!enabled;
        if (modeSwitchRow) modeSwitchRow.classList.toggle('dock-hidden', !show);
        if (!show) {
          setInterfaceMode('ask', false);
        } else if (state.interfaceMode === 'terminal') {
          setInterfaceMode('terminal', false);
        } else {
          setInterfaceMode('ask', false);
        }
      }

      function openInterfacePath(path) {
        try {
          const url = new URL(String(path || '/'), window.location.origin);
          window.open(url.toString(), '_blank', 'noopener');
          setStatus(`opened interface: ${url.pathname}`, 'ok');
        } catch (err) {
          setStatus(`open interface error: ${err.message}`, 'error');
        }
      }

      function ensureLiveLogPopoutOpen() {
        const features = 'popup=yes,width=1040,height=760,left=80,top=80';
        if (!liveLogPopoutWindow || liveLogPopoutWindow.closed) {
          liveLogPopoutWindow = window.open('', 'ccbsLiveLogPopout', features);
          if (!liveLogPopoutWindow) {
            throw new Error('pop-up was blocked by the browser');
          }
          const doc = liveLogPopoutWindow.document;
          doc.open();
          doc.write(`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>CCBS Live Terminal Output</title>
    <style>
      :root {
        color-scheme: dark;
      }
      body {
        margin: 0;
        padding: 12px;
        font-family: Consolas, Menlo, Monaco, 'Courier New', monospace;
        background: #04110c;
        color: #9dff8f;
      }
      .head {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 8px;
      }
      .stamp {
        color: #7dd4d9;
        font-size: 12px;
      }
      pre {
        margin: 0;
        border: 1px solid rgba(125, 212, 217, 0.35);
        border-radius: 10px;
        padding: 12px;
        min-height: calc(100vh - 78px);
        max-height: calc(100vh - 78px);
        overflow: auto;
        white-space: pre-wrap;
        line-height: 1.35;
        background: rgba(6, 20, 37, 0.86);
      }
    </style>
  </head>
  <body>
    <div class="head">
      <strong>CCBS Live Terminal Output</strong>
      <span id="ccbsLiveLogStamp" class="stamp">waiting...</span>
    </div>
    <pre id="ccbsLiveLogOutput">Waiting for terminal output...</pre>
  </body>
</html>`);
          doc.close();
        }
        try {
          liveLogPopoutWindow.focus();
        } catch (_) {}
        return liveLogPopoutWindow;
      }

      function syncLiveLogPopout(outputText) {
        if (!liveLogPopoutWindow || liveLogPopoutWindow.closed) return;
        try {
          const doc = liveLogPopoutWindow.document;
          const pre = doc.getElementById('ccbsLiveLogOutput');
          const stamp = doc.getElementById('ccbsLiveLogStamp');
          if (!pre) return;
          pre.textContent = String(outputText || '');
          pre.scrollTop = pre.scrollHeight;
          if (stamp) stamp.textContent = `updated ${new Date().toLocaleTimeString()}`;
        } catch (_) {}
      }

      function setTerminalOutputText(value, autoScroll = true) {
        if (!terminalOutput) return;
        terminalOutput.textContent = String(value || '');
        if (autoScroll) {
          terminalOutput.scrollTop = terminalOutput.scrollHeight;
        }
        syncLiveLogPopout(terminalOutput.textContent || '');
      }

      function openLiveLogPopout() {
        try {
          ensureLiveLogPopoutOpen();
          syncLiveLogPopout(terminalOutput ? String(terminalOutput.textContent || '') : '');
          setStatus('live terminal pop-out opened', 'ok');
        } catch (err) {
          setStatus(`live pop-out error: ${err.message}`, 'error');
        }
      }

      function postTaskWindowMessage(type, payload = {}) {
        if (!taskWindowPopout || taskWindowPopout.closed) return;
        try {
          taskWindowPopout.postMessage({ type, payload }, window.location.origin);
        } catch (_) {}
      }

      function syncTaskWindowDefaults() {
        postTaskWindowMessage('ccbs_task_window_config', {
          offline_mode: String(state.offlineMode || 'guided'),
          answer_scope: String(state.answerScope || 'repo_grounded'),
          active_role: String(state.activeRole || 'core'),
          remote_allowed_enabled: remoteFoundryGateOpen(),
          remote_gate_reason: remoteFoundryGateReason(),
          busy: !!taskWindowBusy,
        });
      }

      function ensureTaskWindowPopoutOpen() {
        const features = 'popup=yes,width=980,height=760,left=100,top=90';
        if (!taskWindowPopout || taskWindowPopout.closed) {
          taskWindowPopout = window.open('', 'ccbsTaskWindowPopout', features);
          if (!taskWindowPopout) {
            throw new Error('pop-up was blocked by the browser');
          }
          const doc = taskWindowPopout.document;
          doc.open();
          doc.write(`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>AI3 Autopilot</title>
    <style>
      :root { color-scheme: dark; }
      body {
        margin: 0;
        padding: 12px;
        font-family: Segoe UI, Inter, system-ui, -apple-system, sans-serif;
        background: #04110c;
        color: #dcffe2;
      }
      .head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
      }
      .muted {
        color: #8fb8a0;
        font-size: 12px;
      }
      .row {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 8px;
      }
      .field {
        display: grid;
        gap: 4px;
      }
      .field label {
        font-size: 12px;
        color: #8ce9f2;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      textarea, select {
        border: 1px solid rgba(125, 212, 217, 0.42);
        border-radius: 10px;
        padding: 10px;
        background: rgba(5, 16, 36, 0.84);
        color: #d8fff5;
      }
      textarea {
        width: 100%;
        min-height: 160px;
        resize: vertical;
        box-sizing: border-box;
      }
      button {
        border: 0;
        border-radius: 10px;
        padding: 10px 14px;
        font-weight: 700;
        letter-spacing: 0.04em;
        cursor: pointer;
      }
      button.primary { background: linear-gradient(120deg, #99ff45, #64fbd2); color: #04110c; }
      button.alt { background: rgba(12, 38, 28, 0.9); color: #9dff8f; border: 1px solid rgba(153, 255, 69, 0.36); }
      .status {
        margin: 8px 0;
        min-height: 22px;
        font-size: 13px;
        color: #8ce9f2;
      }
      pre {
        margin: 0;
        border: 1px solid rgba(125, 212, 217, 0.36);
        border-radius: 10px;
        min-height: 330px;
        max-height: 330px;
        overflow: auto;
        padding: 12px;
        white-space: pre-wrap;
        line-height: 1.38;
        background: rgba(6, 20, 37, 0.86);
        font-family: Consolas, Menlo, Monaco, 'Courier New', monospace;
      }
    </style>
  </head>
  <body>
    <div class="head">
      <strong>AI3 Autopilot</strong>
      <span class="muted">Give one task. Binary gates decide continue or stop. Local tools must be ready before Remote Allowed or Foundry.</span>
    </div>
    <div class="field">
      <label for="taskInput">Task</label>
      <textarea id="taskInput" placeholder="Example: create a python script that parses logs and summarize error rates per hour"></textarea>
    </div>
    <div class="row">
      <div class="field">
        <label for="taskMode">Mode</label>
        <select id="taskMode">
          <option value="auto">Auto</option>
          <option value="assistant">Assistant</option>
        </select>
      </div>
      <div class="field">
        <label for="taskScope">Scope</label>
        <select id="taskScope">
          <option value="repo_grounded">Repo Grounded</option>
          <option value="general_local">General Local</option>
          <option value="remote_allowed">Remote Allowed</option>
        </select>
      </div>
      <div class="field">
        <label for="taskOfflineMode">Offline Mode</label>
        <select id="taskOfflineMode">
          <option value="guided">Guided</option>
          <option value="strict">Strict</option>
          <option value="off">Off</option>
        </select>
      </div>
      <div class="field">
        <label for="taskRole">Role</label>
        <select id="taskRole">
          <option value="core">Core Agent</option>
          <option value="hacker">Hacker</option>
          <option value="retriever">Retriever</option>
          <option value="scientist">Scientist</option>
          <option value="strategist">Strategist</option>
          <option value="ranger">Ranger</option>
          <option value="guardian">Guardian</option>
          <option value="ops">Ops</option>
        </select>
      </div>
    </div>
    <div class="row">
      <button id="taskRun" type="button" class="primary">Run Autopilot</button>
      <button id="taskFocusMain" type="button" class="alt">Focus Main Window</button>
      <span id="taskStatus" class="status">Ready.</span>
    </div>
    <pre id="taskResult">No task run yet.</pre>
    <script>
      const taskInput = document.getElementById('taskInput');
      const taskMode = document.getElementById('taskMode');
      const taskScope = document.getElementById('taskScope');
      const taskOfflineMode = document.getElementById('taskOfflineMode');
      const taskRole = document.getElementById('taskRole');
      const taskRun = document.getElementById('taskRun');
      const taskFocusMain = document.getElementById('taskFocusMain');
      const taskStatus = document.getElementById('taskStatus');
      const taskResult = document.getElementById('taskResult');

      function postToMain(type, payload) {
        if (!window.opener) return;
        window.opener.postMessage({ type, payload }, window.location.origin || '*');
      }

      taskRun.addEventListener('click', () => {
        const task = String(taskInput.value || '').trim();
        if (!task) {
          taskStatus.textContent = 'Enter a task first.';
          return;
        }
        taskStatus.textContent = 'Running task...';
        postToMain('ccbs_task_window_run', {
          task,
          mode: String(taskMode.value || 'auto'),
          answer_scope: String(taskScope.value || 'repo_grounded'),
          offline_mode: String(taskOfflineMode.value || 'guided'),
          active_role: String(taskRole.value || 'core'),
        });
      });

      taskFocusMain.addEventListener('click', () => {
        if (window.opener && !window.opener.closed) {
          window.opener.focus();
        }
      });

      taskInput.addEventListener('keydown', (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
          event.preventDefault();
          taskRun.click();
        }
      });

      window.addEventListener('message', (event) => {
        if (event.origin && event.origin !== window.location.origin) return;
        const data = event.data || {};
        const payload = data.payload || {};
        if (data.type === 'ccbs_task_window_config') {
          if (payload.answer_scope) taskScope.value = String(payload.answer_scope);
          if (payload.offline_mode) taskOfflineMode.value = String(payload.offline_mode);
          if (payload.active_role) taskRole.value = String(payload.active_role);
          const remoteOpt = taskScope.querySelector('option[value="remote_allowed"]');
          const remoteEnabled = payload.remote_allowed_enabled !== false;
          if (remoteOpt) {
            remoteOpt.disabled = !remoteEnabled;
            remoteOpt.textContent = remoteEnabled ? 'Remote Allowed' : 'Remote Allowed (optimize local tools first)';
          }
          if (!remoteEnabled && taskScope.value === 'remote_allowed') {
            taskScope.value = 'repo_grounded';
          }
          if (typeof payload.busy !== 'undefined') taskRun.disabled = !!payload.busy;
          return;
        }
        if (data.type === 'ccbs_task_window_status') {
          taskStatus.textContent = String(payload.status || 'Ready.');
          if (typeof payload.busy !== 'undefined') taskRun.disabled = !!payload.busy;
          return;
        }
        if (data.type === 'ccbs_task_window_result') {
          taskStatus.textContent = String(payload.status || 'Task finished.');
          const lines = [];
          lines.push('Mode: ' + String(payload.mode || 'assistant'));
          if (typeof payload.ok !== 'undefined') lines.push('OK: ' + String(payload.ok));
          if (payload.provider_used) lines.push('Provider: ' + String(payload.provider_used));
          if (payload.run_status) lines.push('Run: ' + String(payload.run_status));
          if (payload.binary_gate && payload.binary_gate.reason) lines.push('Gate: ' + String(payload.binary_gate.reason));
          if (typeof payload.exit_code !== 'undefined') lines.push('Exit: ' + String(payload.exit_code));
          lines.push('');
          if (payload.output) lines.push(String(payload.output));
          if (payload.answer) lines.push(String(payload.answer));
          if (Array.isArray(payload.next_step_options) && payload.next_step_options.length) {
            lines.push('');
            lines.push('Next steps:');
            for (const item of payload.next_step_options) lines.push('- ' + String(item));
          }
          taskResult.textContent = lines.join('\\n').trim() || 'Task finished.';
          taskResult.scrollTop = taskResult.scrollHeight;
        }
      });
    <\\/script>
  </body>
</html>`);
          doc.close();
        }
        try {
          taskWindowPopout.focus();
        } catch (_) {}
        return taskWindowPopout;
      }

      async function runTaskWindowPayload(payload) {
        const task = String(payload && payload.task ? payload.task : '').trim();
        if (!task) {
          throw new Error('task is required');
        }
        const modeRaw = String(payload && payload.mode ? payload.mode : 'auto').trim().toLowerCase();
        const scope = normalizeAnswerScope(
          payload && payload.answer_scope ? payload.answer_scope : state.answerScope,
          state.answerScope || 'repo_grounded',
        );
        const desiredOffline = normalizeOfflineMode(
          payload && payload.offline_mode ? payload.offline_mode : state.offlineMode,
          state.offlineMode || 'guided',
        );
        const normalizedScope = desiredOffline === 'strict' && scope === 'remote_allowed' ? 'repo_grounded' : scope;
        const knownRoleIds = new Set((state.cards || []).map((row) => String(row.role_id || '').trim().toLowerCase()).filter(Boolean));
        const requestedRole = String(payload && payload.active_role ? payload.active_role : state.activeRole || 'core')
          .trim()
          .toLowerCase();
        const taskRole = knownRoleIds.has(requestedRole) ? requestedRole : 'core';

        const mode = modeRaw === 'assistant' ? 'assistant' : 'auto';
        if (normalizedScope === 'remote_allowed' && !remoteFoundryGateOpen()) {
          throw new Error(remoteFoundryGateReason());
        }

        let decisionPayload = state.languageDecision;
        try {
          decisionPayload = await requestLanguageDecision(task, false);
        } catch (_) {}
        if (applyScopeGuidanceFromDecision(decisionPayload, true)) {
          throw new Error('Scope confirmation required before AI3 Autopilot execution.');
        }
        const model = selectedModel();
        const behavior = roleBehavior(taskRole);
        let forcedOffline = behavior.enforce_offline_only === true ? true : !!offlineOnly.checked;
        let forcedRemote = behavior.enforce_allow_remote === false ? false : !!allowRemote.checked;
        if (desiredOffline === 'strict') {
          forcedOffline = true;
          forcedRemote = false;
        }
        const topK = Math.max(8, Number(topKInput ? topKInput.value : 8) || 8);
        const out = await api('/v3/chat/send', {
          method: 'POST',
          body: JSON.stringify({
            thread_id: state.threadId || '',
            message: task,
            model_key: model ? model.key : '',
            provider: model ? model.provider : '',
            model: model ? model.model : '',
            base_url: model ? model.base_url : '',
            offline_mode: desiredOffline,
            offline_only: forcedOffline,
            allow_remote: forcedRemote,
            top_k: topK,
            active_role: taskRole,
            role_hint: `AI3 Autopilot (${taskRole})`,
            ui_surface: state.surface,
            answer_scope: normalizedScope,
            scope_confirmed: !!state.scopeConfirmed,
            language_mode: 'auto',
            manual_language: '',
            language_storage_mode: normalizeLanguageStorageMode(state.languageStorageMode || 'auto', 'auto'),
            language_external_enrichment: !!state.languageExternalEnrichment,
            decision_payload: decisionPayload || {},
          }),
        });

        if (out.thread_id) {
          const changed = state.threadId !== out.thread_id;
          updateThread(out.thread_id);
          if (changed) await loadCards();
        }
        const answer = (out.assistant_message && out.assistant_message.content) || out.answer || '';
        pushMessage('user', `[AI3 Autopilot] ${task}`);
        if (answer) pushMessage('assistant', answer);
        if (out.language_decision) {
          state.languageDecision = out.language_decision;
          renderLanguageDecision(state.languageDecision);
        }
        state.pendingApprovals = Array.isArray(out.requires_action) ? out.requires_action : [];
        renderSteps(out.step_summary || [], out.run_status || '');
        if (String(out.ops_hint || '') === 'expand') setOpsCollapsed(false, false);
        if (out.role_applied) applyRole(out.role_applied, false, false);
        if (typeof out.scope_confirmed !== 'undefined') state.scopeConfirmed = !!out.scope_confirmed;
        if (out.answer_scope) setScope(out.answer_scope, !!out.scope_confirmed);
        await loadApiEvents().catch(() => {});
        const langDecision = out.language_decision || decisionPayload || {};
        const langNote = langDecision && langDecision.selected_language ? ` · language ${langDecision.selected_language}` : '';
        setStatus(`AI3 Autopilot ${out.run_status || 'completed'} via ${out.provider_used || 'local'}${langNote}`, 'ok');
        return {
          mode,
          ok: !!out.ok,
          status: out.ok ? 'AI3 Autopilot completed.' : `AI3 Autopilot finished with status ${out.run_status || 'unknown'}.`,
          answer,
          run_status: out.run_status,
          provider_used: out.provider_used,
          binary_gate: out.binary_gate || {},
          next_step_options: Array.isArray(out.next_step_options) ? out.next_step_options : [],
        };
      }

      async function handleTaskWindowRun(payload) {
        if (taskWindowBusy) {
          postTaskWindowMessage('ccbs_task_window_status', { status: 'AI3 Autopilot is already running. Please wait.', busy: true });
          return;
        }
        taskWindowBusy = true;
        syncTaskWindowDefaults();
        postTaskWindowMessage('ccbs_task_window_status', { status: 'AI3 Autopilot accepted. Running...', busy: true });
        try {
          const result = await runTaskWindowPayload(payload || {});
          postTaskWindowMessage('ccbs_task_window_result', result);
        } catch (err) {
          const message = String(err && err.message ? err.message : err || 'task failed');
          postTaskWindowMessage('ccbs_task_window_result', { ok: false, status: `AI3 Autopilot failed: ${message}`, mode: 'assistant', output: message });
          setStatus(`AI3 Autopilot error: ${message}`, 'error');
        } finally {
          taskWindowBusy = false;
          syncTaskWindowDefaults();
        }
      }

      function openTaskWindowPopout() {
        try {
          ensureTaskWindowPopoutOpen();
          syncTaskWindowDefaults();
          postTaskWindowMessage('ccbs_task_window_status', { status: 'Ready.', busy: !!taskWindowBusy });
          setStatus('AI3 Autopilot opened', 'ok');
        } catch (err) {
          setStatus(`AI3 Autopilot error: ${err.message}`, 'error');
        }
      }

      function postChatPopoutMessage(type, payload = {}) {
        if (!chatPopoutWindow || chatPopoutWindow.closed) return;
        try {
          chatPopoutWindow.postMessage({ type, payload }, window.location.origin);
        } catch (_) {}
      }

      function syncChatPopoutFeed() {
        postChatPopoutMessage('ccbs_chat_popout_feed', {
          messages: messageLog.slice(-220),
          busy: !!(sendBtn && sendBtn.disabled),
          active_role: String(state.activeRole || 'core'),
          answer_scope: String(state.answerScope || 'repo_grounded'),
          offline_mode: String(state.offlineMode || 'guided'),
        });
      }

      function ensureChatPopoutOpen() {
        const features = 'popup=yes,width=980,height=760,left=120,top=100';
        if (!chatPopoutWindow || chatPopoutWindow.closed) {
          chatPopoutWindow = window.open('', 'ccbsChatPopout', features);
          if (!chatPopoutWindow) throw new Error('pop-up was blocked by the browser');
          const doc = chatPopoutWindow.document;
          doc.open();
          doc.write(`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>CCBS Chat Pop Out</title>
    <style>
      :root { color-scheme: dark; }
      body {
        margin: 0;
        padding: 12px;
        font-family: Segoe UI, Inter, system-ui, -apple-system, sans-serif;
        background: #04110c;
        color: #ddffe4;
      }
      .head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
      .meta { color: #8ce9f2; font-size: 12px; }
      .status { min-height: 22px; color: #8ce9f2; margin-bottom: 8px; font-size: 13px; }
      pre {
        margin: 0 0 8px 0;
        border: 1px solid rgba(125, 212, 217, 0.36);
        border-radius: 10px;
        min-height: 420px;
        max-height: 420px;
        overflow: auto;
        padding: 12px;
        white-space: pre-wrap;
        line-height: 1.36;
        background: rgba(6, 20, 37, 0.86);
        font-family: Consolas, Menlo, Monaco, 'Courier New', monospace;
      }
      textarea {
        width: 100%;
        min-height: 110px;
        resize: vertical;
        box-sizing: border-box;
        border: 1px solid rgba(153, 255, 69, 0.35);
        border-radius: 10px;
        padding: 10px;
        background: rgba(8, 20, 14, 0.85);
        color: #d8fff5;
      }
      .row { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
      .toggle {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: #9dff8f;
      }
      select {
        border: 1px solid rgba(153, 255, 69, 0.35);
        border-radius: 10px;
        padding: 8px 10px;
        background: rgba(8, 20, 14, 0.85);
        color: #d8fff5;
      }
      button {
        border: 0;
        border-radius: 10px;
        padding: 10px 14px;
        font-weight: 700;
        letter-spacing: 0.04em;
        cursor: pointer;
      }
      button.primary { background: linear-gradient(120deg, #99ff45, #64fbd2); color: #04110c; }
      button.alt { background: rgba(12, 38, 28, 0.9); color: #9dff8f; border: 1px solid rgba(153, 255, 69, 0.36); }
    </style>
  </head>
  <body>
    <div class="head">
      <strong>CCBS Chat Pop Out</strong>
      <span id="chatMeta" class="meta">role=core · scope=repo_grounded · mode=guided</span>
    </div>
    <div id="chatStatus" class="status">Ready.</div>
    <pre id="chatFeed">No messages yet.</pre>
    <textarea id="chatInput" placeholder="Ask a question while terminal stays open in the main window..."></textarea>
    <div class="row">
      <button id="chatSend" type="button" class="primary">Send to AI</button>
      <button id="chatVoice" type="button" class="alt">Voice Input</button>
      <button id="chatFocusMain" type="button" class="alt">Focus Main Window</button>
      <label class="toggle" for="chatRouteRole">Route As</label>
      <select id="chatRouteRole">
        <option value="strategist">General Planning</option>
        <option value="samurai">Samurai Verbal → Code</option>
        <option value="current">Current Role</option>
        <option value="hacker">Hacker (Code Only)</option>
      </select>
    </div>
    <script>
      const chatMeta = document.getElementById('chatMeta');
      const chatStatus = document.getElementById('chatStatus');
      const chatFeed = document.getElementById('chatFeed');
      const chatInput = document.getElementById('chatInput');
      const chatSend = document.getElementById('chatSend');
      const chatVoice = document.getElementById('chatVoice');
      const chatFocusMain = document.getElementById('chatFocusMain');
      const chatRouteRole = document.getElementById('chatRouteRole');

      function postToMain(type, payload) {
        if (!window.opener) return;
        window.opener.postMessage({ type, payload }, window.location.origin || '*');
      }

      chatSend.addEventListener('click', () => {
        const message = String(chatInput.value || '').trim();
        if (!message) {
          chatStatus.textContent = 'Enter a question first.';
          return;
        }
        chatStatus.textContent = 'Sending to AI...';
        postToMain('ccbs_chat_popout_send', {
          message,
          route_role: String(chatRouteRole && chatRouteRole.value ? chatRouteRole.value : 'strategist'),
        });
      });

      chatInput.addEventListener('keydown', (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
          event.preventDefault();
          chatSend.click();
        }
      });

      chatFocusMain.addEventListener('click', () => {
        if (window.opener && !window.opener.closed) window.opener.focus();
      });

      let voiceRecognizer = null;
      let voiceActive = false;
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition || null;
      if (chatVoice && SpeechRecognition) {
        voiceRecognizer = new SpeechRecognition();
        voiceRecognizer.lang = 'en-US';
        voiceRecognizer.interimResults = true;
        voiceRecognizer.maxAlternatives = 1;
        voiceRecognizer.onresult = (event) => {
          let finalText = '';
          let interim = '';
          for (let i = event.resultIndex; i < event.results.length; i += 1) {
            const phrase = String(event.results[i][0] && event.results[i][0].transcript ? event.results[i][0].transcript : '');
            if (event.results[i].isFinal) finalText += phrase + ' ';
            else interim += phrase + ' ';
          }
          if (finalText.trim()) {
            const prev = String(chatInput.value || '').trim();
            chatInput.value = (prev ? `${prev} ` : '') + finalText.trim();
            chatStatus.textContent = 'Voice captured.';
          } else if (interim.trim()) {
            chatStatus.textContent = `Listening: ${interim.trim()}`;
          }
        };
        voiceRecognizer.onerror = (event) => {
          voiceActive = false;
          chatVoice.textContent = 'Voice Input';
          chatStatus.textContent = `Voice error: ${String(event.error || 'unknown')}`;
        };
        voiceRecognizer.onend = () => {
          voiceActive = false;
          chatVoice.textContent = 'Voice Input';
        };
        chatVoice.addEventListener('click', () => {
          if (!voiceRecognizer) return;
          if (voiceActive) {
            voiceRecognizer.stop();
            return;
          }
          try {
            voiceActive = true;
            chatVoice.textContent = 'Stop Voice';
            chatStatus.textContent = 'Listening...';
            voiceRecognizer.start();
          } catch (err) {
            voiceActive = false;
            chatVoice.textContent = 'Voice Input';
            chatStatus.textContent = `Voice error: ${String(err && err.message ? err.message : err)}`;
          }
        });
      } else if (chatVoice) {
        chatVoice.disabled = true;
        chatVoice.title = 'Voice input not supported in this browser';
      }

      window.addEventListener('message', (event) => {
        if (event.origin && event.origin !== window.location.origin) return;
        const data = event.data || {};
        const payload = data.payload || {};
        if (data.type === 'ccbs_chat_popout_feed') {
          const rows = Array.isArray(payload.messages) ? payload.messages : [];
          if (rows.length) {
            chatFeed.textContent = rows.map((row) => {
              const role = String(row.role || 'assistant').toLowerCase() === 'user' ? 'YOU' : 'AI';
              return '[' + role + '] ' + String(row.text || '');
            }).join('\\n\\n');
          } else {
            chatFeed.textContent = 'No messages yet.';
          }
          chatFeed.scrollTop = chatFeed.scrollHeight;
          chatSend.disabled = !!payload.busy;
          chatMeta.textContent = 'role=' + String(payload.active_role || 'core')
            + ' · scope=' + String(payload.answer_scope || 'repo_grounded')
            + ' · mode=' + String(payload.offline_mode || 'guided');
          return;
        }
        if (data.type === 'ccbs_chat_popout_status') {
          chatStatus.textContent = String(payload.status || 'Ready.');
          if (typeof payload.busy !== 'undefined') chatSend.disabled = !!payload.busy;
        }
      });
    <\\/script>
  </body>
</html>`);
          doc.close();
        }
        try { chatPopoutWindow.focus(); } catch (_) {}
        return chatPopoutWindow;
      }

      async function handleChatPopoutSend(payload) {
        const text = String(payload && payload.message ? payload.message : '').trim();
        const routeRole = String(payload && payload.route_role ? payload.route_role : 'strategist').trim().toLowerCase();
        if (!text) {
          postChatPopoutMessage('ccbs_chat_popout_status', { status: 'No message provided.', busy: false });
          return;
        }
        if (sendBtn && sendBtn.disabled) {
          postChatPopoutMessage('ccbs_chat_popout_status', { status: 'Main chat is busy. Please wait.', busy: true });
          return;
        }
        const knownRoles = new Set((state.cards || []).map((row) => String(row.role_id || '').trim().toLowerCase()).filter(Boolean));
        let targetRole = String(state.activeRole || 'core').trim().toLowerCase();
        if (routeRole !== 'current') {
          if (knownRoles.has(routeRole)) {
            targetRole = routeRole;
          } else if (routeRole === 'strategist') {
            targetRole = knownRoles.has('strategist') ? 'strategist' : targetRole;
          }
        }
        if (targetRole && targetRole !== String(state.activeRole || '').trim().toLowerCase()) {
          applyRole(targetRole, false, false);
          saveProfile().catch(() => {});
        }
        if (promptInput) promptInput.value = text;
        postChatPopoutMessage('ccbs_chat_popout_status', { status: `Running as ${targetRole || 'current'}...`, busy: true });
        try {
          await sendPrompt();
          const latest = [...messageLog].reverse().find((row) => String(row.role || '') === 'assistant');
          postChatPopoutMessage('ccbs_chat_popout_status', {
            status: latest ? 'Answer received.' : 'Run finished.',
            busy: false,
          });
          syncChatPopoutFeed();
        } catch (err) {
          const message = String(err && err.message ? err.message : err || 'chat send failed');
          postChatPopoutMessage('ccbs_chat_popout_status', { status: `Error: ${message}`, busy: false });
          throw err;
        }
      }

      function openChatPopout() {
        try {
          ensureChatPopoutOpen();
          syncChatPopoutFeed();
          postChatPopoutMessage('ccbs_chat_popout_status', { status: 'Ready.', busy: !!(sendBtn && sendBtn.disabled) });
          setStatus('chat pop-out opened', 'ok');
        } catch (err) {
          setStatus(`chat pop-out error: ${err.message}`, 'error');
        }
      }

      function postDeckPopoutMessage(type, payload = {}) {
        if (!deckPopoutWindow || deckPopoutWindow.closed) return;
        try {
          deckPopoutWindow.postMessage({ type, payload }, window.location.origin);
        } catch (_) {}
      }

      function syncDeckPopout() {
        const cards = (state.cards || []).map((row) => ({
          role_id: String(row.role_id || ''),
          label: String(row.label || row.role_id || ''),
          utility_mode: String(row.utility_mode || ''),
          description: String(row.description || ''),
          icon: String(row.icon || '◎'),
        }));
        postDeckPopoutMessage('ccbs_deck_popout_data', {
          cards,
          active_role: String(state.activeRole || 'core'),
          offline_mode: String(state.offlineMode || 'guided'),
        });
      }

      function ensureDeckPopoutOpen() {
        const features = 'popup=yes,width=560,height=760,left=1130,top=100';
        if (!deckPopoutWindow || deckPopoutWindow.closed) {
          deckPopoutWindow = window.open('', 'ccbsDeckPopout', features);
          if (!deckPopoutWindow) throw new Error('pop-up was blocked by the browser');
          const doc = deckPopoutWindow.document;
          doc.open();
          doc.write(`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>CCBS Card Deck Pop Out</title>
    <style>
      :root { color-scheme: dark; }
      body {
        margin: 0;
        padding: 12px;
        font-family: Segoe UI, Inter, system-ui, -apple-system, sans-serif;
        background: #04110c;
        color: #ddffe4;
      }
      .head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
      .meta { font-size: 12px; color: #8ce9f2; }
      .deck { display: grid; gap: 8px; max-height: calc(100vh - 86px); overflow: auto; }
      button.card {
        text-align: left;
        border: 1px solid rgba(153, 255, 69, 0.35);
        background: rgba(7, 23, 17, 0.88);
        border-radius: 10px;
        color: #d8fff5;
        padding: 10px;
        cursor: pointer;
      }
      button.card.active {
        border-color: rgba(97, 254, 211, 0.8);
        box-shadow: 0 0 0 1px rgba(97, 254, 211, 0.28);
      }
      .name { font-weight: 800; letter-spacing: 0.04em; }
      .mode { font-size: 12px; color: #8ce9f2; margin-top: 4px; }
      .desc { font-size: 12px; color: #bcd9c6; margin-top: 4px; }
    </style>
  </head>
  <body>
    <div class="head">
      <strong>CCBS Card Deck Pop Out</strong>
      <span id="deckMeta" class="meta">active=core · mode=guided</span>
    </div>
    <div id="deckList" class="deck">No cards yet.</div>
    <script>
      const deckList = document.getElementById('deckList');
      const deckMeta = document.getElementById('deckMeta');

      function postToMain(type, payload) {
        if (!window.opener) return;
        window.opener.postMessage({ type, payload }, window.location.origin || '*');
      }

      window.addEventListener('message', (event) => {
        if (event.origin && event.origin !== window.location.origin) return;
        const data = event.data || {};
        const payload = data.payload || {};
        if (data.type !== 'ccbs_deck_popout_data') return;
        const cards = Array.isArray(payload.cards) ? payload.cards : [];
        const activeRole = String(payload.active_role || 'core');
        deckMeta.textContent = 'active=' + activeRole + ' · mode=' + String(payload.offline_mode || 'guided');
        deckList.innerHTML = '';
        if (!cards.length) {
          deckList.textContent = 'No cards yet.';
          return;
        }
        for (const card of cards) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'card' + (String(card.role_id || '') === activeRole ? ' active' : '');
          const name = document.createElement('div');
          name.className = 'name';
          name.textContent = String(card.icon || '◎') + ' ' + String(card.label || card.role_id || 'role');
          const mode = document.createElement('div');
          mode.className = 'mode';
          mode.textContent = String(card.utility_mode || card.role_id || '');
          const desc = document.createElement('div');
          desc.className = 'desc';
          desc.textContent = String(card.description || '');
          btn.appendChild(name);
          btn.appendChild(mode);
          if (desc.textContent) btn.appendChild(desc);
          btn.addEventListener('click', () => {
            postToMain('ccbs_deck_popout_select_role', { role_id: String(card.role_id || '') });
          });
          deckList.appendChild(btn);
        }
      });
    <\\/script>
  </body>
</html>`);
          doc.close();
        }
        try { deckPopoutWindow.focus(); } catch (_) {}
        return deckPopoutWindow;
      }

      function openDeckPopout() {
        try {
          ensureDeckPopoutOpen();
          syncDeckPopout();
          setStatus('card deck pop-out opened', 'ok');
        } catch (err) {
          setStatus(`card deck pop-out error: ${err.message}`, 'error');
        }
      }

      async function loadTerminalPresets() {
        if (!terminalPresetSelect) return;
        const out = await api('/v3/chat/terminal/presets');
        let rows = Array.isArray(out.presets) ? out.presets : [];
        state.terminalPresets = rows;
        if (state.offlineMode === 'strict') {
          rows = rows.filter((row) => !!row.offline_safe && !row.requires_network);
        }
        terminalPresetSelect.innerHTML = '';
        for (const row of rows) {
          const opt = document.createElement('option');
          opt.value = String(row.preset_id || '');
          const desc = String(row.description || '').trim();
          const tags = [];
          if (!row.offline_safe) tags.push('not-offline-safe');
          if (row.requires_network) tags.push('network');
          if (row.requires_confirmation) tags.push('confirm');
          const suffix = tags.length ? ` [${tags.join(', ')}]` : '';
          opt.textContent = desc ? `${row.label || row.preset_id} - ${desc}${suffix}` : `${String(row.label || row.preset_id || '')}${suffix}`;
          terminalPresetSelect.appendChild(opt);
        }
        if (!rows.length) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = 'No terminal presets available';
          terminalPresetSelect.appendChild(opt);
        }
        terminalPresetsLoaded = true;
        if (terminalOutput && !terminalOutput.textContent.trim()) {
          setTerminalOutputText('Type a command and click Run Command, or use presets/profiles.');
        }
      }

      async function loadTerminalProfiles() {
        if (!terminalProfileSelect) return;
        const out = await api('/v3/chat/terminal/profiles');
        let rows = Array.isArray(out.profiles) ? out.profiles : [];
        state.terminalProfiles = rows;
        if (state.offlineMode === 'strict') {
          rows = rows.filter((row) => !!row.offline_safe && !row.requires_network);
        }
        terminalProfileSelect.innerHTML = '';
        for (const row of rows) {
          const opt = document.createElement('option');
          opt.value = String(row.profile_id || '');
          const desc = String(row.description || '').trim();
          const tags = [];
          if (!row.offline_safe) tags.push('not-offline-safe');
          if (row.requires_network) tags.push('network');
          if (row.requires_confirmation) tags.push('confirm');
          const suffix = tags.length ? ` [${tags.join(', ')}]` : '';
          opt.textContent = desc ? `${row.label || row.profile_id} - ${desc}${suffix}` : `${String(row.label || row.profile_id || '')}${suffix}`;
          terminalProfileSelect.appendChild(opt);
        }
        if (!rows.length) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = 'No terminal profiles available';
          terminalProfileSelect.appendChild(opt);
        }
        terminalProfilesLoaded = true;
      }

      function resolveAvailableTerminalProfile(preferredId = '') {
        const rows = Array.isArray(state.terminalProfiles) ? state.terminalProfiles : [];
        const available = state.offlineMode === 'strict'
          ? rows.filter((row) => !!row.offline_safe && !row.requires_network)
          : rows;
        const order = [];
        if (preferredId) order.push(String(preferredId).trim());
        order.push('powershell', 'cmd', 'git_bash', 'wsl_bash', 'python_repl');
        for (const candidate of order) {
          if (!candidate) continue;
          const found = available.find((row) => String(row.profile_id || '') === candidate);
          if (found) return String(found.profile_id || '');
        }
        return available.length ? String(available[0].profile_id || '') : '';
      }

      async function runTerminalPreset() {
        if (!terminalPresetSelect || !terminalOutput) return;
        const presetId = String(terminalPresetSelect.value || '').trim();
        if (!presetId) {
          setStatus('select a terminal preset first', 'info');
          return;
        }
        const presetMeta = (state.terminalPresets || []).find((row) => String(row.preset_id || '') === presetId) || {};
        const timeoutRaw = Number(presetMeta.timeout_sec || 25);
        const timeoutSec = Number.isFinite(timeoutRaw) ? Math.max(3, Math.min(300, Math.floor(timeoutRaw))) : 25;
        let confirmed = false;
        if (presetMeta.requires_confirmation || presetMeta.requires_network) {
          const ok = await confirmAction({
            title: `Run preset: ${presetMeta.label || presetId}`,
            body: `Command: ${presetMeta.command_preview || presetId}\nMode: ${state.offlineMode}\nProceed?`,
            confirmLabel: 'Run Preset',
          });
          if (!ok) {
            setStatus('preset run cancelled', 'info');
            return;
          }
          confirmed = true;
        }
        if (presetMeta.stream_output) {
          await runTerminalPresetStreaming(presetId, timeoutSec, confirmed);
          return;
        }
        if (terminalRunBtn) terminalRunBtn.disabled = true;
        setStatus(`running terminal preset: ${presetId}`, 'info');
        try {
          const out = await api('/v3/chat/terminal/run', {
            method: 'POST',
            body: JSON.stringify({ preset_id: presetId, timeout_sec: timeoutSec, offline_mode: state.offlineMode, confirmed }),
          });
          const lines = [];
          lines.push(`$ ${out.command || presetId}`);
          lines.push(`cwd: ${out.cwd || ''}`);
          lines.push(`timeout: ${timeoutSec}s`);
          lines.push(`exit: ${out.exit_code}${out.timed_out ? ' (timeout)' : ''}`);
          lines.push('');
          if (String(out.stdout || '').trim()) {
            lines.push(String(out.stdout));
          } else {
            lines.push('(no stdout)');
          }
          if (String(out.stderr || '').trim()) {
            lines.push('');
            lines.push('stderr:');
            lines.push(String(out.stderr));
          }
          setTerminalOutputText(lines.join('\\n'));
          setStatus(out.ok ? `terminal preset succeeded: ${presetId}` : `terminal preset finished with exit ${out.exit_code}`, out.ok ? 'ok' : 'error');
          await loadApiEvents().catch(() => {});
        } catch (err) {
          setTerminalOutputText(`error: ${err.message}`);
          setStatus(`terminal run error: ${err.message}`, 'error');
        } finally {
          if (terminalRunBtn) terminalRunBtn.disabled = false;
        }
      }

      async function runTerminalPresetStreaming(presetId, timeoutSec = 120, confirmed = false) {
        if (!terminalOutput) return;
        if (terminalRunBtn) terminalRunBtn.disabled = true;
        setStatus(`starting streamed terminal preset: ${presetId}`, 'info');
        try {
          const start = await api('/v3/chat/terminal/run-stream-start', {
            method: 'POST',
            body: JSON.stringify({ preset_id: presetId, timeout_sec: timeoutSec, offline_mode: state.offlineMode, confirmed }),
          });
          const runId = String(start.run_id || '').trim();
          if (!runId) throw new Error('missing run_id from stream start');

          let finished = false;
          for (let attempt = 0; attempt < 1000; attempt += 1) {
            const out = await api(`/v3/chat/terminal/run-stream-status?run_id=${encodeURIComponent(runId)}`);
            const lines = [];
            lines.push(`$ ${out.command || presetId}`);
            lines.push(`cwd: ${out.cwd || ''}`);
            lines.push(`timeout: ${out.timeout_sec || timeoutSec}s`);
            lines.push(`state: ${out.finished ? 'finished' : 'running'}`);
            lines.push('');
            if (String(out.stdout || '').length > 0) {
              lines.push(String(out.stdout));
            } else {
              lines.push('(no stdout yet)');
            }
            if (String(out.stderr || '').length > 0) {
              lines.push('');
              lines.push('stderr:');
              lines.push(String(out.stderr));
            }
            if (out.stdout_truncated || out.stderr_truncated) {
              lines.push('');
              lines.push('note: output was truncated to keep terminal responsive');
            }
            setTerminalOutputText(lines.join('\\n'));
            if (out.finished) {
              finished = true;
              setStatus(out.ok ? `terminal preset succeeded: ${presetId}` : `terminal preset finished with exit ${out.exit_code}`, out.ok ? 'ok' : 'error');
              break;
            }
            await new Promise((resolve) => setTimeout(resolve, 220));
          }
          if (!finished) {
            setStatus(`terminal stream timed out in client view: ${presetId}`, 'error');
          }
          await loadApiEvents().catch(() => {});
        } catch (err) {
          setTerminalOutputText(`error: ${err.message}`);
          setStatus(`terminal stream error: ${err.message}`, 'error');
        } finally {
          if (terminalRunBtn) terminalRunBtn.disabled = false;
        }
      }

      async function runTerminalCommand() {
        if (!terminalCommandInput || !terminalOutput) return;
        const command = String(terminalCommandInput.value || '').trim();
        if (!command) {
          setStatus('enter a command first', 'info');
          return;
        }
        if (state.offlineMode === 'strict') {
          setStatus('strict mode blocks direct terminal exec; use a reviewed preset/profile or switch offline mode', 'error');
          return;
        }
        const ok = await confirmAction({
          title: 'Run Direct Terminal Command',
          body: `Direct terminal exec runs arbitrary shell code.\nCommand: ${command}\nMode: ${state.offlineMode}\nProceed?`,
          confirmLabel: 'Run Command',
        });
        if (!ok) {
          setStatus('terminal command cancelled', 'info');
          return;
        }
        if (terminalExecBtn) terminalExecBtn.disabled = true;
        setStatus(`running terminal command: ${command}`, 'info');
        try {
          const out = await api('/v3/chat/terminal/exec', {
            method: 'POST',
            body: JSON.stringify({ command, timeout_sec: 60, offline_mode: state.offlineMode, confirmed: true }),
          });
          const lines = [];
          lines.push(`$ ${out.command || command}`);
          lines.push(`shell: ${out.shell_command || ''}`);
          lines.push(`cwd: ${out.cwd || ''}`);
          lines.push(`exit: ${out.exit_code}${out.timed_out ? ' (timeout)' : ''}`);
          lines.push('');
          if (String(out.stdout || '').trim()) {
            lines.push(String(out.stdout));
          } else {
            lines.push('(no stdout)');
          }
          if (String(out.stderr || '').trim()) {
            lines.push('');
            lines.push('stderr:');
            lines.push(String(out.stderr));
          }
          setTerminalOutputText(lines.join('\\n'));
          setStatus(out.ok ? 'terminal command succeeded' : `terminal command exited ${out.exit_code}`, out.ok ? 'ok' : 'error');
          await loadApiEvents().catch(() => {});
        } catch (err) {
          setTerminalOutputText(`error: ${err.message}`);
          setStatus(`terminal command error: ${err.message}`, 'error');
        } finally {
          if (terminalExecBtn) terminalExecBtn.disabled = false;
        }
      }

      async function runTerminalPresetById(presetId) {
        if (!terminalPresetSelect) return;
        const target = String(presetId || '').trim();
        if (!target) return;
        if (!terminalPresetsLoaded) {
          await loadTerminalPresets();
        }
        const exists = Array.from(terminalPresetSelect.options || []).some((opt) => String(opt.value || '') === target);
        if (!exists) {
          setStatus(`terminal preset not available: ${target}`, 'error');
          return;
        }
        terminalPresetSelect.value = target;
        await runTerminalPreset();
      }

      async function runTerminalAudit() {
        if (terminalOutput) setTerminalOutputText('Running preset audit...');
        const out = await api('/v3/chat/terminal/audit', {
          method: 'POST',
          body: JSON.stringify({ offline_mode: state.offlineMode, timeout_sec: 25 }),
        });
        const rows = Array.isArray(out.results) ? out.results : [];
        const lines = [];
        lines.push(`Preset audit mode=${out.offline_mode || state.offlineMode} overall=${out.ok ? 'PASS' : 'FAIL'}`);
        lines.push('');
        for (const row of rows) {
          lines.push(`[${row.ok ? 'OK' : 'FAIL'}] ${row.preset_id} exit=${row.exit_code} reason=${row.reason}`);
          if (row.stderr_tail) lines.push(`  stderr: ${String(row.stderr_tail).split('\\n')[0]}`);
        }
        if (terminalOutput) setTerminalOutputText(lines.join('\\n'));
        setStatus(out.ok ? 'preset audit passed' : 'preset audit found issues', out.ok ? 'ok' : 'error');
        await loadApiEvents().catch(() => {});
      }

      async function runCapabilityFix(actionId, label, lane = '') {
        const id = String(actionId || '').trim().toLowerCase();
        if (!id) return;
        const ok = await confirmAction({
          title: label || `Run ${id}`,
          body: `This runs guided remediation action "${id}" and may install dependencies.\nMode: ${state.offlineMode}\nProceed?`,
          confirmLabel: 'Run Fix',
        });
        if (!ok) {
          setStatus('capability remediation cancelled', 'info');
          return;
        }
        setStatus(`running capability remediation: ${id}`, 'info');
        const out = await api('/v3/chat/capabilities/remediate', {
          method: 'POST',
          body: JSON.stringify({ action_id: id, approve: true, lane }),
        });
        const verify = out.verify || {};
        const lines = [];
        lines.push(`Capability remediation: ${id}`);
        lines.push(`status=${out.status || 'unknown'} ok=${out.ok ? 'true' : 'false'}`);
        lines.push(`overall_ready=${verify.overall_ready ? 'true' : 'false'}`);
        if (Array.isArray(out.steps)) {
          for (const row of out.steps) {
            lines.push(`- ${row.step || 'step'} ok=${row.ok ? 'true' : 'false'} exit=${row.exit_code}`);
            if (row.stderr) lines.push(`  stderr: ${String(row.stderr).split('\\n')[0]}`);
          }
        }
        if (Array.isArray(out.executed_actions)) {
          for (const row of out.executed_actions) {
            lines.push(`- action ${row.action_id || 'unknown'} ok=${row.ok ? 'true' : 'false'}`);
          }
        }
        if (terminalOutput) setTerminalOutputText(lines.join('\\n'));
        await Promise.all([loadOfflineCapabilities(), loadApiEvents()]).catch(() => {});
        setStatus(out.ok ? `capability fix complete: ${id}` : `capability fix incomplete: ${id}`, out.ok ? 'ok' : 'error');
      }

      async function runRoleAction(action) {
        const id = String((action && action.id) || '').trim();
        if (!id) return;
        if (id === 'open_compass') {
          openNeonCompass(true);
          return;
        }
        if (id === 'set_strict') {
          applyOfflineMode('strict', true);
          await saveProfile();
          await Promise.all([loadTerminalPresets(), loadTerminalProfiles(), loadOfflineCapabilities()]);
          setStatus('strict offline mode applied', 'ok');
          return;
        }
        if (id === 'set_deep_trace') {
          if (topKInput) topKInput.value = '8';
          setStatus('Deep Trace engaged (top-k set to 8).', 'ok');
          return;
        }
        if (id === 'expand_ops') {
          setOpsCollapsed(false, true);
          setStatus('ops expanded', 'ok');
          return;
        }
        if (id === 'switch_terminal') {
          setInterfaceMode('terminal', true);
          return;
        }
        if (id === 'fix_all_caps') {
          await runCapabilityFix('fix_all_capabilities', 'Fix All Capabilities', 'all');
          return;
        }
        if (id === 'run_language_catalog_test') {
          await runTerminalPresetById('ccbs_language_catalog_test');
          return;
        }
        if (id === 'repair_cpp') {
          await runCapabilityFix('repair_cpp', 'Repair C++', 'cpp');
          return;
        }
        if (id === 'repair_notebook') {
          await runCapabilityFix('repair_notebook_runtime', 'Repair Notebook Runtime', 'notebook');
          return;
        }
        if (id === 'start_lm_studio') {
          await runCapabilityFix('start_lm_studio', 'Start LM Studio', 'provider');
          return;
        }
        if (id === 'run_notebook_check') {
          await runTerminalPresetById('ccbs_notebook_doctor');
          return;
        }
        if (id === 'run_cpp_smoke') {
          await runTerminalPresetById('ccbs_cpp_compile_smoke');
          return;
        }
        if (id === 'open_profile') {
          if (!terminalProfilesLoaded) await loadTerminalProfiles();
          const profileId = resolveAvailableTerminalProfile(String((action && action.profile_id) || '').trim());
          if (!profileId) {
            setStatus('no terminal profiles available in this workspace', 'error');
            return;
          }
          if (terminalProfileSelect) {
            const exists = Array.from(terminalProfileSelect.options || []).some((opt) => String(opt.value || '') === profileId);
            if (!exists) {
              setStatus(`terminal profile not available: ${profileId}`, 'error');
              return;
            }
            terminalProfileSelect.value = profileId;
          }
          await openTerminalProfile();
          return;
        }
        if (id === 'run_audit') {
          await runTerminalAudit();
          return;
        }
        if (id === 'new_thread') {
          await newThread();
        }
      }

      function renderRoleDetails(roleId) {
        const card = cardByRole(roleId);
        const behavior = (card && card.behavior) ? card.behavior : {};
        const utilityMode = String((card && card.utility_mode) || behavior.utility_mode || roleId || 'core');
        const effectiveRole = String(behavior.effective_role || utilityMode || roleId || 'core');
        const desc = String((card && card.description) || behavior.description || '').trim();
        const constraints = String((card && card.constraint_summary) || '').trim();
        const diff = roleDifferenceText(card);
        const modeText = explainMode(state.offlineMode);
        const behaviorLine = `Effective behavior: ${effectiveRole} · Utility mode: ${utilityMode}`;
        if (cardExplain) {
          cardExplain.textContent = [desc, diff, behaviorLine, constraints ? `Constraints: ${constraints}` : '', modeText].filter(Boolean).join(' ');
        }
        if (!roleQuickActions) return;
        roleQuickActions.innerHTML = '';
        const actions = roleQuickActionsFor(card);
        for (const action of actions) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.textContent = String(action.label || action.id || 'Action');
          if (String(action.id || '') === 'set_strict') btn.className = 'warn';
          else if (String(action.id || '') === 'new_thread') btn.className = 'alt';
          btn.addEventListener('click', () => {
            runRoleAction(action).catch((err) => setStatus(`role action error: ${err.message}`, 'error'));
          });
          roleQuickActions.appendChild(btn);
        }
      }

      async function openTerminalProfile() {
        if (!terminalProfileSelect) return;
        const profileId = String(terminalProfileSelect.value || '').trim();
        if (!profileId) {
          setStatus('select a terminal profile first', 'info');
          return;
        }
        const profileMeta = (state.terminalProfiles || []).find((row) => String(row.profile_id || '') === profileId) || {};
        if (profileMeta.requires_confirmation || profileMeta.requires_network) {
          const ok = await confirmAction({
            title: `Open profile: ${profileMeta.label || profileId}`,
            body: `Command: ${profileMeta.command_preview || profileId}\nMode: ${state.offlineMode}\nProceed?`,
            confirmLabel: 'Open Profile',
          });
          if (!ok) {
            setStatus('open profile cancelled', 'info');
            return;
          }
        }
        if (terminalOpenProfileBtn) terminalOpenProfileBtn.disabled = true;
        try {
          const out = await api('/v3/chat/terminal/open-profile', {
            method: 'POST',
            body: JSON.stringify({ profile_id: profileId, offline_mode: state.offlineMode, confirmed: true }),
          });
          setStatus(`opened terminal profile: ${out.label || profileId}`, 'ok');
          if (terminalOutput) {
            const prev = String(terminalOutput.textContent || '').trim();
            const header = `Opened profile ${out.label || profileId} (pid ${out.pid || 'n/a'})`;
            setTerminalOutputText(prev ? `${header}\n\n${prev}` : header, false);
          }
          await loadApiEvents().catch(() => {});
        } catch (err) {
          setStatus(`open profile error: ${err.message}`, 'error');
        } finally {
          if (terminalOpenProfileBtn) terminalOpenProfileBtn.disabled = false;
        }
      }

      function renderSteps(summary, runStatus = '') {
        const rows = Array.isArray(summary) ? summary : [];
        const lines = [];
        if (runStatus) lines.push(`run status=${runStatus}`);
        if (!rows.length) {
          if (!lines.length) lines.push('No run steps yet.');
          const html = lines.join('<br/>');
          if (steps) steps.innerHTML = html;
          if (drawerSteps) drawerSteps.innerHTML = html;
          return;
        }
        for (const row of rows) {
          const status = String(row.status || 'unknown');
          const type = String(row.step_type || 'step');
          const idx = row.step_index === undefined ? '?' : row.step_index;
          const mark = status === 'completed' ? 'step-ok' : (status === 'requires_action' ? 'step-warn' : 'step-fail');
          lines.push(`${idx}. ${type} :: %${mark}%${status}%`);
        }
        const html = lines
          .map((line) => line.replace(/%(step-[a-z]+)%(.+?)%/g, '<span class="$1">$2</span>'))
          .join('<br/>');
        if (steps) steps.innerHTML = html;
        if (drawerSteps) drawerSteps.innerHTML = html;
      }

      async function api(path, options = {}) {
        const headers = Object.assign({}, options.headers || {}, { 'Content-Type': 'application/json' });
        const token = tokenInput.value.trim();
        if (token) headers['Authorization'] = `Bearer ${token}`;
        let res;
        try {
          res = await fetch(path, Object.assign({}, options, { headers }));
        } catch (err) {
          const msg = String((err && err.message) || err || 'network failure');
          throw new Error(`failed to fetch (${msg}). Check API status, local network loopback, or browser reset.`);
        }
        const text = await res.text();
        let payload = {};
        try { payload = text ? JSON.parse(text) : {}; } catch (_err) { payload = { raw: text }; }
        if (!res.ok) {
          const detail = payload.detail || payload.error || JSON.stringify(payload);
          let hint = '';
          if (res.status === 401) hint = ' Hint: save a bearer token or enable owner auto-auth.';
          else if (res.status === 403) hint = ' Hint: action may be blocked by strict offline policy.';
          else if (res.status >= 500) hint = ' Hint: check the CCBS ai3 API terminal logs.';
          throw new Error(`HTTP ${res.status}: ${detail}${hint}`);
        }
        return payload;
      }

      function selectedModel() {
        const key = modelSelect.value;
        return state.catalog.find((item) => String(item.key) === key) || null;
      }

      function modelAllowedInMode(item) {
        const provider = String((item && item.provider) || '').trim().toLowerCase();
        if (state.offlineMode === 'strict' && (provider === 'openai' || provider === 'codex')) {
          return false;
        }
        return true;
      }

      function renderModelOptions(models) {
        modelSelect.innerHTML = '';
        const rows = (Array.isArray(models) ? models : []).filter((item) => modelAllowedInMode(item));
        for (const item of rows) {
          const opt = document.createElement('option');
          opt.value = item.key;
          const flag = item.reachable ? 'online' : 'offline';
          const src = Array.isArray(item.sources) ? item.sources.join(',') : (item.source || '');
          opt.textContent = `${item.provider} :: ${item.model} (${flag}; ${src})`;
          modelSelect.appendChild(opt);
        }
        if (!models.length) {
          const opt = document.createElement('option');
          opt.value = 'extractive|extractive|';
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

      function renderLanguageDecision(decision) {
        if (!languageDecisionStatus) return;
        if (!decision || typeof decision !== 'object') {
          languageDecisionStatus.textContent = 'No language/model decision yet.';
          return;
        }
        const route = (decision && decision.provider_route) || {};
        const trace = Array.isArray(decision.explanation_trace) ? decision.explanation_trace : [];
        const lines = [];
        lines.push(`Language: ${decision.selected_language || 'Plain text'}`);
        lines.push(`Use case: ${decision.use_case_class || 'simple'}`);
        if (decision.workload_class) lines.push(`Workload: ${decision.workload_class}`);
        lines.push(`Route: ${(route.provider || 'extractive')} :: ${(route.model || 'extractive')}`);
        if (decision.hybrid_mode) lines.push(`Hybrid mode: ${decision.hybrid_mode}`);
        if (decision.scope_recommendation) lines.push(`Scope recommend: ${decision.scope_recommendation}`);
        lines.push(`Confidence: ${typeof decision.confidence === 'number' ? decision.confidence.toFixed(3) : decision.confidence || 'n/a'}`);
        lines.push(`Override: ${decision.override_applied ? 'yes' : 'no'}`);
        if (decision.scope_prompt_required) lines.push('Scope prompt: required');
        if (decision.active_storage_mode) lines.push(`Storage: ${decision.active_storage_mode}`);
        const ranking = Array.isArray(decision.language_rankings) ? decision.language_rankings : [];
        if (ranking.length) {
          const top = ranking.slice(0, 3).map((row) => String((row && row.language) || '')).filter(Boolean);
          if (top.length) lines.push(`Top languages: ${top.join(', ')}`);
        }
        if (trace.length) {
          lines.push('');
          lines.push(`Trace: ${trace[0]}`);
        }
        languageDecisionStatus.textContent = lines.join('\\n');
      }

      function applyScopeGuidanceFromDecision(decision, promptUser = true) {
        const row = decision && typeof decision === 'object' ? decision : {};
        const recommended = normalizeAnswerScope(row.scope_recommendation || state.answerScope, state.answerScope || 'repo_grounded');
        if (recommended && recommended !== state.answerScope) {
          setScope(recommended, false);
        }
        const needsPrompt = !!row.scope_prompt_required && !state.scopeConfirmed;
        if (needsPrompt && promptUser) {
          const reason = String(row.scope_reason || 'Scope confirmation required for this task.').trim();
          openNeonCompass(true);
          setStatus(`Scope check: ${scopeLabel(recommended)} recommended. ${reason} Confirm scope before send.`, 'info');
        }
        return needsPrompt;
      }

      function ensureModelOption(route) {
        if (!modelSelect || !route || typeof route !== 'object') return;
        const key = String(route.model_key || '').trim();
        const provider = String(route.provider || '').trim().toLowerCase();
        const model = String(route.model || '').trim();
        const base = String(route.base_url || '').trim();
        if (!key || !provider || !model) return;
        const exists = Array.from(modelSelect.options || []).some((opt) => String(opt.value || '') === key);
        if (exists) return;
        const opt = document.createElement('option');
        opt.value = key;
        opt.textContent = `${provider} :: ${model} (decision route)`;
        modelSelect.appendChild(opt);
      }

      async function loadLanguageCatalog(refresh = false) {
        const storageMode = normalizeLanguageStorageMode(languageStorageModeSelect ? languageStorageModeSelect.value : state.languageStorageMode, state.languageStorageMode || 'auto');
        const includeExternal = !!(languageExternalToggle && languageExternalToggle.checked);
        const params = new URLSearchParams();
        params.set('storage_mode', storageMode);
        params.set('include_external', includeExternal ? 'true' : 'false');
        if (refresh) params.set('refresh', 'true');
        const out = await api(`/v3/chat/language-catalog?${params.toString()}`);
        state.languageCatalog = Array.isArray(out.languages) ? out.languages : [];
        state.languageStorageMode = String(out.active_storage_mode || storageMode || 'auto');
        const modeLabel = `${state.languageCatalog.length} languages (${state.languageStorageMode})`;
        if (languageCatalogCount) {
          languageCatalogCount.textContent = `Catalog Count: ${modeLabel}`;
        }
        if (languageDecisionStatus && !state.languageDecision) {
          languageDecisionStatus.textContent = `Catalog ready: ${modeLabel}`;
        } else if (state.languageDecision) {
          renderLanguageDecision(state.languageDecision);
        }
      }

      async function requestLanguageDecision(message, openModal = false) {
        const text = String(message || '').trim();
        if (!text) throw new Error('message is required');
        const languageMode = normalizeLanguageMode(languageModeSelect ? languageModeSelect.value : state.languageMode, state.languageMode || 'auto');
        const manualLanguage = String(manualLanguageInput ? manualLanguageInput.value : state.manualLanguage || '').trim();
        const storageMode = normalizeLanguageStorageMode(languageStorageModeSelect ? languageStorageModeSelect.value : state.languageStorageMode, state.languageStorageMode || 'auto');
        const includeExternal = !!(languageExternalToggle && languageExternalToggle.checked);
        const out = await api('/v3/chat/language-decision', {
          method: 'POST',
          body: JSON.stringify({
            message: text,
            offline_mode: state.offlineMode,
            answer_scope: state.answerScope,
            language_mode: languageMode,
            manual_language: manualLanguage,
            language_storage_mode: storageMode,
            language_external_enrichment: includeExternal,
            metadata: {
              active_role: state.activeRole,
              ui_surface: state.surface,
            },
          }),
        });
        const decision = (out && out.decision) ? out.decision : {};
        state.languageDecision = decision;
        state.languageMode = languageMode;
        state.manualLanguage = manualLanguage;
        state.languageStorageMode = storageMode;
        state.languageExternalEnrichment = includeExternal;
        renderLanguageDecision(decision);
        applyScopeGuidanceFromDecision(decision, false);
        const route = (decision && decision.provider_route) || {};
        ensureModelOption(route);
        if (route && route.model_key) {
          const exists = Array.from(modelSelect.options || []).some((opt) => String(opt.value || '') === String(route.model_key || ''));
          if (exists) modelSelect.value = String(route.model_key || '');
        }
        if (openModal) {
          await showLanguageDecisionModal(decision);
        }
        return decision;
      }

      async function showLanguageDecisionModal(decision) {
        const row = decision || state.languageDecision || {};
        if (!languageDecisionModal || typeof languageDecisionModal.showModal !== 'function') {
          return;
        }
        const route = (row && row.provider_route) || {};
        const topLanguages = collectTopLanguages(row, 4);
        if (languageDecisionSummary) {
          const summary = [
            `Language: ${row.selected_language || 'Plain text'}`,
            `Use case: ${row.use_case_class || 'simple'}`,
            `Workload: ${row.workload_class || 'general'}`,
            `Scope: ${scopeLabel(row.scope_recommendation || state.answerScope || 'repo_grounded')}`,
            `Route: ${(route.provider || 'extractive')} :: ${(route.model || 'extractive')}`,
            `Confidence: ${formatDecisionConfidence(row.confidence)}`,
          ];
          languageDecisionSummary.textContent = summary.join('\\n');
        }
        if (languageDecisionTrace) {
          const trace = Array.isArray(row.explanation_trace) ? row.explanation_trace : [];
          languageDecisionTrace.textContent = trace.length ? trace.join('\\n') : 'No trace available.';
        }
        if (modalSelectedLanguage) modalSelectedLanguage.value = String(row.selected_language || manualLanguageInput.value || '');
        if (modalSelectedRoute) modalSelectedRoute.value = `${route.provider || 'extractive'} :: ${route.model || 'extractive'}`;
        if (modalLanguageMode) modalLanguageMode.value = normalizeLanguageMode(languageModeSelect ? languageModeSelect.value : state.languageMode, state.languageMode || 'auto');
        if (modalScopeRecommendation) modalScopeRecommendation.value = scopeLabel(row.scope_recommendation || state.answerScope || 'repo_grounded');
        if (modalTopLanguages) modalTopLanguages.value = topLanguages.length ? topLanguages.join(', ') : 'n/a';
        if (modalDecisionConfidence) modalDecisionConfidence.value = formatDecisionConfidence(row.confidence);
        if (modalHybridMode) modalHybridMode.value = String(row.hybrid_mode || 'local_only');

        await new Promise((resolve) => {
          const done = () => {
            languageDecisionModal.removeEventListener('close', done);
            const action = String(languageDecisionModal.returnValue || '');
            if (action === 'apply') {
              if (modalLanguageMode && languageModeSelect) {
                languageModeSelect.value = normalizeLanguageMode(modalLanguageMode.value, state.languageMode || 'auto');
                state.languageMode = languageModeSelect.value;
              }
              if (modalSelectedLanguage && manualLanguageInput) {
                manualLanguageInput.value = String(modalSelectedLanguage.value || '').trim();
                state.manualLanguage = manualLanguageInput.value;
              }
              if (manualLanguageInput && state.languageMode === 'manual' && !manualLanguageInput.value.trim()) {
                manualLanguageInput.value = String(row.selected_language || '').trim();
              }
              saveProfile().catch((err) => setStatus(`profile warning: ${err.message}`, 'error'));
            }
            resolve(null);
          };
          languageDecisionModal.addEventListener('close', done);
          languageDecisionModal.showModal();
        });
      }

      function roleBehavior(roleId) {
        const row = state.cards.find((item) => String(item.role_id) === String(roleId));
        return (row && row.behavior) ? row.behavior : {
          ui_mode: 'balanced',
          role_hint: 'Balanced assistant mode.',
          description: 'General purpose lane for everyday Q/A and execution.',
          enforce_offline_only: null,
          enforce_allow_remote: null,
          top_k: 5,
          top_k_min: 5,
          ops_hint: 'balanced',
          effective_role: String(roleId || 'core'),
          utility_mode: String(roleId || 'core'),
        };
      }

      async function syncRoleSelection(roleId) {
        const out = await api('/v3/chat/role-select', {
          method: 'POST',
          body: JSON.stringify({
            role_id: String(roleId || ''),
            model_key: modelSelect ? String(modelSelect.value || '') : '',
          }),
        });
        if (out && typeof out.xp !== 'undefined') {
          setStatus(`role XP updated: ${out.role_id} -> ${out.xp} (${out.stage || 'base'})`, 'ok');
        }
      }

      function applyRole(roleId, announce = true, reward = false) {
        state.activeRole = String(roleId || 'core');
        for (const btn of roleDeck.querySelectorAll('.role-card')) {
          btn.setAttribute('aria-pressed', String(btn.dataset.roleId === state.activeRole));
        }
        setHackerInterfaceVisible(state.activeRole === 'hacker');
        const behavior = roleBehavior(state.activeRole);
        if (roleHintInput && !roleHintInput.value.trim()) roleHintInput.value = String(behavior.role_hint || '');

        if (behavior.enforce_offline_only === true) applyOfflineMode('strict', true);
        if (behavior.enforce_offline_only !== true && state.offlineMode === 'strict') {
          applyOfflineMode(state.offlineMode, false);
        }
        if (behavior.enforce_allow_remote === false) allowRemote.checked = false;

        const topKMin = Number(behavior.top_k_min || 0);
        if (topKMin > 0 && Number(topKInput.value || 0) < topKMin) {
          topKInput.value = String(topKMin);
        }
        if (String(behavior.ops_hint || '') === 'expand') setOpsCollapsed(false);
        if (state.activeRole === 'ranger') {
          openNeonCompass(true);
          state.scopeConfirmed = false;
          renderScopeStatus();
        }
        renderRoleDetails(state.activeRole);
        syncTaskWindowDefaults();
        syncDeckPopout();
        syncChatPopoutFeed();

        if (announce) setStatus(`role set: ${state.activeRole}`, 'ok');
        if (reward) {
          syncRoleSelection(state.activeRole).catch(() => {
            // non-blocking
          });
        }
      }

      function cardVariantOptions(card) {
        const options = Array.isArray(card && card.variant_options) ? card.variant_options : [];
        const filtered = options.filter((row) => row && typeof row === 'object');
        if (filtered.length) return filtered;
        return [{
          variant_id: String(card && card.variant_id ? card.variant_id : 'v1'),
          image_url: String(card && card.image_url ? card.image_url : ''),
          image_inline_url: String(card && card.image_inline_url ? card.image_inline_url : ''),
          image_fallback_url: String(card && card.image_fallback_url ? card.image_fallback_url : ''),
          frame_style: String(card && card.frame_style ? card.frame_style : 'neon'),
          accent_palette: (card && card.accent_palette) ? card.accent_palette : {},
        }];
      }

      function applyCardVariant(btn, card, index, announce = false) {
        const options = cardVariantOptions(card);
        if (!options.length) return;
        const idx = ((Number(index || 0) % options.length) + options.length) % options.length;
        const option = options[idx] || {};
        state.roleVariantIndex[String(card.role_id || '')] = idx;

        const inline = String(option.image_inline_url || card.image_inline_url || '').trim();
        const primary = String(inline || option.image_url || card.image_url || '').trim();
        const fallback = String(option.image_fallback_url || card.image_fallback_url || '').trim();
        const artPrimary = btn.querySelector('.role-art.primary');
        const artFallback = btn.querySelector('.role-art.fallback');
        let value = 'none';
        if (primary && fallback && primary !== fallback) value = `url('${primary}'), url('${fallback}')`;
        else if (primary) value = `url('${primary}')`;
        else if (fallback) value = `url('${fallback}')`;
        btn.style.setProperty('--card-image', value);
        btn.classList.toggle('has-image', value !== 'none');

        if (artFallback) {
          if (fallback) {
            artFallback.src = fallback;
            artFallback.style.display = primary ? 'none' : 'block';
          } else {
            artFallback.removeAttribute('src');
            artFallback.style.display = 'none';
          }
        }

        if (artPrimary) {
          if (primary) {
            artPrimary.src = primary;
            artPrimary.style.display = 'block';
          } else {
            artPrimary.removeAttribute('src');
            artPrimary.style.display = 'none';
          }
          artPrimary.onerror = () => {
            artPrimary.style.display = 'none';
            if (artFallback && fallback) {
              artFallback.src = fallback;
              artFallback.style.display = 'block';
            }
          };
        }

        const accent = (option.accent_palette && option.accent_palette.border)
          ? option.accent_palette.border
          : ((card.accent_palette && card.accent_palette.border) ? card.accent_palette.border : '');
        if (accent) btn.style.setProperty('--role-accent', accent);

        btn.dataset.variantIndex = String(idx);
        btn.dataset.variantId = String(option.variant_id || card.variant_id || 'v1');
        if (announce) {
          const name = String(card.label || card.role_id || 'role');
          setStatus(`variant cycled: ${name} (${idx + 1}/${options.length})`, 'ok');
        }
        renderSmylesStrip(state.cards || []);
      }

      function primaryCardImage(card) {
        const options = cardVariantOptions(card);
        const idx = Number(state.roleVariantIndex[String(card.role_id || '')] || 0);
        const option = options[((idx % options.length) + options.length) % options.length] || {};
        const inline = String(option.image_inline_url || card.image_inline_url || '').trim();
        const primary = String(inline || option.image_url || card.image_url || '').trim();
        const fallback = String(option.image_fallback_url || card.image_fallback_url || '').trim();
        return primary || fallback;
      }

      function renderSmylesStrip(cards) {
        if (!smylesStrip) return;
        const rows = Array.isArray(cards) ? cards : [];
        if (!rows.length) {
          smylesStrip.innerHTML = '<div class="small">No Smyles visuals available.</div>';
          return;
        }
        smylesStrip.innerHTML = '';
        for (const card of rows.slice(0, 6)) {
          const tile = document.createElement('div');
          tile.className = 'smyle-tile';
          const img = document.createElement('img');
          const src = primaryCardImage(card);
          if (src) {
            img.src = src;
          } else {
            img.src = '/assets/ai3/cards/core/core_a.svg';
          }
          img.alt = `${String(card.label || card.role_id || 'Role')} visual`;
          img.loading = 'lazy';
          img.decoding = 'async';
          tile.appendChild(img);
          const caption = document.createElement('div');
          caption.className = 'caption';
          caption.textContent = String(card.label || card.role_id || 'Role');
          tile.appendChild(caption);
          smylesStrip.appendChild(tile);
        }
      }

      function renderRoleDeck(cards, activeRole) {
        roleDeck.innerHTML = '';
        for (const card of cards) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = `role-card${card.is_core ? ' core' : ''}`;
          btn.dataset.roleId = String(card.role_id || '');
          btn.setAttribute('aria-pressed', String(card.role_id === activeRole));
          btn.setAttribute('aria-label', `${card.label || card.role_id} role button`);

          const options = cardVariantOptions(card);
          const accent = (card.accent_palette && card.accent_palette.border) ? card.accent_palette.border : '';
          if (accent) btn.style.setProperty('--role-accent', accent);

          const jitterX = boundedFloat(`${loadSeed}:${card.role_id}:x`, -4, 4).toFixed(2);
          const jitterY = boundedFloat(`${loadSeed}:${card.role_id}:y`, -4, 4).toFixed(2);
          const tilt = boundedFloat(`${loadSeed}:${card.role_id}:tilt`, -1.5, 1.5).toFixed(2);
          const pulse = boundedFloat(`${loadSeed}:${card.role_id}:pulse`, 2, 16).toFixed(2);
          btn.style.setProperty('--jitter-x', `${jitterX}px`);
          btn.style.setProperty('--jitter-y', `${jitterY}px`);
          btn.style.setProperty('--tilt', `${tilt}deg`);
          btn.style.setProperty('--pulse', `${pulse}px`);

          const artPrimary = document.createElement('img');
          artPrimary.className = 'role-art primary';
          artPrimary.alt = '';
          artPrimary.setAttribute('aria-hidden', 'true');
          btn.appendChild(artPrimary);

          const artFallback = document.createElement('img');
          artFallback.className = 'role-art fallback';
          artFallback.alt = '';
          artFallback.setAttribute('aria-hidden', 'true');
          btn.appendChild(artFallback);

          const seededIndex = boundedInt(`${loadSeed}:${card.role_id}:variant`, options.length);
          applyCardVariant(btn, card, seededIndex, false);

          const icon = document.createElement('div');
          icon.className = 'icon-chip';
          icon.textContent = card.icon || '◎';
          btn.appendChild(icon);

          const name = document.createElement('div');
          name.className = 'role-name';
          name.textContent = card.label || card.role_id;
          btn.appendChild(name);

          const mode = document.createElement('div');
          mode.className = 'role-mode';
          const evo = (card && card.evolution) ? card.evolution : {};
          const xp = Number(evo.xp || 0);
          const stage = String(evo.stage_label || evo.stage || '');
          const utilityMode = String(card.utility_mode || card.role_id || '').replace(/_/g, ' ');
          const effectiveMode = String((card.behavior && card.behavior.effective_role) || card.utility_mode || card.role_id || '').replace(/_/g, ' ');
          const behaviorText = `${utilityMode} -> ${effectiveMode}`;
          mode.textContent = stage ? `${behaviorText} · XP ${xp} · ${stage}` : behaviorText;
          btn.appendChild(mode);

          const desc = document.createElement('div');
          desc.className = 'role-desc';
          const behavior = card.behavior || {};
          desc.textContent = String(card.description || behavior.description || behavior.role_hint || '').trim();
          if (desc.textContent) btn.appendChild(desc);

          const constraints = String(card.constraint_summary || '').trim();
          if (constraints || desc.textContent) {
            btn.title = [desc.textContent, constraints].filter(Boolean).join(' | ');
          }

          btn.addEventListener('click', () => {
            const sameRole = String(state.activeRole || '') === String(card.role_id || '');
            if (sameRole && options.length > 1) {
              const current = Number(btn.dataset.variantIndex || 0);
              applyCardVariant(btn, card, current + 1, true);
              applyRole(card.role_id, false, true);
              return;
            }
            applyRole(card.role_id, true, true);
          });
          roleDeck.appendChild(btn);
        }
        syncDeckPopout();
      }

      async function loadCards() {
        const params = new URLSearchParams();
        if (state.threadId) params.set('thread_id', state.threadId);
        params.set('surface', state.surface);
        const out = await api(`/v3/chat/cards?${params.toString()}`);
        state.cards = out.cards || [];
        const preferred = String(out.active_role || state.activeRole || 'core');
        renderRoleDeck(state.cards, preferred);
        renderSmylesStrip(state.cards);
        applyRole(preferred, false, false);
        if (cardPack && out.pack && out.pack.pack_id) cardPack.value = out.pack.pack_id;
      }

      async function refreshSmilesDeck() {
        loadSeed = createLoadSeed();
        await loadCards();
        setStatus('Smyles visuals refreshed.', 'ok');
      }

      async function browserReset() {
        try {
          if ('caches' in globalThis && caches && typeof caches.keys === 'function') {
            const keys = await caches.keys();
            await Promise.all(keys.map((key) => caches.delete(key)));
          }
        } catch (_err) {
          // ignore cache clear failures
        }
        const url = new URL(window.location.href);
        url.searchParams.set('reset', String(Date.now()));
        window.location.replace(url.toString());
      }

      async function loadProfile() {
        const out = await api('/v3/chat/profile');
        const p = out.profile || {};
        displayName.value = p.display_name || 'Owner';
        avatarStyle.value = p.avatar_style || 'nft-core';
        themeSelect.value = p.theme || 'neon-deck';
        tonePreset.value = p.tone_preset || 'balanced';
        state.languageMode = normalizeLanguageMode(p.language_mode || 'auto', 'auto');
        state.manualLanguage = String(p.manual_language || '').trim();
        state.languageStorageMode = normalizeLanguageStorageMode(p.language_storage_mode || 'auto', 'auto');
        state.languageExternalEnrichment = asBool(p.language_external_enrichment, false);
        if (languageModeSelect) languageModeSelect.value = state.languageMode;
        if (manualLanguageInput) manualLanguageInput.value = state.manualLanguage;
        if (languageStorageModeSelect) languageStorageModeSelect.value = state.languageStorageMode;
        if (languageExternalToggle) languageExternalToggle.checked = !!state.languageExternalEnrichment;
        if (cardPack && p.card_pack) cardPack.value = p.card_pack;
        state.activeRole = p.active_role || 'core';
        state.opsCollapsed = asBool(p.ops_collapsed, true);
        state.offlineMode = normalizeOfflineMode(p.offline_mode || 'guided', 'guided');
        state.scopePromptMode = normalizeScopePromptMode(p.scope_prompt_mode || 'always', 'always');
        state.answerScope = normalizeAnswerScope(p.default_answer_scope || 'repo_grounded', 'repo_grounded');
        state.liveOutputMode = normalizeLiveOutputMode(p.live_output_mode || 'collapsed', 'collapsed');
        applyOfflineMode(state.offlineMode, true);
        setScope(state.answerScope, false);
        if (scopePromptModeSelect) scopePromptModeSelect.value = state.scopePromptMode;
        renderModelOptions(state.catalog || []);
        if (p.preferred_model) {
          const exists = Array.from(modelSelect.options || []).some((opt) => String(opt.value || '') === String(p.preferred_model));
          if (exists) modelSelect.value = p.preferred_model;
        }
        applyTheme(themeSelect.value);
        setOpsCollapsed(state.opsCollapsed, false);
        setLiveOutputMode(state.liveOutputMode, false);
      }

      async function saveProfile() {
        const body = {
          display_name: displayName.value.trim(),
          avatar_style: avatarStyle.value,
          theme: themeSelect.value,
          preferred_model: modelSelect.value,
          language_mode: normalizeLanguageMode(languageModeSelect ? languageModeSelect.value : state.languageMode, 'auto'),
          manual_language: String(manualLanguageInput ? manualLanguageInput.value : state.manualLanguage || '').trim(),
          language_storage_mode: normalizeLanguageStorageMode(languageStorageModeSelect ? languageStorageModeSelect.value : state.languageStorageMode, 'auto'),
          language_external_enrichment: !!(languageExternalToggle && languageExternalToggle.checked),
          tone_preset: tonePreset.value,
          active_role: state.activeRole,
          card_pack: cardPack ? cardPack.value.trim() : '',
          ops_collapsed: !!state.opsCollapsed,
          offline_mode: normalizeOfflineMode(offlineModeSelect ? offlineModeSelect.value : state.offlineMode, 'guided'),
          scope_prompt_mode: normalizeScopePromptMode(scopePromptModeSelect ? scopePromptModeSelect.value : state.scopePromptMode, 'always'),
          default_answer_scope: normalizeAnswerScope(answerScopeSelect ? answerScopeSelect.value : state.answerScope, 'repo_grounded'),
          live_output_mode: normalizeLiveOutputMode(state.liveOutputMode || 'collapsed', 'collapsed'),
        };
        const out = await api('/v3/chat/profile', { method: 'POST', body: JSON.stringify(body) });
        const p = out.profile || {};
        state.languageMode = normalizeLanguageMode(p.language_mode || body.language_mode || state.languageMode, 'auto');
        state.manualLanguage = String(p.manual_language || body.manual_language || state.manualLanguage || '').trim();
        state.languageStorageMode = normalizeLanguageStorageMode(p.language_storage_mode || body.language_storage_mode || state.languageStorageMode, 'auto');
        state.languageExternalEnrichment = asBool(p.language_external_enrichment, body.language_external_enrichment);
        state.offlineMode = normalizeOfflineMode(p.offline_mode || body.offline_mode || state.offlineMode, 'guided');
        state.scopePromptMode = normalizeScopePromptMode(p.scope_prompt_mode || body.scope_prompt_mode || state.scopePromptMode, 'always');
        state.answerScope = normalizeAnswerScope(p.default_answer_scope || body.default_answer_scope || state.answerScope, 'repo_grounded');
        state.liveOutputMode = normalizeLiveOutputMode(p.live_output_mode || body.live_output_mode || state.liveOutputMode, 'collapsed');
        if (languageModeSelect) languageModeSelect.value = state.languageMode;
        if (manualLanguageInput) manualLanguageInput.value = state.manualLanguage;
        if (languageStorageModeSelect) languageStorageModeSelect.value = state.languageStorageMode;
        if (languageExternalToggle) languageExternalToggle.checked = !!state.languageExternalEnrichment;
        applyOfflineMode(state.offlineMode, false);
        setScope(state.answerScope, state.scopeConfirmed);
        if (scopePromptModeSelect) scopePromptModeSelect.value = state.scopePromptMode;
        setLiveOutputMode(state.liveOutputMode, false);
        applyTheme(p.theme || themeSelect.value);
        setStatus('profile saved', 'ok');
      }

      async function loadHistory() {
        if (!state.threadId) return;
        try {
          const out = await api(`/v3/chat/history/${encodeURIComponent(state.threadId)}`);
          clearFeed();
          const rows = Array.isArray(out.messages) ? out.messages : [];
          for (const msg of rows) {
            const role = String(msg.role || '') === 'assistant' ? 'assistant' : (String(msg.role || '') === 'user' ? 'user' : 'assistant');
            pushMessage(role, String(msg.content || ''));
          }
        } catch (err) {
          if (String(err.message || '').toLowerCase().includes('thread not found')) {
            updateThread('');
            setStatus('previous thread expired; started fresh session', 'info');
            return;
          }
          throw err;
        }
      }

      function updateThread(threadId) {
        state.threadId = String(threadId || '').trim();
        localStorage.setItem(threadStoreKey, state.threadId);
        if (threadInput) threadInput.value = state.threadId;
        if (threadInfo) threadInfo.textContent = `Thread: ${state.threadId || 'auto'}`;
      }

      async function sendPrompt() {
        const text = promptInput.value.trim();
        if (!text) return;
        const currentScopePromptMode = normalizeScopePromptMode(scopePromptModeSelect ? scopePromptModeSelect.value : state.scopePromptMode, state.scopePromptMode || 'always');
        const currentScope = normalizeAnswerScope(answerScopeSelect ? answerScopeSelect.value : state.answerScope, state.answerScope || 'repo_grounded');
        if (state.activeRole === 'ranger' && !state.scopeConfirmed) {
          openNeonCompass(true);
          setStatus('Ranger lane requires Neon Compass scope confirmation before send.', 'error');
          return;
        }
        if (state.offlineMode === 'strict' && currentScope === 'remote_allowed') {
          setStatus('Strict mode blocks Remote Allowed scope. Pick Repo Grounded or General Local.', 'error');
          return;
        }
        if (currentScope === 'remote_allowed' && !remoteFoundryGateOpen()) {
          setStatus(remoteFoundryGateReason(), 'error');
          return;
        }

        sendBtn.disabled = true;
        setStatus('running...', 'info');

        try {
          let decisionPayload = state.languageDecision;
          try {
            decisionPayload = await requestLanguageDecision(text, false);
          } catch (decisionErr) {
            setStatus(`language decision warning: ${decisionErr.message}`, 'info');
          }
          if (applyScopeGuidanceFromDecision(decisionPayload, true)) {
            return;
          }

          const model = selectedModel();
          const behavior = roleBehavior(state.activeRole);
          let forcedOffline = behavior.enforce_offline_only === true ? true : !!offlineOnly.checked;
          let forcedRemote = behavior.enforce_allow_remote === false ? false : !!allowRemote.checked;
          if (state.offlineMode === 'strict') {
            forcedOffline = true;
            forcedRemote = false;
          }
          const topK = Math.max(1, Number(topKInput.value || behavior.top_k || 5));
          pushMessage('user', text);

          const out = await api('/v3/chat/send', {
            method: 'POST',
            body: JSON.stringify({
              thread_id: state.threadId || '',
              message: text,
              model_key: model ? model.key : '',
              provider: model ? model.provider : '',
              model: model ? model.model : '',
              base_url: model ? model.base_url : '',
              offline_mode: state.offlineMode,
              offline_only: forcedOffline,
              allow_remote: forcedRemote,
              top_k: topK,
              active_role: state.activeRole,
              role_hint: roleHintInput.value.trim(),
              ui_surface: state.surface,
              answer_scope: currentScope,
              scope_confirmed: !!state.scopeConfirmed,
              language_mode: normalizeLanguageMode(languageModeSelect ? languageModeSelect.value : state.languageMode, state.languageMode || 'auto'),
              manual_language: String(manualLanguageInput ? manualLanguageInput.value : state.manualLanguage || '').trim(),
              language_storage_mode: normalizeLanguageStorageMode(languageStorageModeSelect ? languageStorageModeSelect.value : state.languageStorageMode, state.languageStorageMode || 'auto'),
              language_external_enrichment: !!(languageExternalToggle && languageExternalToggle.checked),
              decision_payload: decisionPayload || {},
            }),
          });

          if (out.thread_id) {
            const changed = state.threadId !== out.thread_id;
            updateThread(out.thread_id);
            if (changed) {
              await loadCards();
            }
          }

          const answer = (out.assistant_message && out.assistant_message.content) || out.answer || '';
          if (answer) pushMessage('assistant', answer);
          if (out.language_decision) {
            state.languageDecision = out.language_decision;
            renderLanguageDecision(state.languageDecision);
          }

          state.pendingApprovals = Array.isArray(out.requires_action) ? out.requires_action : [];
          renderSteps(out.step_summary || [], out.run_status || '');
          if (String(out.ops_hint || '') === 'expand') setOpsCollapsed(false, false);
          if (out.role_applied) applyRole(out.role_applied, false, false);
          if (typeof out.scope_confirmed !== 'undefined') {
            state.scopeConfirmed = !!out.scope_confirmed;
          }
          if (out.answer_scope) {
            setScope(out.answer_scope, !!out.scope_confirmed);
          }
          if (currentScopePromptMode === 'always') {
            state.scopeConfirmed = false;
            renderScopeStatus();
          }
          if (typeof out.role_xp_total !== 'undefined') {
            await loadCards();
          }
          await loadApiEvents().catch(() => {});

          const xpNote = (typeof out.role_xp_gain !== 'undefined' && typeof out.role_xp_total !== 'undefined')
            ? ` · XP +${out.role_xp_gain} (total ${out.role_xp_total})`
            : '';
          const conf = out.confidence && out.confidence.label ? ` · confidence ${out.confidence.label}` : '';
          const prov = out.provenance && typeof out.provenance.citation_count !== 'undefined'
            ? ` · citations ${out.provenance.citation_count}`
            : '';
          const langDecision = out.language_decision || decisionPayload || {};
          const langNote = langDecision && langDecision.selected_language ? ` · language ${langDecision.selected_language}` : '';
          setStatus(`run ${out.run_status || 'completed'} via ${out.provider_used || 'local'}${langNote}${xpNote}${conf}${prov}`, 'ok');
          promptInput.value = '';
        } catch (err) {
          setStatus(`error: ${err.message}`, 'error');
        } finally {
          sendBtn.disabled = false;
          syncChatPopoutFeed();
        }
      }

      async function approvePending() {
        const rows = Array.isArray(state.pendingApprovals) ? state.pendingApprovals : [];
        if (!rows.length) {
          setStatus('no pending approvals', 'info');
          return;
        }
        let approved = 0;
        try {
          for (const row of rows) {
            const id = String(row.tool_call_id || '').trim();
            if (!id) continue;
            const out = await api(`/v3/tool-calls/${encodeURIComponent(id)}/approvals`, {
              method: 'POST',
              body: JSON.stringify({ decision: 'approved', resume: true, allow_remote: state.offlineMode === 'strict' ? false : !!allowRemote.checked }),
            });
            approved += 1;
            if (Array.isArray(out.steps)) {
              const mapped = out.steps.map((s) => ({ step_index: s.step_index, step_type: s.step_type, status: s.status }));
              const runStatus = out.run && out.run.status ? out.run.status : '';
              renderSteps(mapped, runStatus);
            }
          }
          state.pendingApprovals = [];
          setStatus(`approved ${approved} tool calls`, 'ok');
        } catch (err) {
          setStatus(`approval error: ${err.message}`, 'error');
        }
      }

      async function newThread() {
        updateThread('');
        clearFeed();
        state.pendingApprovals = [];
        renderSteps([], '');
        setStatus('new thread session ready', 'ok');
        await loadCards();
      }

      async function useBearerIdentityProfile() {
        await loadIdentity();
        const username = String((state.me && state.me.username) || '').trim();
        if (username && (!displayName.value || displayName.value.trim().toLowerCase() === 'owner')) {
          displayName.value = username;
        }
        await saveProfile();
        await Promise.all([loadCards(), loadOfflineCapabilities()]);
        setStatus(`profile scoped to ${username || 'current identity'}`, 'ok');
      }

      document.getElementById('saveToken').addEventListener('click', () => {
        localStorage.setItem('ccbs_ai3_token', tokenInput.value.trim());
        setStatus('token saved', 'ok');
      });
      if (useBearerProfileBtn) {
        useBearerProfileBtn.addEventListener('click', () => {
          useBearerIdentityProfile().catch((err) => setStatus(`identity error: ${err.message}`, 'error'));
        });
      }
      if (refreshLanguageCatalogBtn) {
        refreshLanguageCatalogBtn.addEventListener('click', () => {
          loadLanguageCatalog(true)
            .then(() => setStatus('language catalog refreshed', 'ok'))
            .catch((err) => setStatus(`language catalog error: ${err.message}`, 'error'));
        });
      }
      if (openLanguageDecisionBtn) {
        openLanguageDecisionBtn.addEventListener('click', () => {
          const text = String(promptInput.value || '').trim();
          if (!text) {
            setStatus('enter a prompt first to compute language/model decision', 'info');
            return;
          }
          requestLanguageDecision(text, true).catch((err) => setStatus(`language decision error: ${err.message}`, 'error'));
        });
      }
      if (copyDecisionTraceBtn) {
        copyDecisionTraceBtn.addEventListener('click', () => {
          const summary = String(languageDecisionSummary ? languageDecisionSummary.textContent || '' : '').trim();
          const trace = String(languageDecisionTrace ? languageDecisionTrace.textContent || '' : '').trim();
          const payload = [summary, trace].filter(Boolean).join('\\n\\n');
          if (!payload) {
            setStatus('no language decision trace to copy yet', 'info');
            return;
          }
          copyTextToClipboard(payload)
            .then((ok) => {
              if (ok) setStatus('language decision copied to clipboard', 'ok');
              else setStatus('clipboard copy unavailable in this browser', 'error');
            })
            .catch((err) => setStatus(`clipboard error: ${err.message}`, 'error'));
        });
      }
      if (languageModeSelect) {
        languageModeSelect.addEventListener('change', () => {
          state.languageMode = normalizeLanguageMode(languageModeSelect.value, state.languageMode || 'auto');
          saveProfile().catch((err) => setStatus(`language mode error: ${err.message}`, 'error'));
        });
      }
      if (manualLanguageInput) {
        manualLanguageInput.addEventListener('change', () => {
          state.manualLanguage = String(manualLanguageInput.value || '').trim();
          saveProfile().catch((err) => setStatus(`manual language error: ${err.message}`, 'error'));
        });
      }
      if (languageStorageModeSelect) {
        languageStorageModeSelect.addEventListener('change', () => {
          state.languageStorageMode = normalizeLanguageStorageMode(languageStorageModeSelect.value, state.languageStorageMode || 'auto');
          Promise.all([saveProfile(), loadLanguageCatalog(false)])
            .catch((err) => setStatus(`language storage mode error: ${err.message}`, 'error'));
        });
      }
      if (languageExternalToggle) {
        languageExternalToggle.addEventListener('change', () => {
          state.languageExternalEnrichment = !!languageExternalToggle.checked;
          Promise.all([saveProfile(), loadLanguageCatalog(false)])
            .catch((err) => setStatus(`language enrichment error: ${err.message}`, 'error'));
        });
      }
      document.getElementById('saveProfile').addEventListener('click', () => saveProfile().catch((err) => setStatus(`error: ${err.message}`, 'error')));
      document.getElementById('send').addEventListener('click', () => sendPrompt());
      document.getElementById('newThread').addEventListener('click', () => newThread().catch((err) => setStatus(`error: ${err.message}`, 'error')));
      document.getElementById('approvePending').addEventListener('click', () => approvePending());
      if (smilesRefreshBtn) {
        smilesRefreshBtn.addEventListener('click', () => {
          refreshSmilesDeck().catch((err) => setStatus(`error: ${err.message}`, 'error'));
        });
      }
      if (smilesRefreshTopBtn) {
        smilesRefreshTopBtn.addEventListener('click', () => {
          refreshSmilesDeck().catch((err) => setStatus(`error: ${err.message}`, 'error'));
        });
      }
      if (browserResetBtn) {
        browserResetBtn.addEventListener('click', () => {
          browserReset().catch((err) => setStatus(`error: ${err.message}`, 'error'));
        });
      }
      if (browserResetTopBtn) {
        browserResetTopBtn.addEventListener('click', () => {
          browserReset().catch((err) => setStatus(`error: ${err.message}`, 'error'));
        });
      }
      if (openSmileEditorBtn) {
        openSmileEditorBtn.addEventListener('click', () => {
          window.location.href = '/admin/smiles/ui';
        });
      }
      if (modeAskBtn) modeAskBtn.addEventListener('click', () => setInterfaceMode('ask', true));
      if (modeTerminalBtn) modeTerminalBtn.addEventListener('click', () => setInterfaceMode('terminal', true));
      if (terminalRunBtn) {
        terminalRunBtn.addEventListener('click', () => {
          runTerminalPreset().catch((err) => setStatus(`terminal run error: ${err.message}`, 'error'));
        });
      }
      if (terminalExecBtn) {
        terminalExecBtn.addEventListener('click', () => {
          runTerminalCommand().catch((err) => setStatus(`terminal command error: ${err.message}`, 'error'));
        });
      }
      if (terminalCommandInput) {
        terminalCommandInput.addEventListener('keydown', (event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            runTerminalCommand().catch((err) => setStatus(`terminal command error: ${err.message}`, 'error'));
          }
        });
      }
      if (terminalOpenProfileBtn) {
        terminalOpenProfileBtn.addEventListener('click', () => {
          openTerminalProfile().catch((err) => setStatus(`open profile error: ${err.message}`, 'error'));
        });
      }
      if (runNotebookPresetBtn) {
        runNotebookPresetBtn.addEventListener('click', () => {
          runTerminalPresetById('ccbs_notebook_doctor').catch((err) => setStatus(`terminal run error: ${err.message}`, 'error'));
        });
      }
      if (runLanguageCatalogTestBtn) {
        runLanguageCatalogTestBtn.addEventListener('click', () => {
          runTerminalPresetById('ccbs_language_catalog_test').catch((err) => setStatus(`terminal run error: ${err.message}`, 'error'));
        });
      }
      if (runCppPresetBtn) {
        runCppPresetBtn.addEventListener('click', () => {
          runTerminalPresetById('ccbs_cpp_compile_smoke').catch((err) => setStatus(`terminal run error: ${err.message}`, 'error'));
        });
      }
      if (fixAllCapsBtn) {
        fixAllCapsBtn.addEventListener('click', () => {
          runCapabilityFix('fix_all_capabilities', 'Fix All Capabilities', 'all').catch((err) => setStatus(`capability fix error: ${err.message}`, 'error'));
        });
      }
      if (repairCppBtn) {
        repairCppBtn.addEventListener('click', () => {
          runCapabilityFix('repair_cpp', 'Repair C++', 'cpp').catch((err) => setStatus(`capability fix error: ${err.message}`, 'error'));
        });
      }
      if (repairNotebookBtn) {
        repairNotebookBtn.addEventListener('click', () => {
          runCapabilityFix('repair_notebook_runtime', 'Repair Notebook Runtime', 'notebook').catch((err) => setStatus(`capability fix error: ${err.message}`, 'error'));
        });
      }
      if (startLmStudioBtn) {
        startLmStudioBtn.addEventListener('click', () => {
          runCapabilityFix('start_lm_studio', 'Start LM Studio', 'provider').catch((err) => setStatus(`capability fix error: ${err.message}`, 'error'));
        });
      }
      if (terminalAuditBtn) {
        terminalAuditBtn.addEventListener('click', () => {
          runTerminalAudit().catch((err) => setStatus(`audit error: ${err.message}`, 'error'));
        });
      }
      if (openCommandDeckBtn) {
        openCommandDeckBtn.addEventListener('click', () => openInterfacePath('/v3/ui'));
      }
      if (openChatOnlyBtn) {
        openChatOnlyBtn.addEventListener('click', () => openInterfacePath('/v3/chat-ui'));
      }
      if (openAdminUiBtn) {
        openAdminUiBtn.addEventListener('click', () => openInterfacePath('/admin/ui'));
      }
      if (openTerminalPopoutBtn) {
        openTerminalPopoutBtn.addEventListener('click', () => openLiveLogPopout());
      }
      if (openTaskWindowBtn) {
        openTaskWindowBtn.addEventListener('click', () => openTaskWindowPopout());
      }
      if (openChatPopoutBtn) {
        openChatPopoutBtn.addEventListener('click', () => openChatPopout());
      }
      if (openDeckPopoutBtn) {
        openDeckPopoutBtn.addEventListener('click', () => openDeckPopout());
      }
      const openFoundryPaneBtn = document.getElementById('openFoundryPane');
      if (openFoundryPaneBtn) {
        openFoundryPaneBtn.addEventListener('click', () => {
          window.open(window.location.origin + '/v3/foundry-ui', '_blank', 'noopener,noreferrer');
        });
      }
      if (openChatPopoutTerminalBtn) {
        openChatPopoutTerminalBtn.addEventListener('click', () => openChatPopout());
      }
      if (openDeckPopoutTerminalBtn) {
        openDeckPopoutTerminalBtn.addEventListener('click', () => openDeckPopout());
      }

      window.addEventListener('message', (event) => {
        if (event.origin && event.origin !== window.location.origin) return;
        const data = event.data || {};
        const type = String(data.type || '');
        if (type === 'ccbs_task_window_run') {
          handleTaskWindowRun(data.payload || {}).catch((err) => {
            setStatus(`task window error: ${err.message}`, 'error');
          });
          return;
        }
        if (type === 'ccbs_chat_popout_send') {
          handleChatPopoutSend(data.payload || {}).catch((err) => {
            setStatus(`chat pop-out error: ${err.message}`, 'error');
            postChatPopoutMessage('ccbs_chat_popout_status', { status: `Error: ${err.message}`, busy: false });
          });
          return;
        }
        if (type === 'ccbs_deck_popout_select_role') {
          const roleId = String((data.payload || {}).role_id || '').trim().toLowerCase();
          if (!roleId) return;
          applyRole(roleId, true, true);
          saveProfile().catch((err) => setStatus(`role save error: ${err.message}`, 'error'));
        }
      });

      if (opsToggle) opsToggle.addEventListener('click', () => setOpsCollapsed(!state.opsCollapsed, true));
      if (drawerToggle) drawerToggle.addEventListener('click', () => setOpsCollapsed(!state.opsCollapsed, true));
      if (offlineModeSelect) {
        offlineModeSelect.addEventListener('change', () => {
          applyOfflineMode(offlineModeSelect.value, true);
          Promise.all([saveProfile(), loadCatalog(), loadTerminalPresets(), loadTerminalProfiles(), loadOfflineCapabilities()])
            .then(() => setStatus(`offline mode set: ${state.offlineMode}`, 'ok'))
            .catch((err) => setStatus(`offline mode error: ${err.message}`, 'error'));
        });
      }
      if (answerScopeSelect) {
        answerScopeSelect.addEventListener('change', () => {
          setScope(answerScopeSelect.value, false);
        });
      }
      if (scopeConfirmBtn) {
        scopeConfirmBtn.addEventListener('click', () => {
          confirmScopeSelection();
          saveProfile().catch((err) => setStatus(`scope save error: ${err.message}`, 'error'));
        });
      }
      if (scopePromptModeSelect) {
        scopePromptModeSelect.addEventListener('change', () => {
          state.scopePromptMode = normalizeScopePromptMode(scopePromptModeSelect.value, state.scopePromptMode);
          saveProfile().catch((err) => setStatus(`scope mode error: ${err.message}`, 'error'));
        });
      }
      if (liveOutputToggle) {
        liveOutputToggle.addEventListener('click', () => {
          const next = state.liveOutputMode === 'collapsed' ? 'summary' : 'collapsed';
          setLiveOutputMode(next, true);
        });
      }
      if (liveOutputTabSummary) {
        liveOutputTabSummary.addEventListener('click', () => setLiveOutputMode('summary', true));
      }
      if (liveOutputTabRaw) {
        liveOutputTabRaw.addEventListener('click', () => setLiveOutputMode('raw', true));
      }

      themeSelect.addEventListener('change', () => applyTheme(themeSelect.value));
      promptInput.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') sendPrompt();
      });
      setHackerInterfaceVisible(false);

      (async () => {
        try {
          await loadIdentity();
          await loadCatalog();
          await loadProfile();
          await loadLanguageCatalog(false);
          await loadCards();
          await loadOfflineCapabilities();
          await loadApiEvents();
          if (state.threadId) {
            await loadHistory();
          }
          setStatus(`ready (${state.offlineMode})`, 'ok');
          setInterval(() => {
            loadApiEvents().catch(() => {});
          }, 4000);
        } catch (err) {
          setStatus(`startup error: ${err.message}`, 'error');
        }
      })();
    </script>
    """


def render_surface_html(surface: str) -> str:
    raw = str(surface).strip().lower()
    if raw == "chat-ui":
        surface_name = "chat-ui"
    elif raw == "foundry-ui":
        surface_name = "foundry-ui"
    else:
        surface_name = "ui"
    if surface_name == "chat-ui":
        page_title = "CCBS Chat Only"
        heading = "CCBS Chat Only"
        subtitle = "Fluid ask-me-anything mode with dynamic NFT role deck and lightweight ops drawer."
    elif surface_name == "foundry-ui":
        page_title = "CCBS Foundry Lane"
        heading = "CCBS Foundry Lane"
        subtitle = "Foundry remote lane — binary gate enforced. Local tools must be ready before Foundry opens."
    else:
        page_title = "QB Control Center"
        heading = "QB Control Center"
        subtitle = "Task routing, role control, and runtime operations in one dashboard."

    html = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>__PAGE_TITLE__</title>
  <style>
__SHARED_CSS__
  </style>
</head>
<body data-surface=\"__SURFACE__\" class=\"ops-collapsed\">
  <div class=\"app\">
    <aside class=\"panel controls\">
      <div class=\"title\">
        <h1>__HEADING__</h1>
        <div class=\"sub\">__SUBTITLE__</div>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"token\">Bearer Token (optional in owner auto-auth mode)</label>
        <input id=\"token\" placeholder=\"paste API token (optional)\" autocomplete=\"off\" />
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"model\">Model</label>
        <select id=\"model\"></select>
      </div>

      <div class=\"row\">
        <label class=\"toggle\"><input id=\"offlineOnly\" type=\"checkbox\" checked /> Local Only (offline)</label>
        <label class=\"toggle\"><input id=\"allowRemote\" type=\"checkbox\" /> Allow Cloud/Remote</label>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"offlineMode\">Offline Mode</label>
        <select id=\"offlineMode\">
          <option value=\"guided\">Guided</option>
          <option value=\"strict\">Strict</option>
          <option value=\"off\">Off</option>
        </select>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"scopePromptMode\">Scope Confirmation</label>
        <select id=\"scopePromptMode\">
          <option value=\"always\">Always Ask First</option>
          <option value=\"manual\">Manual</option>
        </select>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"profileScope\">Current Profile Scope</label>
        <input id=\"profileScope\" readonly placeholder=\"unknown\" />
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"displayName\">Display Name</label>
        <input id=\"displayName\" placeholder=\"Owner\" />
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"avatarStyle\">Avatar Style</label>
        <select id=\"avatarStyle\">
          <option value=\"nft-core\">NFT Core</option>
          <option value=\"samurai\">Samurai</option>
          <option value=\"strategist\">Strategist</option>
          <option value=\"guardian\">Guardian</option>
        </select>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"theme\">Theme</label>
        <select id=\"theme\">
          <option value=\"neon-deck\">Neon Deck</option>
          <option value=\"cyber-lime\">Cyber Lime</option>
          <option value=\"ocean-core\">Ocean Core</option>
        </select>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"tonePreset\">Tone Preset</label>
        <select id=\"tonePreset\">
          <option value=\"balanced\">Balanced</option>
          <option value=\"concise\">Concise</option>
          <option value=\"coach\">Coach</option>
          <option value=\"architect\">Architect</option>
        </select>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"languageMode\">Language Mode</label>
        <select id=\"languageMode\">
          <option value=\"auto\">Auto (Language + Model)</option>
          <option value=\"manual\">Manual Language Override</option>
        </select>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"manualLanguage\">Manual Language</label>
        <input id=\"manualLanguage\" placeholder=\"e.g. Python, C++, Rust\" />
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"languageStorageMode\">Language Storage</label>
        <select id=\"languageStorageMode\">
          <option value=\"auto\">Auto Fallback</option>
          <option value=\"json\">JSON</option>
          <option value=\"sqlite\">SQLite</option>
          <option value=\"parquet\">Parquet</option>
          <option value=\"feather\">Feather</option>
        </select>
      </div>

      <div class=\"row\">
        <label class=\"toggle\"><input id=\"languageExternalEnrichment\" type=\"checkbox\" /> External GitHub Enrichment</label>
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"cardPack\">Card Pack</label>
        <input id=\"cardPack\" placeholder=\"auto\" />
      </div>

      <div class=\"field\">
        <label class=\"label\" for=\"threadId\">Thread ID</label>
        <input id=\"threadId\" readonly placeholder=\"auto\" />
        <div id=\"threadInfo\" class=\"small\">Thread: auto</div>
      </div>

      <div class=\"row\">
        <button id=\"saveProfile\" type=\"button\">Save Profile</button>
        <button id=\"saveToken\" type=\"button\" class=\"alt\">Save Token</button>
        <button id=\"useBearerProfile\" type=\"button\" class=\"alt\">Use Bearer Identity</button>
        <button id=\"refreshLanguageCatalog\" type=\"button\" class=\"alt\">Refresh Languages</button>
        <button id=\"newThread\" type=\"button\" class=\"alt\">New Thread</button>
        <button id=\"smilesRefresh\" type=\"button\" class=\"smiles\">Refresh UI</button>
        <button id=\"browserReset\" type=\"button\" class=\"warn\">Reset UI State</button>
        <button id=\"openSmileEditor\" type=\"button\" class=\"alt\">Style Editor</button>
      </div>
      <div id=\"languageCatalogCount\" class=\"small\">Catalog Count: loading...</div>

      <div class=\"field\">
        <label class=\"label\">Language and Model Routing</label>
        <pre id=\"languageDecisionStatus\" class=\"steps\" style=\"min-height:80px;max-height:180px;\">No language/model decision yet.</pre>
      </div>

      <div class=\"field\">
        <label class=\"label\">Local Runtime Health</label>
        <div id=\"offlineCapabilities\" class=\"steps\" style=\"min-height:100px;max-height:240px;\">
          Loading offline capabilities...
        </div>
      </div>
    </aside>

    <section class=\"panel main\">
      <div class=\"status-bar\">
        <div id=\"status\" class=\"status\">Ready.</div>
        <div class=\"status-actions\">
          <button id=\"smilesRefreshTop\" type=\"button\" class=\"smiles\">Refresh UI</button>
          <button id=\"browserResetTop\" type=\"button\" class=\"warn\">Reset UI State</button>
        </div>
      </div>
      <div id=\"roleDeck\" class=\"deck\" aria-label=\"Role card buttons\"></div>
      <section class=\"smyles-panel\" aria-label=\"Smyles visual strip\">
        <div class=\"ops-head\">
          <strong>Smyles Visual Strip</strong>
        </div>
        <div id=\"smylesStrip\" class=\"smyles-strip\">
          <div class=\"small\">Loading Smyles visuals...</div>
        </div>
        <div class=\"small\">Role-aligned visuals for quick recognition.</div>
      </section>
      <section id=\"cardDetails\" class=\"panel\" style=\"padding:10px;\">
        <div class=\"ops-head\">
          <strong>Selected Role</strong>
        </div>
        <div id=\"cardExplain\" class=\"small\">Select a role card to view differences and quick actions.</div>
        <div id=\"roleQuickActions\" class=\"row\" style=\"margin-top:8px;\"></div>
      </section>
      <section id=\"scopePanel\" class=\"panel\">
        <div class=\"ops-head\">
          <strong>Scope Router</strong>
        </div>
        <div class=\"scope-row\">
          <div class=\"field\">
            <label class=\"label\" for=\"answerScope\">Answer Scope</label>
            <select id=\"answerScope\">
              <option value=\"repo_grounded\">Repo Grounded</option>
              <option value=\"general_local\">General Local</option>
              <option value=\"remote_allowed\">Remote Allowed</option>
            </select>
          </div>
          <button id=\"scopeConfirm\" type=\"button\" class=\"alt\">Apply Scope</button>
        </div>
        <div id=\"scopeStatus\" class=\"scope-note\">Choose a scope and apply it before sending in Ranger lane.</div>
      </section>
		      <div id=\"feed\" class=\"feed\"></div>
		      <div class=\"composer\">
	        <div id=\"interfaceModeRow\" class=\"row mode-switch dock-hidden\">
	          <button id=\"modeAsk\" type=\"button\" class=\"alt\" aria-pressed=\"true\">Ask Anything</button>
	          <button id=\"modeTerminal\" type=\"button\" class=\"warn\" aria-pressed=\"false\">Hacker Terminal</button>
	          <button id=\"openChatPopoutTerminal\" type=\"button\" class=\"alt\">Pop Out Chat</button>
	          <button id=\"openDeckPopoutTerminal\" type=\"button\" class=\"alt\">Pop Out Cards</button>
	        </div>
	        <div id=\"askPane\">
	          <div class=\"row\">
	            <div class=\"field\" style=\"flex:1;min-width:180px;\">
	              <label class=\"label\" for=\"roleHint\">Role Hint</label>
	              <input id=\"roleHint\" placeholder=\"auto from selected role\" />
	            </div>
	            <div class=\"field\" style=\"width:100px;\">
	              <label class=\"label\" for=\"topK\">Top-K</label>
	              <input id=\"topK\" type=\"number\" min=\"1\" max=\"32\" value=\"5\" />
	            </div>
	          </div>
	          <textarea id=\"prompt\" placeholder=\"Ask me anything...\"></textarea>
	          <div class=\"row\">
            <button id=\"openLanguageDecision\" type=\"button\" class=\"alt\">Routing Details</button>
              <button id=\"openTaskWindow\" type=\"button\" class=\"alt\">Task Planner</button>
              <button id=\"openFoundryPane\" type=\"button\" class=\"alt\">Foundry Remote</button>
            <button id=\"openChatPopout\" type=\"button\" class=\"alt\">Open Chat Window</button>
            <button id=\"openDeckPopout\" type=\"button\" class=\"alt\">Open Role Cards</button>
            <button id=\"send\" type=\"button\">Send Task</button>
            <button id=\"approvePending\" type=\"button\" class=\"warn\">Approve Action</button>
          </div>
        </div>
	        <div id=\"terminalPane\" class=\"terminal-pane dock-hidden\">
	          <div class=\"field\">
	            <label class=\"label\" for=\"terminalCommand\">Terminal Command</label>
	            <input id=\"terminalCommand\" placeholder=\"Type any command (runs exactly as entered)\" />
	          </div>
	          <div class=\"field\">
	            <label class=\"label\" for=\"terminalProfile\">Terminal Profile</label>
	            <select id=\"terminalProfile\">
	              <option value=\"\">Loading terminal profiles...</option>
	            </select>
	          </div>
	          <div class=\"field\">
	            <label class=\"label\" for=\"terminalPreset\">Terminal Preset</label>
	            <select id=\"terminalPreset\">
	              <option value=\"\">Loading terminal presets...</option>
	            </select>
	          </div>
	          <div class=\"row\">
	            <button id=\"terminalExec\" type=\"button\" class=\"warn\">Run Command</button>
	            <button id=\"terminalOpenProfile\" type=\"button\" class=\"warn\">Open Profile</button>
	            <button id=\"terminalRun\" type=\"button\">Run Preset</button>
	            <button id=\"runLanguageCatalogTest\" type=\"button\" class=\"alt\">Language Catalog Test</button>
	            <button id=\"runNotebookPreset\" type=\"button\" class=\"alt\">Notebook Check</button>
	            <button id=\"runCppPreset\" type=\"button\" class=\"alt\">C++ Smoke</button>
	            <button id=\"fixAllCaps\" type=\"button\" class=\"alt\">Fix All Capabilities</button>
	            <button id=\"repairCpp\" type=\"button\" class=\"alt\">Repair C++</button>
	            <button id=\"repairNotebook\" type=\"button\" class=\"alt\">Repair Notebook Runtime</button>
	            <button id=\"startLmStudio\" type=\"button\" class=\"alt\">Start LM Studio</button>
	            <button id=\"openTerminalPopout\" type=\"button\" class=\"alt\">Pop Out Live Log</button>
	            <button id=\"terminalAudit\" type=\"button\" class=\"alt\">Preset Audit</button>
	            <button id=\"openCommandDeck\" type=\"button\" class=\"alt\">Open Command Deck</button>
	            <button id=\"openChatOnly\" type=\"button\" class=\"alt\">Open Chat UI</button>
	            <button id=\"openAdminUi\" type=\"button\" class=\"alt\">Open Admin UI</button>
	          </div>
		          <pre id=\"terminalOutput\" class=\"terminal-output\">Type a command and click Run Command, or use presets/profiles.</pre>
		        </div>
            <section id=\"liveOutput\" class=\"live-console collapsed\">
              <div class=\"live-console-head\">
                <strong>Activity Log</strong>
                <div class=\"live-console-tabs\">
                  <button id=\"liveOutputToggle\" type=\"button\" class=\"alt\">Show/Hide</button>
                  <button id=\"liveOutputTabSummary\" type=\"button\" class=\"alt\" aria-pressed=\"false\">Summary View</button>
                  <button id=\"liveOutputTabRaw\" type=\"button\" class=\"warn\" aria-pressed=\"false\">Raw Events</button>
                </div>
              </div>
              <div class=\"live-console-body\">
                <pre id=\"liveOutputSummary\" style=\"display:none;\">No API events yet.</pre>
                <pre id=\"liveOutputRaw\" style=\"display:none;\">No API events yet.</pre>
              </div>
            </section>
		      </div>

      <section id=\"opsDrawer\" class=\"panel\" style=\"padding:10px;\">
        <div class=\"ops-head\">
          <strong>Run Details</strong>
          <button id=\"drawerToggle\" type=\"button\" class=\"btn alt\" aria-expanded=\"false\">Toggle</button>
        </div>
        <div class=\"drawer-content\">
          <div id=\"drawerSteps\" class=\"steps\">No run yet.</div>
        </div>
      </section>
    </section>

    <aside id=\"opsPanel\" class=\"panel ops\">
      <div class=\"ops-head\">
        <strong>System Panel</strong>
        <button id=\"opsToggle\" type=\"button\" class=\"btn alt\" aria-expanded=\"false\">Toggle</button>
      </div>
      <div class=\"ops-content\">
        <div id=\"steps\" class=\"steps\">No run yet.</div>
      </div>
    </aside>
  </div>
  <dialog id=\"languageDecisionModal\" class=\"panel\" style=\"max-width:760px;\">
    <form method=\"dialog\" class=\"language-modal-form\">
      <strong>Language + Model Decision</strong>
      <div id=\"languageDecisionSummary\" class=\"small language-modal-summary\">No decision yet.</div>
      <div class=\"language-modal-grid\">
        <div class=\"field\">
          <label class=\"label\" for=\"modalLanguageMode\">Mode</label>
          <select id=\"modalLanguageMode\">
            <option value=\"auto\">Auto</option>
            <option value=\"manual\">Manual</option>
          </select>
        </div>
        <div class=\"field\">
          <label class=\"label\" for=\"modalScopeRecommendation\">Recommended Scope</label>
          <input id=\"modalScopeRecommendation\" readonly />
        </div>
        <div class=\"field\">
          <label class=\"label\" for=\"modalSelectedLanguage\">Selected Language</label>
          <input id=\"modalSelectedLanguage\" />
        </div>
        <div class=\"field\">
          <label class=\"label\" for=\"modalTopLanguages\">Top Languages</label>
          <input id=\"modalTopLanguages\" readonly />
        </div>
        <div class=\"field\">
          <label class=\"label\" for=\"modalSelectedRoute\">Selected Route</label>
          <input id=\"modalSelectedRoute\" readonly />
        </div>
        <div class=\"field\">
          <label class=\"label\" for=\"modalDecisionConfidence\">Confidence</label>
          <input id=\"modalDecisionConfidence\" readonly />
        </div>
        <div class=\"field\">
          <label class=\"label\" for=\"modalHybridMode\">Hybrid Mode</label>
          <input id=\"modalHybridMode\" readonly />
        </div>
      </div>
      <pre id=\"languageDecisionTrace\" class=\"steps language-modal-trace\">No trace available.</pre>
      <div class=\"row\">
        <button id=\"copyDecisionTrace\" type=\"button\" class=\"alt\">Copy Trace</button>
        <button value=\"apply\" type=\"submit\">Apply Decision</button>
        <button value=\"close\" type=\"submit\" class=\"warn\">Close</button>
      </div>
    </form>
  </dialog>
  <dialog id=\"confirmModal\" class=\"panel\" style=\"max-width:560px;\">
    <form method=\"dialog\" style=\"display:grid;gap:10px;\">
      <strong id=\"confirmTitle\">Confirm action</strong>
      <div id=\"confirmBody\" class=\"small\"></div>
      <div class=\"row\">
        <button id=\"confirmOk\" value=\"confirm\" type=\"submit\">Run</button>
        <button id=\"confirmCancel\" value=\"cancel\" type=\"submit\" class=\"warn\">Cancel</button>
      </div>
    </form>
  </dialog>
__SHARED_JS__
</body>
</html>
"""

    return (
        html.replace("__PAGE_TITLE__", page_title)
        .replace("__HEADING__", heading)
        .replace("__SUBTITLE__", subtitle)
        .replace("__SURFACE__", surface_name)
        .replace("__SHARED_CSS__", _shared_css())
        .replace("__SHARED_JS__", _shared_js())
    )


def redesign_enabled() -> bool:
    return _flag_enabled("CCBS_UI_REDESIGN_ENABLE", True)
