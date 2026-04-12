"""CLI surface for ai3 runtime rollout commands (ccbs ai3 ...)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..repo import RepoError, repo_root
from .checkpoint import get_checkpoint, list_checkpoints
from .db import connect_runtime, runtime_db_path
from .mcp.approvals import approve_tool_call, reject_tool_call
from .mcp.registry import seed_mcp_registry
from .migrations import migrate_runtime
from .orchestrator import (
    create_message,
    create_run,
    create_thread,
    ensure_endpoint,
    execute_run,
    list_run_artifacts,
    list_run_citations,
    list_run_steps,
    resume_run,
    retrieve_chunks,
)
from .retrieval.citation_verify import verify_run_citations
from .retrieval.ccbs_seed import (
    DEFAULT_PACKAGE_ID as CCBS_DEFAULT_PACKAGE_ID,
    DEFAULT_PACKAGE_RELPATH as CCBS_DEFAULT_PACKAGE_RELPATH,
    DEFAULT_SOURCE_ID as CCBS_DEFAULT_SOURCE_ID,
    upsert_catalog_ccbs_package,
    write_ccbs_seed_package,
)
from .retrieval.vault_catalog import catalog_doctor, index_catalog, load_catalog, resolve_runtime_vault_root, sync_catalog
from .retrieval.zip_ingest import index_zip_archive
from .retrieval.zip_manifest import sync_zip_manifest


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def _resolve_path(root: Path, raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _parse_tool_calls(values: list[str] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in values or []:
        value = json.loads(str(raw))
        if not isinstance(value, dict):
            raise ValueError("tool-call JSON must be an object")
        tool_name = str(value.get("tool_name", "")).strip()
        if not tool_name:
            raise ValueError("tool-call JSON requires tool_name")
        args = value.get("arguments", {})
        if not isinstance(args, dict):
            raise ValueError("tool-call arguments must be an object")
        out.append({"tool_name": tool_name, "arguments": args})
    return out


def _cmd_db_migrate(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        out = migrate_runtime(root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "db_path": out.get("db_path", str(runtime_db_path(root))),
        "version": out.get("version", 0),
        "applied": out.get("applied", []),
    }
    if args.json:
        _print_json(payload)
    else:
        print(f"ai3 runtime db: {payload['db_path']}")
        print(f"schema version: {payload['version']}")
        if payload["applied"]:
            print(f"applied migrations: {payload['applied']}")
    return 0


def _cmd_thread_create(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        thread = create_thread(
            conn,
            title=str(args.title or "").strip(),
            tags=[str(item).strip() for item in args.tag or [] if str(item).strip()],
            metadata=_parse_json_object(args.metadata_json),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json({"thread": thread})
    else:
        print(f"thread created: {thread['thread_id']}")
    return 0


def _run_create_common(args: argparse.Namespace, root: Path, conn: Any) -> dict[str, Any]:
    seed_mcp_registry(conn)
    if str(args.question or "").strip():
        create_message(conn, thread_id=args.thread_id, role="user", content=" ".join(args.question).strip())

    endpoint_id = str(args.endpoint_id or "").strip()
    if not endpoint_id:
        endpoint_id = ensure_endpoint(
            conn,
            provider=str(args.provider or "ollama"),
            base_url=str(args.base_url or ""),
            chat_model=str(args.model or ""),
            endpoint_id=str(args.new_endpoint_id or ""),
        )

    metadata = _parse_json_object(args.metadata_json)
    if str(args.question or "").strip():
        metadata["question"] = " ".join(args.question).strip()
    metadata.setdefault("top_k", max(1, int(args.top_k)))
    metadata.setdefault("offline_only", bool(args.offline_only))
    metadata.setdefault("strict_local_models", True)
    metadata.setdefault("allow_extractive_fallback", False)
    metadata.setdefault("local_attempts_max", max(1, int(args.local_attempts_max)))
    metadata.setdefault("codex_model", str(args.codex_model))
    metadata.setdefault("codex_base_url", str(args.codex_base_url))
    metadata.setdefault("timeout_s", max(3, int(args.timeout_s)))
    metadata.setdefault("dual_write", bool(args.dual_write))
    metadata.setdefault("tool_calls", _parse_tool_calls(args.tool_call_json))

    run = create_run(conn, thread_id=args.thread_id, endpoint_id=endpoint_id, metadata=metadata)
    if bool(args.execute):
        return execute_run(
            root=root,
            conn=conn,
            run_id=str(run["run_id"]),
            actor="cli",
            allow_remote=bool(args.allow_remote),
        )
    return {"run": run, "steps": [], "citations": [], "artifacts": []}


def _cmd_run_create(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        out = _run_create_common(args, root=root, conn=conn)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
        return 0

    run = out.get("run", {})
    print(f"run: {run.get('run_id')} status={run.get('status')}")
    if out.get("requires_action"):
        print("requires action: approve pending tool calls before resume")
    taskmaster = out.get("taskmaster", {})
    if isinstance(taskmaster, dict) and str(taskmaster.get("answer", "")).strip():
        print("")
        print(str(taskmaster.get("answer", "")))
    return 0


def _cmd_run_resume(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        out = resume_run(root=root, conn=conn, run_id=args.run_id, actor="cli", allow_remote=bool(args.allow_remote))
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
        return 0

    run = out.get("run", {})
    print(f"run: {run.get('run_id')} status={run.get('status')}")
    return 0


def _cmd_tool_approve(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        if args.reject:
            approval = reject_tool_call(conn, tool_call_id=args.tool_call_id, approved_by="cli", rationale=args.rationale)
        else:
            approval = approve_tool_call(conn, tool_call_id=args.tool_call_id, approved_by="cli", rationale=args.rationale)

        payload: dict[str, Any] = {"approval": approval}
        row = conn.execute("SELECT run_id FROM tool_call WHERE tool_call_id = ?", (args.tool_call_id,)).fetchone()
        run_id = str(row["run_id"] or "") if row else ""
        payload["run_id"] = run_id

        if not args.reject and args.resume and run_id:
            resumed = resume_run(root=root, conn=conn, run_id=run_id, actor="cli", allow_remote=bool(args.allow_remote))
            payload["run"] = resumed.get("run")
            payload["steps"] = resumed.get("steps", [])
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(payload)
    else:
        print(f"approval decision: {payload['approval']['decision']}")
        run = payload.get("run")
        if isinstance(run, dict):
            print(f"run: {run.get('run_id')} status={run.get('status')}")
    return 0


def _cmd_vault_sync(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        zip_path = _resolve_path(root, args.zip_path)
        out = sync_zip_manifest(conn, zip_path=zip_path)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
    else:
        print(f"zip synced: {out['zip_id']} entries={out['entries']}")
    return 0


def _cmd_vault_index(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)

        if args.zip_id:
            row = conn.execute("SELECT zip_id, path FROM zip_archive WHERE zip_id = ?", (args.zip_id,)).fetchone()
            if row is None:
                raise ValueError(f"zip_id not found: {args.zip_id}")
            zip_id = str(row["zip_id"])
            zip_path = Path(str(row["path"]))
        else:
            zip_path = _resolve_path(root, args.zip_path)
            synced = sync_zip_manifest(conn, zip_path=zip_path)
            zip_id = str(synced["zip_id"])

        out = index_zip_archive(
            conn,
            zip_id=zip_id,
            zip_path=zip_path,
            max_entries=max(1, int(args.max_entries)),
            only_pending=not bool(args.full),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
    else:
        print(f"zip indexed: {out['zip_id']} docs={out['docs_indexed']} chunks={out['chunks_indexed']}")
    return 0


def _cmd_vault_catalog_validate(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        catalog_path = _resolve_path(root, args.path)
        catalog = load_catalog(catalog_path)
        serializable = {
            "ok": True,
            "catalog": {
                "version": int(catalog.get("version", 0)),
                "catalog_path": str(catalog.get("catalog_path", "")),
                "vault_root": str(catalog.get("vault_root", "")),
                "allowlist_roots": [str(item) for item in catalog.get("allowlist_roots", [])],
                "runtime": {
                    "use_fallback_when_missing": bool(dict(catalog.get("runtime", {})).get("use_fallback_when_missing", True)),
                    "fallback_vault_root": str(dict(catalog.get("runtime", {})).get("fallback_vault_root", "")),
                },
                "source_count": len(catalog.get("sources", [])),
                "package_count": len(catalog.get("packages", [])),
            },
        }
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(serializable)
    else:
        print(f"catalog valid: {serializable['catalog']['catalog_path']}")
        print(f"sources={serializable['catalog']['source_count']} packages={serializable['catalog']['package_count']}")
    return 0


def _cmd_vault_doctor(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        catalog_path = _resolve_path(root, args.path)
        catalog = load_catalog(catalog_path)
        out = catalog_doctor(
            catalog,
            source_id=str(args.source_id or ""),
            package_id=str(args.package_id or ""),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(out)
    else:
        runtime = dict(out.get("runtime", {}))
        print(f"vault runtime root: {runtime.get('resolved_vault_root', '')}")
        if bool(runtime.get("fallback_used", False)):
            print("fallback root is active (configured vault root missing).")
        print(f"active packages checked: {out.get('active_selected', 0)}")
        print(f"missing packages: {len(out.get('missing_packages', []))}")
    return 0 if bool(out.get("ok", False)) else 1


def _cmd_vault_seed_ccbs(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        catalog_path = _resolve_path(root, args.path)
        catalog = load_catalog(catalog_path)
        runtime = resolve_runtime_vault_root(catalog)
        runtime_root = Path(str(runtime.get("resolved_vault_root", ""))).expanduser().resolve()
        source_id = str(args.source_id or CCBS_DEFAULT_SOURCE_ID).strip() or CCBS_DEFAULT_SOURCE_ID
        package_id = str(args.package_id or CCBS_DEFAULT_PACKAGE_ID).strip() or CCBS_DEFAULT_PACKAGE_ID

        out = write_ccbs_seed_package(
            repo_root=root,
            vault_root=runtime_root,
            package_relpath=CCBS_DEFAULT_PACKAGE_RELPATH,
            include_untracked=bool(args.include_untracked),
            dry_run=bool(args.dry_run),
        )
        out["runtime"] = runtime
        out["source_id"] = source_id
        out["package_id"] = package_id
        out["catalog_path"] = str(catalog_path)

        if bool(args.write_catalog) and not bool(args.dry_run):
            out["catalog_update"] = upsert_catalog_ccbs_package(
                catalog_path=catalog_path,
                source_id=source_id,
                package_id=package_id,
                zip_relpath=CCBS_DEFAULT_PACKAGE_RELPATH,
            )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(out)
    else:
        counts = dict(out.get("manifest", {}).get("counts", {}))
        print(f"CCBS seed selected={counts.get('selected', 0)} text={counts.get('text', 0)} binary={counts.get('binary_metadata_only', 0)}")
        print(f"seed zip: {out.get('zip_path', '')}")
        if bool(args.dry_run):
            print("dry-run only (no writes performed)")
        elif out.get("catalog_update"):
            print(f"catalog updated: {out.get('catalog_path', '')}")
    return 0


def _cmd_vault_sync_catalog(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        catalog_path = _resolve_path(root, args.path)
        out = sync_catalog(
            conn,
            catalog_path=catalog_path,
            source_id=str(args.source_id or ""),
            package_id=str(args.package_id or ""),
            full_hash=bool(args.full_hash),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
    else:
        print(
            "vault sync-catalog: "
            f"selected={out.get('selected_packages', 0)} synced={len(out.get('synced', []))} errors={len(out.get('errors', []))}"
        )
    return 0


def _cmd_vault_index_catalog(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        catalog_path = _resolve_path(root, args.path)
        out = index_catalog(
            conn,
            catalog_path=catalog_path,
            source_id=str(args.source_id or ""),
            package_id=str(args.package_id or ""),
            full=bool(args.full),
            full_hash=bool(args.full_hash),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
    else:
        print(
            "vault index-catalog: "
            f"indexed={len(out.get('indexed', []))} errors={len(out.get('errors', []))} full={bool(out.get('full_reindex', False))}"
        )
    return 0


def _cmd_vault_list(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        source_id = str(args.source_id or "").strip()
        active_only = bool(args.active_only)
        rows = conn.execute(
            """
            SELECT zip_id, source_id, package_id, path, sha256, active, size_bytes, last_scanned_at
            FROM zip_archive
            WHERE (? = '' OR source_id = ?)
              AND (? = 0 OR active = 1)
            ORDER BY source_id, package_id, path
            """,
            (source_id, source_id, 1 if active_only else 0),
        ).fetchall()
        out = {
            "filters": {"source_id": source_id, "active_only": active_only},
            "count": len(rows),
            "items": [
                {
                    "zip_id": str(row["zip_id"]),
                    "source_id": str(row["source_id"] or ""),
                    "package_id": str(row["package_id"] or ""),
                    "path": str(row["path"] or ""),
                    "sha256": str(row["sha256"] or ""),
                    "active": bool(int(row["active"] or 0)),
                    "size_bytes": int(row["size_bytes"] or 0),
                    "last_scanned_at": str(row["last_scanned_at"] or ""),
                }
                for row in rows
            ],
        }
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
    else:
        print(f"vault archives: {out['count']}")
        for item in out["items"][:20]:
            print(f"- {item['source_id']} {item['package_id']} {item['zip_id']} {item['path']}")
    return 0


def _cmd_vault_verify_citations(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        run_id = str(args.run_id or "").strip()
        if bool(args.latest):
            row = conn.execute("SELECT run_id FROM citation ORDER BY rowid DESC LIMIT 1").fetchone()
            if row is None:
                raise ValueError("no citations found in runtime database")
            run_id = str(row["run_id"])
        out = verify_run_citations(conn, run_id=run_id, strict=bool(args.strict))
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
    else:
        print(f"citation verify run={out['run_id']} verified={out['verified']} failed={out['failed']}")
    if bool(args.strict) and int(out.get("failed", 0)) > 0:
        return 1
    return 0


def _cmd_vault_reset_parse(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        package_id = str(args.package_id or "").strip()
        source_id = str(args.source_id or "").strip()
        if not package_id and not source_id:
            raise ValueError("set --package-id or --source-id")

        query = """
            UPDATE zip_entry
            SET parse_status = 'pending',
                parse_error = '',
                text_extracted = 0
            WHERE entry_id IN (
                SELECT ze.entry_id
                FROM zip_entry ze
                JOIN zip_archive za ON za.zip_id = ze.zip_id
                WHERE (? = '' OR ze.package_id = ?)
                  AND (? = '' OR za.source_id = ?)
            )
        """
        conn.execute(query, (package_id, package_id, source_id, source_id))
        affected = int(conn.execute("SELECT changes()").fetchone()[0])
        conn.commit()
        out = {"package_id": package_id, "source_id": source_id, "reset_entries": affected}
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
    else:
        print(f"vault parse status reset: {out['reset_entries']}")
    return 0


def _cmd_retrieve(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        query = " ".join(args.query).strip()
        out = retrieve_chunks(conn, query=query, top_k=max(1, int(args.top_k)))
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(out)
        return 0

    print(f"query: {out.get('query', '')}")
    for item in out.get("hits", []):
        print(f"- rank={item.get('rank')} score={item.get('score'):.4f} {item.get('source_uri')}")
        snippet = str(item.get("snippet", "")).strip().replace("\n", " ")
        if snippet:
            print(f"  {snippet[:180]}")
    return 0


def _cmd_checkpoint_list(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        rows = list_checkpoints(conn, run_id=str(args.run_id or ""), limit=max(1, int(args.limit)))
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    payload = {"checkpoints": rows}
    if args.json:
        _print_json(payload)
        return 0

    print(f"checkpoints: {len(rows)}")
    for row in rows:
        print(f"- {row['checkpoint_id']} run={row['run_id']} step={row['step_id']} at={row['created_at']}")
    return 0


def _cmd_checkpoint_replay(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        checkpoint = get_checkpoint(conn, checkpoint_id=args.checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"checkpoint not found: {args.checkpoint_id}")

        payload: dict[str, Any] = {"checkpoint": checkpoint}
        if args.resume:
            resumed = resume_run(root=root, conn=conn, run_id=str(checkpoint["run_id"]), actor="cli", allow_remote=bool(args.allow_remote))
            payload["run"] = resumed.get("run")
            payload["steps"] = resumed.get("steps", [])
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(payload)
    else:
        chk = payload["checkpoint"]
        print(f"checkpoint: {chk['checkpoint_id']} run={chk['run_id']} step={chk['step_id']}")
        run = payload.get("run")
        if isinstance(run, dict):
            print(f"run resumed: {run.get('run_id')} status={run.get('status')}")
    return 0


def _cmd_run_show(args: argparse.Namespace) -> int:
    conn = None
    try:
        root = repo_root()
        conn = connect_runtime(root)
        run = conn.execute(
            "SELECT run_id, thread_id, endpoint_id, status, started_at, completed_at, error, trace_id, metadata_json FROM run WHERE run_id = ?",
            (args.run_id,),
        ).fetchone()
        if run is None:
            raise ValueError(f"run not found: {args.run_id}")
        payload = {
            "run": {
                "run_id": str(run["run_id"]),
                "thread_id": str(run["thread_id"]),
                "endpoint_id": str(run["endpoint_id"]),
                "status": str(run["status"]),
                "started_at": str(run["started_at"] or ""),
                "completed_at": str(run["completed_at"] or ""),
                "error": str(run["error"] or ""),
                "trace_id": str(run["trace_id"] or ""),
                "metadata": json.loads(str(run["metadata_json"] or "{}")),
            },
            "steps": list_run_steps(conn, args.run_id),
            "citations": list_run_citations(conn, args.run_id),
            "artifacts": list_run_artifacts(conn, args.run_id),
        }
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    finally:
        if conn is not None:
            conn.close()

    if args.json:
        _print_json(payload)
        return 0

    run_row = payload["run"]
    print(f"run: {run_row['run_id']} status={run_row['status']}")
    print(f"steps: {len(payload['steps'])} citations: {len(payload['citations'])} artifacts: {len(payload['artifacts'])}")
    return 0


def add_ai3_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    ai3 = subparsers.add_parser("ai3", help="SPEC-2 ai3 runtime commands")
    ai3_sub = ai3.add_subparsers(dest="ai3_cmd", required=True)

    db_parser = ai3_sub.add_parser("db", help="ai3 runtime database operations")
    db_sub = db_parser.add_subparsers(dest="ai3_db_cmd", required=True)
    db_migrate = db_sub.add_parser("migrate", help="Apply ai3 schema migrations")
    db_migrate.add_argument("--json", action="store_true", help="Emit JSON output")
    db_migrate.set_defaults(func=_cmd_db_migrate)

    thread_parser = ai3_sub.add_parser("thread", help="ai3 thread operations")
    thread_sub = thread_parser.add_subparsers(dest="ai3_thread_cmd", required=True)
    thread_create = thread_sub.add_parser("create", help="Create thread")
    thread_create.add_argument("--title", default="", help="Thread title")
    thread_create.add_argument("--tag", action="append", default=[], help="Thread tag (repeatable)")
    thread_create.add_argument("--metadata-json", default="{}", help="Thread metadata JSON")
    thread_create.add_argument("--json", action="store_true", help="Emit JSON output")
    thread_create.set_defaults(func=_cmd_thread_create)

    run_parser = ai3_sub.add_parser("run", help="ai3 run operations")
    run_sub = run_parser.add_subparsers(dest="ai3_run_cmd", required=True)

    run_create = run_sub.add_parser("create", help="Create run and optionally execute")
    run_create.add_argument("--thread-id", required=True, help="Target thread id")
    run_create.add_argument("question", nargs="*", help="Optional user question; inserted as user message")
    run_create.add_argument("--endpoint-id", default="", help="Existing endpoint id")
    run_create.add_argument("--new-endpoint-id", default="", help="New endpoint id override")
    run_create.add_argument("--provider", choices=("ollama", "lmstudio", "codex"), default="ollama", help="Endpoint provider")
    run_create.add_argument("--base-url", default="", help="Endpoint base URL")
    run_create.add_argument("--model", default="", help="Endpoint chat model")
    run_create.add_argument("--top-k", type=int, default=5, help="Retriever top-k")
    run_create.add_argument("--local-attempts-max", type=int, default=3, help="Local attempt count before remote fallback")
    run_create.add_argument("--offline-only", action="store_true", help="Do not escalate to remote")
    run_create.add_argument("--allow-remote", action="store_true", help="Allow remote attempt when routing policy allows")
    run_create.add_argument("--dual-write", dest="dual_write", action="store_true", help="Mirror ai3 result into ai2 audit/memory (default)")
    run_create.add_argument("--no-dual-write", dest="dual_write", action="store_false", help="Disable ai2 dual-write for this run")
    run_create.add_argument("--codex-model", default="gpt-5", help="Remote codex model")
    run_create.add_argument("--codex-base-url", default="https://api.openai.com/v1", help="Remote codex base URL")
    run_create.add_argument("--timeout-s", type=int, default=40, help="Provider timeout")
    run_create.add_argument("--metadata-json", default="{}", help="Additional run metadata")
    run_create.add_argument("--tool-call-json", action="append", default=[], help='Tool call object: {"tool_name":"...","arguments":{...}}')
    run_create.add_argument("--execute", dest="execute", action="store_true", help="Execute run immediately (default)")
    run_create.add_argument("--no-execute", dest="execute", action="store_false", help="Create queued run only")
    run_create.add_argument("--json", action="store_true", help="Emit JSON output")
    run_create.set_defaults(func=_cmd_run_create, execute=True, dual_write=True, allow_remote=False)

    run_resume = run_sub.add_parser("resume", help="Resume paused/requires_action run")
    run_resume.add_argument("run_id", help="Run id")
    run_resume.add_argument("--allow-remote", action="store_true", help="Allow remote attempt when resuming")
    run_resume.add_argument("--json", action="store_true", help="Emit JSON output")
    run_resume.set_defaults(func=_cmd_run_resume)

    run_show = run_sub.add_parser("show", help="Show run state, steps, citations, and artifacts")
    run_show.add_argument("run_id", help="Run id")
    run_show.add_argument("--json", action="store_true", help="Emit JSON output")
    run_show.set_defaults(func=_cmd_run_show)

    tool_parser = ai3_sub.add_parser("tool", help="Tool approval flow")
    tool_sub = tool_parser.add_subparsers(dest="ai3_tool_cmd", required=True)
    tool_approve = tool_sub.add_parser("approve", help="Approve/reject one tool call")
    tool_approve.add_argument("tool_call_id", help="Tool call id")
    tool_approve.add_argument("--reject", action="store_true", help="Reject instead of approve")
    tool_approve.add_argument("--rationale", default="", help="Decision rationale")
    tool_approve.add_argument("--resume", action="store_true", help="Resume parent run after approval")
    tool_approve.add_argument("--allow-remote", action="store_true", help="Allow remote attempt during resume")
    tool_approve.add_argument("--json", action="store_true", help="Emit JSON output")
    tool_approve.set_defaults(func=_cmd_tool_approve)

    vault_parser = ai3_sub.add_parser("vault", help="ZIP vault manifest/index operations")
    vault_sub = vault_parser.add_subparsers(dest="ai3_vault_cmd", required=True)
    vault_catalog = vault_sub.add_parser("catalog", help="Vault catalog operations")
    vault_catalog_sub = vault_catalog.add_subparsers(dest="ai3_vault_catalog_cmd", required=True)
    vault_catalog_validate = vault_catalog_sub.add_parser("validate", help="Validate vault catalog JSON")
    vault_catalog_validate.add_argument("--path", default="config/offline-vault.catalog.json", help="Vault catalog path")
    vault_catalog_validate.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_catalog_validate.set_defaults(func=_cmd_vault_catalog_validate)

    vault_doctor = vault_sub.add_parser("doctor", help="Inspect vault runtime root and package presence")
    vault_doctor.add_argument("--path", default="config/offline-vault.catalog.json", help="Vault catalog path")
    vault_doctor.add_argument("--source-id", default="", help="Optional source filter")
    vault_doctor.add_argument("--package-id", default="", help="Optional package filter")
    vault_doctor.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_doctor.set_defaults(func=_cmd_vault_doctor)

    vault_sync = vault_sub.add_parser("sync", help="Sync ZIP manifest into runtime db")
    vault_sync.add_argument("zip_path", help="Zip file path")
    vault_sync.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_sync.set_defaults(func=_cmd_vault_sync)

    vault_index = vault_sub.add_parser("index", help="Index ZIP entries into document/chunk stores")
    vault_index.add_argument("--zip-id", default="", help="Existing zip_id from vault sync")
    vault_index.add_argument("--zip-path", default="", help="Zip path (used when --zip-id omitted)")
    vault_index.add_argument("--max-entries", type=int, default=20000, help="Max entries to process")
    vault_index.add_argument("--full", action="store_true", help="Reindex all text entries, not only pending")
    vault_index.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_index.set_defaults(func=_cmd_vault_index)

    vault_sync_catalog = vault_sub.add_parser("sync-catalog", help="Sync all matching active package zips from catalog")
    vault_sync_catalog.add_argument("--path", default="config/offline-vault.catalog.json", help="Vault catalog path")
    vault_sync_catalog.add_argument("--source-id", default="", help="Optional source filter")
    vault_sync_catalog.add_argument("--package-id", default="", help="Optional package filter")
    vault_sync_catalog.add_argument("--full-hash", action="store_true", help="Compute entry sha256 for each manifest row")
    vault_sync_catalog.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_sync_catalog.set_defaults(func=_cmd_vault_sync_catalog)

    vault_index_catalog = vault_sub.add_parser("index-catalog", help="Index all matching active package zips from catalog")
    vault_index_catalog.add_argument("--path", default="config/offline-vault.catalog.json", help="Vault catalog path")
    vault_index_catalog.add_argument("--source-id", default="", help="Optional source filter")
    vault_index_catalog.add_argument("--package-id", default="", help="Optional package filter")
    vault_index_catalog.add_argument("--full", action="store_true", help="Reindex all text entries, not only pending")
    vault_index_catalog.add_argument("--full-hash", action="store_true", help="Compute entry sha256 during sync stage")
    vault_index_catalog.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_index_catalog.set_defaults(func=_cmd_vault_index_catalog)

    vault_list = vault_sub.add_parser("list", help="List synced vault archives")
    vault_list.add_argument("--source-id", default="", help="Optional source filter")
    vault_list.add_argument("--active-only", action="store_true", help="Show only active archives")
    vault_list.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_list.set_defaults(func=_cmd_vault_list)

    vault_verify = vault_sub.add_parser("verify-citations", help="Verify citation integrity for one run")
    vault_verify.add_argument("--run-id", default="", help="Run id to verify")
    vault_verify.add_argument("--latest", action="store_true", help="Verify citations for most recent cited run")
    vault_verify.add_argument("--strict", action="store_true", help="Exit non-zero when any citation fails")
    vault_verify.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_verify.set_defaults(func=_cmd_vault_verify_citations)

    vault_reset_parse = vault_sub.add_parser("reset-parse-status", help="Reset parse status to pending for selected archive entries")
    vault_reset_parse.add_argument("--package-id", default="", help="Package id filter")
    vault_reset_parse.add_argument("--source-id", default="", help="Source id filter")
    vault_reset_parse.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_reset_parse.set_defaults(func=_cmd_vault_reset_parse)

    vault_seed_ccbs = vault_sub.add_parser("seed-ccbs", help="Create deterministic CCBS bootstrap package")
    vault_seed_ccbs.add_argument("--path", default="config/offline-vault.catalog.json", help="Vault catalog path")
    vault_seed_ccbs.add_argument("--source-id", default=CCBS_DEFAULT_SOURCE_ID, help="Source id for catalog package upsert")
    vault_seed_ccbs.add_argument("--package-id", default=CCBS_DEFAULT_PACKAGE_ID, help="Package id for catalog package upsert")
    vault_seed_ccbs.add_argument("--include-untracked", action="store_true", help="Include untracked git files in CCBS scan")
    vault_seed_ccbs.add_argument("--write-catalog", action="store_true", help="Update catalog package entry after zip write")
    vault_seed_ccbs.add_argument("--dry-run", action="store_true", help="Plan only; no zip/catalog writes")
    vault_seed_ccbs.add_argument("--json", action="store_true", help="Emit JSON output")
    vault_seed_ccbs.set_defaults(func=_cmd_vault_seed_ccbs)

    retrieve = ai3_sub.add_parser("retrieve", help="Run hybrid retrieval and show ranked hits")
    retrieve.add_argument("query", nargs="+", help="Retrieval query")
    retrieve.add_argument("--top-k", type=int, default=5, help="Top-k hits")
    retrieve.add_argument("--json", action="store_true", help="Emit JSON output")
    retrieve.set_defaults(func=_cmd_retrieve)

    checkpoint_parser = ai3_sub.add_parser("checkpoint", help="Checkpoint inspect/replay")
    checkpoint_sub = checkpoint_parser.add_subparsers(dest="ai3_checkpoint_cmd", required=True)
    checkpoint_list = checkpoint_sub.add_parser("list", help="List checkpoints")
    checkpoint_list.add_argument("--run-id", default="", help="Optional run id filter")
    checkpoint_list.add_argument("--limit", type=int, default=50, help="Maximum checkpoints")
    checkpoint_list.add_argument("--json", action="store_true", help="Emit JSON output")
    checkpoint_list.set_defaults(func=_cmd_checkpoint_list)

    checkpoint_replay = checkpoint_sub.add_parser("replay", help="Show checkpoint and optionally resume run")
    checkpoint_replay.add_argument("checkpoint_id", help="Checkpoint id")
    checkpoint_replay.add_argument("--resume", action="store_true", help="Resume run from stored run id")
    checkpoint_replay.add_argument("--allow-remote", action="store_true", help="Allow remote attempt when resuming")
    checkpoint_replay.add_argument("--json", action="store_true", help="Emit JSON output")
    checkpoint_replay.set_defaults(func=_cmd_checkpoint_replay)
