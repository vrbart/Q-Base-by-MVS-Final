# Technologies Used (AlgoFest)

## Core Runtime

- Python
- PowerShell
- Batch launcher wrappers

## Application Stack

- `ccbs_app` Python modules (`src/ccbs_app/*`)
- FastAPI/Uvicorn API surface (via `ccbs_app.cli ai api serve`)
- Browser UI surface at `/v3/ui`

## Orchestration And Multi-Instance

- Multi-lane runtime orchestration (`scripts/codex_multi_manager.ps1`)
- Runtime health/doctor flow (`scripts/qb_doctor.ps1`, `QB-doctor.bat`)
- Lane routing/parser metadata (`src/ccbs_app/multi_instance_agent.py`)

## AI/Model Integration

- Codex CLI lane integration
- Local model fallback surfaces (as configured)

## Quantum Extension

- Azure CLI + Azure Quantum extension
- Azure Quantum workspace integration (`scripts/qb_quantum_multi_instance.ps1`)
- Quantinuum and Rigetti simulator targets (when enabled)

## Quality And Verification

- Pytest for targeted subsystem verification:
  - `tests/test_multi_instance_agent.py`
  - `tests/test_multi_instance_api_surface.py`
  - `tests/test_ai3_foundry_pane.py`
