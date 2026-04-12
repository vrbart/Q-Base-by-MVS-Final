"""Build-a-thon prototype helpers for local multi-agent orchestration and Microsoft handoff."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .repo import RepoError, repo_root


DEFAULT_SCENARIO_ID = "governed-ops-incident"
DEFAULT_COHORT = "Americas Timezone waitlist (starting May 4, 2026)"
DEFAULT_REGION = "North America"
DEFAULT_TEAM_TYPE = "We are Agent & AI enthusiasts learning to innovate with Microsoft products"
DEFAULT_EXPERIENCE_LEVEL = "We have some hands-on experience"
DEFAULT_COPILOT_STUDIO_ACCESS = "No, we do not have access; but we will obtain required access prior to the Build-A-Thon"

ORCHESTRATOR = {
    "agent_id": "control_tower_orchestrator",
    "display_name": "Control Tower Orchestrator",
    "kind": "orchestrator",
    "purpose": "Own intake, delegation order, human checkpoints, and final state.",
    "microsoft_surface": "Copilot Studio primary orchestrator agent",
}

SPECIALIST_AGENTS: list[dict[str, Any]] = [
    {
        "agent_id": "routing_specialist",
        "display_name": "Routing Specialist",
        "enabled_by_default": True,
        "purpose": "Classify the request and choose the right downstream specialists.",
        "microsoft_surface": "Copilot Studio topic or secondary specialist agent",
    },
    {
        "agent_id": "policy_guard",
        "display_name": "Policy Guard",
        "enabled_by_default": True,
        "purpose": "Detect risky actions, policy boundaries, and approval requirements.",
        "microsoft_surface": "Copilot Studio guardrail instructions plus policy topics",
    },
    {
        "agent_id": "evidence_retriever",
        "display_name": "Evidence Retriever",
        "enabled_by_default": True,
        "purpose": "Pull known facts, prior runbooks, and environment evidence before action.",
        "microsoft_surface": "Knowledge sources, Dataverse, or retrieval plugin",
    },
    {
        "agent_id": "execution_planner",
        "display_name": "Execution Planner",
        "enabled_by_default": True,
        "purpose": "Turn the request into bounded execution steps with checkpoints.",
        "microsoft_surface": "Copilot Studio orchestration logic or Power Automate planning flow",
    },
    {
        "agent_id": "executive_reporter",
        "display_name": "Executive Reporter",
        "enabled_by_default": True,
        "purpose": "Produce the final audit-ready summary for humans.",
        "microsoft_surface": "Copilot Studio final response composition",
    },
    {
        "agent_id": "approval_manager",
        "display_name": "Approval Manager",
        "enabled_by_default": False,
        "purpose": "Pause risky flows until a human approves the next action.",
        "microsoft_surface": "Power Automate approvals or Copilot Studio action gating",
    },
    {
        "agent_id": "tool_runner",
        "display_name": "Tool Runner",
        "enabled_by_default": False,
        "purpose": "Execute bounded diagnostics or remediation tasks after approval.",
        "microsoft_surface": "Power Automate flow, connector, or secure action plugin",
    },
    {
        "agent_id": "compliance_reviewer",
        "display_name": "Compliance Reviewer",
        "enabled_by_default": False,
        "purpose": "Check audit, privacy, and control obligations before closure.",
        "microsoft_surface": "Compliance topic or specialist Copilot Studio agent",
    },
    {
        "agent_id": "notification_handoff",
        "display_name": "Notification Handoff",
        "enabled_by_default": False,
        "purpose": "Notify operators, stakeholders, or Teams channels with the right level of detail.",
        "microsoft_surface": "Teams message action or Power Automate notification flow",
    },
    {
        "agent_id": "knowledge_publisher",
        "display_name": "Knowledge Publisher",
        "enabled_by_default": False,
        "purpose": "Convert resolved work into reusable knowledge or runbook content.",
        "microsoft_surface": "Dataverse or SharePoint knowledge update flow",
    },
]

SCENARIOS: dict[str, dict[str, Any]] = {
    DEFAULT_SCENARIO_ID: {
        "scenario_id": DEFAULT_SCENARIO_ID,
        "title": "Governed IT Operations Incident Triage",
        "description": (
            "A support engineer receives a production operations incident and needs a governed agentic "
            "workflow for triage, approvals, bounded remediation, and an audit-ready handoff."
        ),
        "default_request": (
            "A production support engineer reports recurring environment health failures and needs a governed "
            "plan for diagnostics, approvals, remediation, stakeholder notification, and an audit-ready summary."
        ),
        "business_goal": (
            "Reduce time-to-triage while keeping approvals, evidence capture, and operator trust intact."
        ),
        "default_specialists": [
            "routing_specialist",
            "policy_guard",
            "evidence_retriever",
            "execution_planner",
            "executive_reporter",
        ],
    }
}


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _keyword_hit(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(item in lowered for item in keywords)


def _agent_catalog_map() -> dict[str, dict[str, Any]]:
    return {item["agent_id"]: dict(item) for item in SPECIALIST_AGENTS}


def list_specialist_agents() -> dict[str, Any]:
    return {
        "orchestrator": dict(ORCHESTRATOR),
        "delegation_limit": len(SPECIALIST_AGENTS),
        "specialists": [dict(item) for item in SPECIALIST_AGENTS],
    }


def _classify_request(request: str) -> dict[str, Any]:
    lowered = request.lower()
    needs_execution = _keyword_hit(lowered, {"fix", "repair", "run", "execute", "remediate", "restart"})
    high_risk = _keyword_hit(
        lowered,
        {"production", "prod", "admin", "credential", "password", "delete", "firewall", "network"},
    )
    needs_compliance = _keyword_hit(lowered, {"audit", "policy", "privacy", "compliance", "control"})
    needs_notifications = _keyword_hit(lowered, {"incident", "outage", "stakeholder", "notify", "teams"})
    recurring_issue = _keyword_hit(lowered, {"recurring", "repeat", "repeated", "again", "runbook"})

    if _keyword_hit(lowered, {"incident", "outage", "health", "failure", "triage"}):
        request_type = "incident_triage"
    elif _keyword_hit(lowered, {"change", "deploy", "rollout", "release"}):
        request_type = "change_request"
    else:
        request_type = "operations_request"

    risk_level = "high" if high_risk or needs_execution else "medium"
    approval_required = high_risk or needs_execution

    return {
        "request_type": request_type,
        "risk_level": risk_level,
        "needs_execution": needs_execution,
        "approval_required": approval_required,
        "needs_compliance": needs_compliance,
        "needs_notifications": needs_notifications,
        "recurring_issue": recurring_issue,
    }


def _select_specialists(
    scenario: dict[str, Any],
    classification: dict[str, Any],
    max_specialists: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    catalog = _agent_catalog_map()
    selected_ids: list[str] = list(scenario.get("default_specialists", []))

    if classification.get("approval_required"):
        selected_ids.append("approval_manager")
    if classification.get("needs_execution"):
        selected_ids.append("tool_runner")
    if classification.get("needs_compliance"):
        selected_ids.append("compliance_reviewer")
    if classification.get("needs_notifications"):
        selected_ids.append("notification_handoff")
    if classification.get("recurring_issue"):
        selected_ids.append("knowledge_publisher")

    deduped: list[str] = []
    for agent_id in selected_ids:
        if agent_id in catalog and agent_id not in deduped:
            deduped.append(agent_id)

    capped = max(1, min(len(SPECIALIST_AGENTS), int(max_specialists)))
    active_ids = deduped[:capped]
    deferred_ids = deduped[capped:]
    return ([catalog[item] for item in active_ids], deferred_ids)


def _approval_reasons(request: str, classification: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    lowered = request.lower()
    if classification.get("approval_required"):
        reasons.append("Risky actions must remain human-approved before execution.")
    if "production" in lowered or "prod" in lowered:
        reasons.append("Production-impacting work should not run without operator confirmation.")
    if any(token in lowered for token in ["credential", "password", "admin"]):
        reasons.append("Sensitive identity or admin operations require explicit approval.")
    return reasons


def _agent_output(agent_id: str, request: str, scenario: dict[str, Any], classification: dict[str, Any]) -> str:
    if agent_id == "routing_specialist":
        return (
            f"Classified the request as {classification['request_type']} with {classification['risk_level']} risk, "
            "then delegated to the specialists needed for triage, policy review, evidence, planning, and reporting."
        )
    if agent_id == "policy_guard":
        return (
            "Flagged approval checkpoints for risky or production-impacting actions and kept the flow bounded "
            "instead of allowing unrestricted automation."
        )
    if agent_id == "evidence_retriever":
        return (
            "Requested prior incidents, known environment facts, and existing runbooks before planning any action, "
            "so the controller starts from evidence rather than guesswork."
        )
    if agent_id == "execution_planner":
        return (
            "Produced a bounded execution plan: validate context, collect diagnostics, pause for approval, "
            "run the approved action, verify the result, and record the outcome."
        )
    if agent_id == "executive_reporter":
        return (
            f"Prepared a concise operator summary for the scenario '{scenario['title']}', including request type, "
            "risk, approvals, and next actions."
        )
    if agent_id == "approval_manager":
        return "Inserted explicit human approval before remediation or admin-level actions continue."
    if agent_id == "tool_runner":
        return "Reserved execution for approved diagnostics and remediation steps instead of allowing free-form commands."
    if agent_id == "compliance_reviewer":
        return "Checked whether audit, privacy, or control requirements should shape the final workflow and records."
    if agent_id == "notification_handoff":
        return "Prepared stakeholder-ready notifications for Teams or other channels after triage results are known."
    if agent_id == "knowledge_publisher":
        return "Captured the resolved pattern as reusable knowledge so future incidents can start from a runbook."
    return f"Reviewed the request: {request}"


def run_local_buildathon_controller(
    request: str,
    scenario_id: str = DEFAULT_SCENARIO_ID,
    max_specialists: int = 5,
) -> dict[str, Any]:
    normalized_request = _normalize_text(request)
    if not normalized_request:
        raise ValueError("request is required")
    if scenario_id not in SCENARIOS:
        raise ValueError(f"unknown scenario_id: {scenario_id}")

    scenario = dict(SCENARIOS[scenario_id])
    classification = _classify_request(normalized_request)
    specialists, deferred = _select_specialists(scenario, classification, max_specialists=max_specialists)
    approvals = _approval_reasons(normalized_request, classification)

    agent_outputs = [
        {
            "agent_id": ORCHESTRATOR["agent_id"],
            "display_name": ORCHESTRATOR["display_name"],
            "kind": ORCHESTRATOR["kind"],
            "output": (
                f"Received the request for '{scenario['title']}' and delegated to {len(specialists)} specialist agent(s) "
                f"out of a catalog of {len(SPECIALIST_AGENTS)}."
            ),
        }
    ]
    for item in specialists:
        agent_outputs.append(
            {
                "agent_id": item["agent_id"],
                "display_name": item["display_name"],
                "kind": "specialist",
                "output": _agent_output(item["agent_id"], normalized_request, scenario, classification),
            }
        )

    final_summary = (
        "CCBS can be demonstrated here as a multi-agent control surface: one orchestrator delegates to specialist "
        f"agents for routing, policy, evidence, planning, and reporting, with up to {len(SPECIALIST_AGENTS)} specialist "
        "roles available, human approvals enforced for risky actions, and one audit-ready final answer for operators."
    )

    return {
        "prototype_name": "CCBS Multi-Agent Buildathon Prototype",
        "scenario": scenario,
        "request": normalized_request,
        "classification": classification,
        "orchestrator": dict(ORCHESTRATOR),
        "delegation_limit": len(SPECIALIST_AGENTS),
        "selected_specialists": specialists,
        "deferred_specialists": deferred,
        "approval_reasons": approvals,
        "agent_outputs": agent_outputs,
        "demo_steps": [
            "Receive the operator request.",
            "Classify risk and choose specialists.",
            "Retrieve evidence and plan bounded actions.",
            "Pause for approval when the policy guard requires it.",
            "Produce an operator-ready and audit-ready summary.",
        ],
        "final_summary": final_summary,
    }


def build_microsoft_scaffold(controller: dict[str, Any]) -> dict[str, Any]:
    specialists = controller.get("selected_specialists", [])
    role_map = [
        {
            "agent_id": ORCHESTRATOR["agent_id"],
            "display_name": ORCHESTRATOR["display_name"],
            "microsoft_surface": ORCHESTRATOR["microsoft_surface"],
        }
    ]
    for item in specialists:
        role_map.append(
            {
                "agent_id": str(item.get("agent_id", "")),
                "display_name": str(item.get("display_name", "")),
                "microsoft_surface": str(item.get("microsoft_surface", "")),
            }
        )

    return {
        "reference_template": "CCBS365 basic custom engine agent template",
        "work_tenant_required": True,
        "local_limitations": [
            "A real Copilot Studio build still needs a work tenant, developer environment access, and credits.",
            "Power Platform CLI is not installed in this environment, so local packaging and deployment are not ready yet.",
            "This repo can build and validate the orchestration design now, then project it into Microsoft surfaces later.",
        ],
        "recommended_components": [
            "Copilot Studio orchestrator agent for intake and delegation.",
            "Power Automate approval flow for risky actions.",
            "Dataverse or SharePoint knowledge storage for evidence and runbooks.",
            "Teams notification flow for stakeholder updates.",
            "Optional Microsoft 365 Agents app path for Teams-hosted experience.",
        ],
        "implementation_order": [
            "Stand up the orchestrator agent and intake topic.",
            "Map specialist roles to topics, plugins, or flows.",
            "Add approval checkpoints before any mutating action.",
            "Connect knowledge and evidence sources.",
            "Add Teams or email notification handoff.",
            "Test the governed incident-triage scenario end to end.",
        ],
        "role_mapping": role_map,
    }


def build_entry_draft(
    controller: dict[str, Any],
    *,
    company_name: str = "[Your Company or Organization]",
    team_name: str = "CCBS Team",
    cohort: str = DEFAULT_COHORT,
    copilot_studio_access: str = DEFAULT_COPILOT_STUDIO_ACCESS,
    region: str = DEFAULT_REGION,
    team_type: str = DEFAULT_TEAM_TYPE,
    experience_level: str = DEFAULT_EXPERIENCE_LEVEL,
) -> dict[str, Any]:
    scenario = dict(controller.get("scenario", {}))
    final_summary = str(controller.get("final_summary", "")).strip()
    return {
        "question_2_month": cohort,
        "question_3_company_or_organization": company_name,
        "question_4_copilot_studio_access": copilot_studio_access,
        "question_5_brief_description": (
            "CCBS is a multi-agent operations prototype where one orchestration agent can delegate work to up to 10 "
            "specialist agents. For the governed incident-triage scenario, the orchestrator routes the request to "
            "specialists for classification, policy review, evidence retrieval, bounded planning, approvals, execution "
            "support, and reporting so the team gets one controlled, auditable result instead of disconnected agent output."
        ),
        "question_6_primary_goal": (
            "Our goal is to leave the event with a working Microsoft-oriented prototype for governed technical operations: "
            "request intake, specialist delegation, human approval gates, bounded task execution, and evidence-backed "
            "reporting for a real business workflow."
        ),
        "question_7_region": region,
        "question_8_team_type": team_type,
        "question_9_experience": experience_level,
        "team_name": team_name,
        "scenario_title": scenario.get("title", DEFAULT_SCENARIO_ID),
        "positioning_summary": final_summary,
        "personal_fields_note": (
            "Questions 10 through 19 still need real names and work email addresses; do not use placeholders there."
        ),
    }


def _entry_markdown(entry: dict[str, Any]) -> str:
    lines = [
        "# CCBS Build-A-Thon Entry Draft",
        "",
        "Use real names and work emails for the personal fields before submitting.",
        "",
        f"2. Which month will your team participate in?  ",
        f"{entry['question_2_month']}",
        "",
        f"3. Company or Organization Name  ",
        f"{entry['question_3_company_or_organization']}",
        "",
        f"4. Does your team have access to Copilot Studio developer environment in your work tenant?  ",
        f"{entry['question_4_copilot_studio_access']}",
        "",
        f"5. Briefly describe your team's agentic prototype  ",
        f"{entry['question_5_brief_description']}",
        "",
        f"6. What is your team's primary goal for participating?  ",
        f"{entry['question_6_primary_goal']}",
        "",
        f"7. What region are you joining us from?  ",
        f"{entry['question_7_region']}",
        "",
        f"8. What describes your team the best?  ",
        f"{entry['question_8_team_type']}",
        "",
        f"9. What best describes the level of experience of your team with Power Platform or Copilot Studio or Agent Building?  ",
        f"{entry['question_9_experience']}",
        "",
        "Questions 10-19:",
        entry["personal_fields_note"],
    ]
    return "\n".join(lines) + "\n"


def write_buildathon_bundle(
    output_dir: Path,
    controller: dict[str, Any],
    *,
    company_name: str,
    team_name: str,
    cohort: str,
    copilot_studio_access: str,
    region: str,
    team_type: str,
    experience_level: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scaffold = build_microsoft_scaffold(controller)
    entry = build_entry_draft(
        controller,
        company_name=company_name,
        team_name=team_name,
        cohort=cohort,
        copilot_studio_access=copilot_studio_access,
        region=region,
        team_type=team_type,
        experience_level=experience_level,
    )

    controller_path = output_dir / "controller_run.json"
    scaffold_path = output_dir / "microsoft_scaffold.json"
    entry_path = output_dir / "entry_draft.md"

    controller_path.write_text(json.dumps(controller, indent=2), encoding="utf-8")
    scaffold_path.write_text(json.dumps(scaffold, indent=2), encoding="utf-8")
    entry_path.write_text(_entry_markdown(entry), encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "files": [str(controller_path), str(scaffold_path), str(entry_path)],
    }


def _cmd_buildathon_roles(args: argparse.Namespace) -> int:
    payload = list_specialist_agents()
    if args.json:
        _print_json(payload)
        return 0

    print(f"Orchestrator: {payload['orchestrator']['display_name']}")
    print(f"Delegation limit: {payload['delegation_limit']} specialist agents")
    print("")
    print("Specialists:")
    for item in payload["specialists"]:
        mode = "default" if bool(item.get("enabled_by_default", False)) else "conditional"
        print(f"- {item['display_name']} [{mode}] :: {item['purpose']}")
    return 0


def _cmd_buildathon_run(args: argparse.Namespace) -> int:
    try:
        request = _normalize_text(args.request or "")
        if not request:
            request = str(SCENARIOS[args.scenario_id]["default_request"])
        payload = run_local_buildathon_controller(
            request=request,
            scenario_id=str(args.scenario_id),
            max_specialists=max(1, int(args.max_specialists)),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    scenario = payload["scenario"]
    print(f"Scenario: {scenario['title']}")
    print(f"Request: {payload['request']}")
    print(f"Risk: {payload['classification']['risk_level']} | Type: {payload['classification']['request_type']}")
    print(f"Delegation: 1 orchestrator + {len(payload['selected_specialists'])} specialist agent(s)")
    if payload["approval_reasons"]:
        print("Approvals:")
        for item in payload["approval_reasons"]:
            print(f"- {item}")
    print("")
    print("Agent outputs:")
    for item in payload["agent_outputs"]:
        print(f"- {item['display_name']}: {item['output']}")
    print("")
    print(payload["final_summary"])
    return 0


def _cmd_buildathon_scaffold(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        request = _normalize_text(args.request or "")
        if not request:
            request = str(SCENARIOS[args.scenario_id]["default_request"])
        controller = run_local_buildathon_controller(
            request=request,
            scenario_id=str(args.scenario_id),
            max_specialists=max(1, int(args.max_specialists)),
        )
        output_dir = (root / Path(args.output_dir)).resolve()
        payload = write_buildathon_bundle(
            output_dir,
            controller,
            company_name=str(args.company_name),
            team_name=str(args.team_name),
            cohort=str(args.cohort),
            copilot_studio_access=str(args.copilot_studio_access),
            region=str(args.region),
            team_type=str(args.team_type),
            experience_level=str(args.experience_level),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
    else:
        print(f"Bundle written: {payload['output_dir']}")
        for item in payload["files"]:
            print(f"- {item}")
    return 0


def _cmd_buildathon_entry_draft(args: argparse.Namespace) -> int:
    try:
        request = _normalize_text(args.request or "")
        if not request:
            request = str(SCENARIOS[args.scenario_id]["default_request"])
        controller = run_local_buildathon_controller(
            request=request,
            scenario_id=str(args.scenario_id),
            max_specialists=max(1, int(args.max_specialists)),
        )
        entry = build_entry_draft(
            controller,
            company_name=str(args.company_name),
            team_name=str(args.team_name),
            cohort=str(args.cohort),
            copilot_studio_access=str(args.copilot_studio_access),
            region=str(args.region),
            team_type=str(args.team_type),
            experience_level=str(args.experience_level),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(entry)
    else:
        print(_entry_markdown(entry).rstrip())
    return 0


def add_buildathon_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    buildathon = sub.add_parser(
        "buildathon",
        help="Local multi-agent build-a-thon prototype, Microsoft scaffold, and entry draft helpers",
    )
    buildathon_sub = buildathon.add_subparsers(dest="buildathon_cmd", required=True)

    roles = buildathon_sub.add_parser("roles", help="List the orchestrator and specialist-agent catalog")
    roles.add_argument("--json", action="store_true", help="Emit JSON output")
    roles.set_defaults(func=_cmd_buildathon_roles)

    run = buildathon_sub.add_parser("run", help="Run the local deterministic multi-agent controller")
    run.add_argument("--scenario-id", default=DEFAULT_SCENARIO_ID, choices=sorted(SCENARIOS.keys()))
    run.add_argument("--request", default="", help="Override the scenario's default request")
    run.add_argument("--max-specialists", type=int, default=5, help="Maximum active specialist agents (1-10)")
    run.add_argument("--json", action="store_true", help="Emit JSON output")
    run.set_defaults(func=_cmd_buildathon_run)

    scaffold = buildathon_sub.add_parser("scaffold", help="Write a Microsoft handoff bundle for the current scenario")
    scaffold.add_argument("--scenario-id", default=DEFAULT_SCENARIO_ID, choices=sorted(SCENARIOS.keys()))
    scaffold.add_argument("--request", default="", help="Override the scenario's default request")
    scaffold.add_argument("--max-specialists", type=int, default=5, help="Maximum active specialist agents (1-10)")
    scaffold.add_argument("--output-dir", default="dist/buildathon/governed-ops-incident", help="Relative output directory")
    scaffold.add_argument("--company-name", default="[Your Company or Organization]")
    scaffold.add_argument("--team-name", default="CCBS Team")
    scaffold.add_argument("--cohort", default=DEFAULT_COHORT)
    scaffold.add_argument("--copilot-studio-access", default=DEFAULT_COPILOT_STUDIO_ACCESS)
    scaffold.add_argument("--region", default=DEFAULT_REGION)
    scaffold.add_argument("--team-type", default=DEFAULT_TEAM_TYPE)
    scaffold.add_argument("--experience-level", default=DEFAULT_EXPERIENCE_LEVEL)
    scaffold.add_argument("--json", action="store_true", help="Emit JSON output")
    scaffold.set_defaults(func=_cmd_buildathon_scaffold)

    entry = buildathon_sub.add_parser("entry-draft", help="Print paste-ready build-a-thon form answers")
    entry.add_argument("--scenario-id", default=DEFAULT_SCENARIO_ID, choices=sorted(SCENARIOS.keys()))
    entry.add_argument("--request", default="", help="Override the scenario's default request")
    entry.add_argument("--max-specialists", type=int, default=5, help="Maximum active specialist agents (1-10)")
    entry.add_argument("--company-name", default="[Your Company or Organization]")
    entry.add_argument("--team-name", default="CCBS Team")
    entry.add_argument("--cohort", default=DEFAULT_COHORT)
    entry.add_argument("--copilot-studio-access", default=DEFAULT_COPILOT_STUDIO_ACCESS)
    entry.add_argument("--region", default=DEFAULT_REGION)
    entry.add_argument("--team-type", default=DEFAULT_TEAM_TYPE)
    entry.add_argument("--experience-level", default=DEFAULT_EXPERIENCE_LEVEL)
    entry.add_argument("--json", action="store_true", help="Emit JSON output")
    entry.set_defaults(func=_cmd_buildathon_entry_draft)