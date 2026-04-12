This folder contains the portable evidence bundle produced from `examples/sample_project.json`.

Files:
- `sample_project_bundle.json`: collected run bundle with input batch, run record, and decision manifest.

Notes:
- The public repo's quantum CLI depends on `apps.orchestrator`, which is present in the main workspace but not packaged into this curated export.
- The evidence run was executed with a combined `PYTHONPATH` so the public repo CLI could use the shared orchestrator runtime and persist a real bundle.
