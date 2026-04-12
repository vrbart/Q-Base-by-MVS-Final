import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

function argValue(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  if (idx === -1 || idx + 1 >= process.argv.length) {
    return fallback;
  }
  return process.argv[idx + 1];
}

function hasArg(name) {
  return process.argv.includes(name);
}

async function firstVisibleLocator(page, selectors) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if ((await locator.count()) < 1) {
      continue;
    }
    try {
      if (await locator.isVisible({ timeout: 750 })) {
        return locator;
      }
    } catch {
      // keep scanning selectors
    }
  }
  return null;
}

async function safeClick(locator, timeoutMs = 1500) {
  try {
    await locator.click({ timeout: timeoutMs });
    return true;
  } catch {
    return false;
  }
}

async function waitForTableRows(page, selector, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const count = await page.locator(`${selector} tr`).count();
      if (count > 0) {
        return true;
      }
    } catch {
      // ignore
    }
    await page.waitForTimeout(500);
  }
  return false;
}

async function clickFirstMatchingButton(page, patterns) {
  for (const pattern of patterns) {
    try {
      const button = page.getByRole("button", { name: pattern }).first();
      if ((await button.count()) < 1) {
        continue;
      }
      await button.click({ timeout: 1250 });
      return true;
    } catch {
      // keep trying
    }
  }
  return false;
}

async function newestWebmFile(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".webm"))
    .map((entry) => path.join(dir, entry.name));
  if (files.length === 0) {
    return "";
  }
  let newest = files[0];
  let newestMtime = (await fs.stat(newest)).mtimeMs;
  for (const file of files.slice(1)) {
    const mtime = (await fs.stat(file)).mtimeMs;
    if (mtime > newestMtime) {
      newest = file;
      newestMtime = mtime;
    }
  }
  return newest;
}

async function main() {
  const url = argValue("--url", "http://127.0.0.1:11435/v3/ui");
  const outDir = path.resolve(argValue("--output-dir", path.join("dist", "demo")));
  const prompt = argValue(
    "--prompt",
    "Build a simple team productivity web app (auth + todo CRUD + docs + deploy). Decompose and assign across 3 lanes; show optimizer decision + evidence"
  );
  // Default to ~4:20 so a direct `node capture_ui_demo.mjs` run doesn't stop early.
  const durationSec = Math.max(5, Number.parseInt(argValue("--duration-sec", "260"), 10) || 260);
  const headed = hasArg("--headed");
  // Tune defaults for "busy but readable" and to reach >= 200 visible actions in ~4:20.
  const paceMs = Math.max(150, Number.parseInt(argValue("--pace-ms", "650"), 10) || 650);
  const holdMs = Math.max(300, Number.parseInt(argValue("--hold-ms", "900"), 10) || 900);
  const targetActions = Math.max(10, Number.parseInt(argValue("--target-actions", "200"), 10) || 200);
  const requestedCyclesRaw = Number.parseInt(argValue("--cycles", ""), 10);
  const requestedCycles = Number.isFinite(requestedCyclesRaw) ? requestedCyclesRaw : 0;
  const cycles = Math.max(1, requestedCycles > 0 ? requestedCycles : Math.ceil(targetActions / 2));
  const endBufferMs = Math.max(8000, Number.parseInt(argValue("--end-buffer-ms", "9000"), 10) || 9000);

  await fs.mkdir(outDir, { recursive: true });

  const browser = await chromium.launch({
    headless: !headed,
    args: [
      "--disable-background-timer-throttling",
      "--disable-backgrounding-occluded-windows",
      "--disable-renderer-backgrounding"
    ]
  });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: {
      dir: outDir,
      size: { width: 1920, height: 1080 }
    }
  });

  const page = await context.newPage();
  const video = page.video();

  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await page.locator("#refresh").waitFor({ state: "visible", timeout: 20000 });
  await page.bringToFront().catch(() => {});

  // Slight zoom improves readability on 1080p recordings.
  await page.evaluate(() => {
    // eslint-disable-next-line no-param-reassign
    document.documentElement.style.scrollBehavior = "smooth";
    // eslint-disable-next-line no-param-reassign
    document.body.style.zoom = "110%";
  });

  // On-screen step overlay so the video clearly shows multiple actions.
  await page.evaluate(() => {
    const existing = document.getElementById("qbStepOverlay");
    if (existing) existing.remove();
    const el = document.createElement("div");
    el.id = "qbStepOverlay";
    el.style.position = "fixed";
    el.style.right = "18px";
    el.style.bottom = "18px";
    el.style.zIndex = "99999";
    el.style.padding = "10px 12px";
    el.style.borderRadius = "12px";
    el.style.border = "1px solid rgba(110,191,255,0.45)";
    el.style.background = "rgba(7,16,38,0.92)";
    el.style.boxShadow = "0 16px 30px rgba(0,0,0,0.35)";
    el.style.color = "#e9f5ff";
    el.style.fontFamily = "\"Space Grotesk\", \"Segoe UI\", sans-serif";
    el.style.fontSize = "12px";
    el.style.letterSpacing = "0.04em";
    el.style.textTransform = "uppercase";
    el.textContent = "DEMO: loading…";
    document.body.appendChild(el);
  });

  async function setOverlay(text) {
    await page.evaluate((t) => {
      const el = document.getElementById("qbStepOverlay");
      if (el) el.textContent = t;
    }, text);
  }

  const startShot = path.join(outDir, "qb_demo_start.png");
  await page.screenshot({ path: startShot, fullPage: true });

  const startedAt = Date.now();
  const stepLog = [];
  let taskActionsDone = 0;

  const workItems = [
    {
      label: "frontend: auth + todo ui",
      ask: "Build responsive UI: login, add todo, mark done, list completed. Use clean labels and UX."
    },
    {
      label: "backend: auth + todo api",
      ask: "Design REST API: login/register, create/list/update todos, auth middleware, validation."
    },
    {
      label: "db: schema + migrations",
      ask: "Define data model: users, todos, timestamps, indexes. Provide migration + seed."
    },
    {
      label: "tests: smoke + auth",
      ask: "Add smoke tests: login flow, todo CRUD, completed list. Keep fast and deterministic."
    },
    {
      label: "docs: run + deploy",
      ask: "Write concise docs: setup, env vars, one-command run, deploy options, expected outputs."
    },
    {
      label: "deploy: container",
      ask: "Create a simple deploy path: Dockerfile + compose + health check. Document it."
    }
  ];

  async function shot(name) {
    const p = path.join(outDir, name);
    await page.screenshot({ path: p, fullPage: true });
    return p;
  }

  async function mark(step, action, extra = {}) {
    const entry = Object.assign(
      {
        step,
        action,
        t_ms: Date.now() - startedAt
      },
      extra
    );
    stepLog.push(entry);
    return entry;
  }

  // 1) Refresh (loads lane snapshot + telemetry)
  await setOverlay(`STEP 1/6: Refresh (load lanes + telemetry) | tasks ${taskActionsDone}/${targetActions}`);
  await mark(1, "refresh", { ok: await safeClick(page.locator("#refresh")) });
  await page.waitForTimeout(holdMs);
  await shot("qb_step_1_refresh.png");

  // 2) Sync workspaces (keeps lane registry deterministic)
  await setOverlay(`STEP 2/6: Sync Workspaces (idempotent) | tasks ${taskActionsDone}/${targetActions}`);
  await mark(2, "sync", { ok: await safeClick(page.locator("#sync")) });
  await page.waitForTimeout(holdMs);
  await shot("qb_step_2_sync.png");

  // 2.5) Launch lanes (safe/no-op if already running, makes the deck feel alive)
  await setOverlay(`STEP 2/6: Launch Lanes (idempotent) | tasks ${taskActionsDone}/${targetActions}`);
  await mark(2, "launch_lanes", { ok: await safeClick(page.locator("#launch")) });
  await page.waitForTimeout(Math.max(holdMs, 2600));
  await shot("qb_step_2b_launch.png");

  // 3) Route + 4) Optimize cycles (multiple visible actions, still deterministic)
  const askInput = page.locator("#askInput");
  const taskLabel = page.locator("#taskLabel");
  const applyUsage = page.locator("#applyUsage");
  const appScanSummary = page.locator("details").filter({ hasText: "App Capability Scan" }).locator("summary");
  const targetTotalMs = durationSec * 1000;
  let i = 1;
  while (
    i <= cycles &&
    taskActionsDone < targetActions &&
    Date.now() - startedAt < targetTotalMs - endBufferMs
  ) {
    const directive = ["-1", "-2", "-3"][(i - 1) % 3];
    const parallel = ["3", "4", "5"][(i - 1) % 3];
    const item = workItems[(i - 1) % workItems.length];
    await setOverlay(`STEP 3/6: Route Ask (cycle ${i}, ${directive}) | tasks ${taskActionsDone}/${targetActions}`);
    // Flip apply-usage so telemetry visibly changes in a predictable pattern.
    await applyUsage.selectOption(i % 2 === 0 ? "false" : "true").catch(() => {});
    if ((await askInput.count()) > 0) {
      const askText =
        `${directive} ${prompt}\n` +
        `- ${item.ask}\n` +
        `- Subtasks: UI, API, DB, auth, tests, docs, deploy, security checks\n` +
        `- Acceptance: runnable locally, clear outputs, evidence captured\n` +
        `- Constraints: safe defaults, reproducible, no hardcoded secrets\n` +
        `- Deliverables: code, docs, tests, deploy notes, quickstart\n` +
        `- Evidence: logs + artifacts + decision summary JSON`;
      await askInput.fill(askText);
    }
    if ((await taskLabel.count()) > 0) {
      const ts = new Date().toISOString().replace(/[:.]/g, "").slice(0, 15);
      await taskLabel.fill(`demo-c${String(i).padStart(2, "0")}: ${item.label} (${ts})`);
    }
    await page.waitForTimeout(paceMs);
    const routeOk = await safeClick(page.locator("#routeAsk"));
    if (routeOk) taskActionsDone += 1;
    const routeEntry = await mark(3, "route", { cycle: i, ok: routeOk, task_actions_done: taskActionsDone });
    routeEntry.rows_ready = await waitForTableRows(page, "#routeRows", 8000);
    await page.locator("#routeRows").scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(holdMs);
    if (i <= 3 || i % 10 === 0) {
      await shot(`qb_step_3_route_c${i}.png`);
    }

    await setOverlay(`STEP 4/6: Optimize (cycle ${i}/${cycles}, parallel=${parallel}) | tasks ${taskActionsDone}/${targetActions}`);
    // Set parallelism dropdown so the UI visibly changes state between cycles.
    await page.selectOption("#parallel", parallel).catch(() => {});
    const optOk = await safeClick(page.locator("#optimize"));
    if (optOk) taskActionsDone += 1;
    const optEntry = await mark(4, "optimize", { cycle: i, ok: optOk, task_actions_done: taskActionsDone });
    optEntry.rows_ready = await waitForTableRows(page, "#decisionRows", 8000);
    await page.locator("#decisionRows").scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(holdMs);
    if (i <= 3 || i % 10 === 0) {
      await shot(`qb_step_4_optimize_c${i}.png`);
    }

    // Every few cycles, re-run refresh/sync so the status line changes and the deck looks alive.
    if (i % 4 === 0) {
      await setOverlay(`STEP 1/6: Refresh (checkpoint after cycle ${i}) | tasks ${taskActionsDone}/${targetActions}`);
      await mark(1, "refresh_checkpoint", { cycle: i, ok: await safeClick(page.locator("#refresh")) });
      await page.waitForTimeout(Math.min(holdMs, 2200));
    }
    if (i % 8 === 0) {
      await setOverlay(`STEP 2/6: Sync Workspaces (checkpoint after cycle ${i}) | tasks ${taskActionsDone}/${targetActions}`);
      await mark(2, "sync_checkpoint", { cycle: i, ok: await safeClick(page.locator("#sync")) });
      await page.waitForTimeout(Math.min(holdMs, 2200));
    }
    if (i % 6 === 0 && (await appScanSummary.count()) > 0) {
      await setOverlay(`STEP 5/6: App Capability Scan (checkpoint after cycle ${i}) | tasks ${taskActionsDone}/${targetActions}`);
      await mark(5, "capability_scan_toggle", { cycle: i, ok: await safeClick(appScanSummary) });
      await page.waitForTimeout(Math.min(holdMs, 2200));
    }

    i += 1;
  }

  // 5) Expand capability scan section for visual proof (if present)
  await setOverlay(`STEP 5/6: Evidence (capability scan + snapshots) | tasks ${taskActionsDone}/${targetActions}`);
  if ((await appScanSummary.count()) > 0) {
    await safeClick(appScanSummary);
    await page.waitForTimeout(holdMs);
  }
  await mark(5, "evidence_expand", { ok: true });
  await shot("qb_step_5_evidence.png");

  await setOverlay(`STEP 6/6: Done (hold for readability) | tasks ${taskActionsDone}/${targetActions}`);

  const stepLogPath = path.join(outDir, "qb_demo_steps.json");

  // Pad out recording to requested duration, but keep the screen "alive" so there's no dead time.
  const deadline = startedAt + durationSec * 1000;
  let keepAliveTick = 0;
  while (Date.now() < deadline) {
    const remaining = deadline - Date.now();
    if (remaining < 1200) {
      break;
    }
    keepAliveTick += 1;
    await setOverlay(`BONUS: Refresh + Sync (tick ${keepAliveTick}) | tasks ${taskActionsDone}/${targetActions}`);
    await safeClick(page.locator("#refresh"));
    await page.waitForTimeout(Math.min(holdMs, 800));
    await safeClick(page.locator("#sync"));
    await page.waitForTimeout(Math.min(holdMs, 800));
    if (keepAliveTick % 3 === 0 && (await appScanSummary.count()) > 0) {
      await safeClick(appScanSummary);
      await page.waitForTimeout(420);
    }
  }

  // Write a machine-readable log so reviewers can confirm each action ran.
  await fs.writeFile(
    stepLogPath,
    `${JSON.stringify(
      {
        url,
        headed,
        pace_ms: paceMs,
        hold_ms: holdMs,
        target_actions: targetActions,
        task_actions_done: taskActionsDone,
        cycles_max: cycles,
        end_buffer_ms: endBufferMs,
        steps: stepLog
      },
      null,
      2
    )}\n`,
    "utf-8"
  );

  const tailMs = Math.max(0, deadline - Date.now());
  if (tailMs > 0) {
    await page.waitForTimeout(tailMs);
  }

  const endShot = path.join(outDir, "qb_demo_end.png");
  await page.screenshot({ path: endShot, fullPage: true });

  await page.close();
  let videoPath = "";
  if (video) {
    try {
      videoPath = await video.path();
    } catch {
      videoPath = "";
    }
  }
  await context.close();
  await browser.close();

  if (!videoPath) {
    videoPath = await newestWebmFile(outDir);
  }

  let finalVideoPath = videoPath;
  if (videoPath) {
    const target = path.join(outDir, "qb_demo_capture.webm");
    if (path.resolve(videoPath) !== path.resolve(target)) {
      await fs.copyFile(videoPath, target);
      finalVideoPath = target;
    }
  }

  const summary = {
    ok: true,
    url,
    prompt,
    duration_sec: durationSec,
    headed,
    target_actions: targetActions,
    task_actions_done: taskActionsDone,
    outputs: {
      video: finalVideoPath,
      screenshot_start: startShot,
      screenshot_end: endShot,
      step_log: stepLogPath
    }
  };
  // machine-readable output for automation systems
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

main().catch((err) => {
  process.stderr.write(`capture_ui_demo failed: ${err?.stack || err}\n`);
  process.exit(1);
});
