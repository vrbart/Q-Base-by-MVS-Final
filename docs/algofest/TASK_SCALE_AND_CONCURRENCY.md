# Task Scale And Concurrency Proof

Q-Base by MVS was built and packaged as a **large orchestration workflow**, not as a single prompt-response demo.

## What Is Defensible

The strongest honest claim is not "20 visible windows were on screen."  
The strongest honest claim is:

- the public system is configured for **10 orchestration lanes**
- the lane manager currently reports **10/10 available**
- the latest demo run logged **196 task actions**
- the public repo contains **160 tracked files**
- the curated submission surface includes runtime code, automation, docs, examples, tests, and gallery assets

## Evidence

### 1. Ten-lane orchestration surface

The public configuration file defines **10 instances**:

- `clean-core`
- `playground`
- `ccbs-pro`
- `aux-04`
- `aux-05`
- `aux-06`
- `aux-07`
- `aux-08`
- `aux-09`
- `aux-10`

Source:

- [`config/codex_instances_10.json`](../../config/codex_instances_10.json)

### 2. Lane manager availability

The lane manager currently reports:

- `codex_cli_found: true`
- `availability_counter: 10/10`

That means the orchestration surface is prepared for ten available lanes even if the demo video only shows one browser UI.

### 3. Large task graph in the recorded run

The latest recorded demo step log shows:

- `task_actions_done: 196`
- `logged step events: 252`

This is important because the public demo is not a static page recording. It is a repeated execution loop involving refresh, sync, route, optimize, checkpoints, and evidence-oriented state changes.

Source:

- [`dist/demo/qb_demo_steps.json`](../../dist/demo/qb_demo_steps.json)

### 4. Curated public delivery work

The public repository is also part of the task graph. The final published surface includes:

- core runtime code
- PowerShell orchestration
- batch launchers
- browser automation
- validation scripts
- curated submission docs
- examples and evidence assets
- tests
- gallery images

Public scope at the time of packaging:

- **160 tracked files**
- **4 focused tests**
- **4 gallery images**

## Why The Video Shows One Screen

The recorder captures a **single orchestration control surface** in the browser.  
It does **not** try to show every background worker shell, every possible lane window, or every local process.

So the correct interpretation is:

- the video proves the control plane was active
- the config and lane manager prove the system scale
- the step log proves the task volume

## Submission-Safe Summary

Use this wording on the project page if needed:

> Q-Base was developed and packaged as a long orchestration workflow rather than a single prompt-response demo. The public proof surface shows 10 configured lanes, 10/10 lane availability, and a recorded run with 196 task actions across routing, optimization, synchronization, checkpointing, and evidence capture.

