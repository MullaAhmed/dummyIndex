# monitor a folder and auto-trigger --update when files change
from __future__ import annotations
import json
import sys
import time
from pathlib import Path


from dummyindex.pipeline.detect import CODE_EXTENSIONS, DOC_EXTENSIONS, PAPER_EXTENSIONS, IMAGE_EXTENSIONS

_WATCHED_EXTENSIONS = CODE_EXTENSIONS | DOC_EXTENSIONS | PAPER_EXTENSIONS | IMAGE_EXTENSIONS
_CODE_EXTENSIONS = CODE_EXTENSIONS


def _report_root_label(watch_path: Path) -> str:
    if watch_path.is_absolute():
        return watch_path.name or str(watch_path)
    return Path.cwd().name if watch_path == Path(".") else str(watch_path)


def _relativize_source_files(payload: dict, root: Path) -> None:
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in payload.get(bucket, []):
            source = item.get("source_file")
            if not source:
                continue
            source_path = Path(source)
            if not source_path.is_absolute():
                continue
            try:
                item["source_file"] = str(source_path.resolve().relative_to(root))
            except ValueError:
                continue


def _rebuild_code(watch_path: Path, *, follow_symlinks: bool = False, skip_structure: bool = False) -> bool:
    """Re-run AST extraction + build + cluster + report for code files. No LLM needed.

    Returns True on success, False on error.
    """
    watch_root = watch_path.resolve()
    project_root = Path.cwd().resolve() if not watch_path.is_absolute() else watch_root
    report_root = _report_root_label(watch_path)
    try:
        from dummyindex.pipeline.extract import extract
        from dummyindex.pipeline.detect import detect
        from dummyindex.pipeline.build import build_from_json
        from dummyindex.analysis.cluster import cluster, score_all
        from dummyindex.analysis.analyze import god_nodes, surprising_connections, suggest_questions
        from dummyindex.analysis.report import generate
        from dummyindex.pipeline.export import to_json, to_html

        detected = detect(watch_path, follow_symlinks=follow_symlinks)
        code_files = [Path(f) for f in detected['files']['code']]

        if not code_files:
            print("[dummyindex watch] No code files found - nothing to rebuild.")
            return False

        result = extract(code_files, cache_root=watch_root)

        # Preserve semantic nodes/edges from a previous full run.
        # AST-only rebuild replaces code nodes; doc/paper/image nodes are kept.
        out = watch_path / "dummyindex-out"
        existing_graph = out / "graph.json"
        if existing_graph.exists():
            try:
                existing = json.loads(existing_graph.read_text(encoding="utf-8"))
                code_ids = {n["id"] for n in existing.get("nodes", []) if n.get("file_type") == "code"}
                sem_nodes = [n for n in existing.get("nodes", []) if n.get("file_type") != "code"]
                sem_edges = [e for e in existing.get("links", existing.get("edges", []))
                             if e.get("confidence") in ("INFERRED", "AMBIGUOUS")
                             or (e.get("source") not in code_ids and e.get("target") not in code_ids)]
                result = {
                    "nodes": result["nodes"] + sem_nodes,
                    "edges": result["edges"] + sem_edges,
                    "hyperedges": existing.get("hyperedges", []),
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            except Exception:
                pass  # corrupt graph.json - proceed with AST-only

        _relativize_source_files(result, project_root)

        detection = {
            "files": {"code": [str(f) for f in code_files], "document": [], "paper": [], "image": []},
            "total_files": len(code_files),
            "total_words": detected.get("total_words", 0),
        }

        G = build_from_json(result)
        communities = cluster(G)
        cohesion = score_all(G, communities)
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        labels = {cid: "Community " + str(cid) for cid in communities}
        questions = suggest_questions(G, communities, labels)

        out.mkdir(exist_ok=True)

        report = generate(G, communities, cohesion, labels, gods, surprises, detection,
                          {"input": 0, "output": 0}, report_root, suggested_questions=questions)
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        to_json(G, communities, str(out / "graph.json"))

        # to_html raises ValueError for graphs > MAX_NODES_FOR_VIZ (5000).
        # Wrap so core outputs (graph.json + GRAPH_REPORT.md) always land.
        html_written = False
        try:
            to_html(G, communities, str(out / "graph.html"), community_labels=labels or None)
            html_written = True
        except ValueError as viz_err:
            print(f"[dummyindex watch] Skipped graph.html: {viz_err}")
            stale = out / "graph.html"
            if stale.exists():
                stale.unlink()

        structure_written = False
        if not skip_structure:
            structure_written = _build_structure_artifacts(result, code_files, watch_path, out)

        flow_written = _build_flow_artifacts(G, gods, labels, out)
        feature_written = _build_feature_artifacts(G, communities, gods, labels, out)

        # clear stale needs_update flag if present
        flag = out / "needs_update"
        if flag.exists():
            flag.unlink()

        print(f"[dummyindex watch] Rebuilt: {G.number_of_nodes()} nodes, "
              f"{G.number_of_edges()} edges, {len(communities)} communities")
        products = ["graph.json"]
        if html_written:
            products.append("graph.html")
        products.append("GRAPH_REPORT.md")
        if structure_written:
            products.extend(["structure_graph.json", "structure_graph.html"])
        if flow_written:
            products.extend(["flow_graph.json", "flow_graph.html"])
        if feature_written:
            products.extend(["feature_graph.json", "feature_graph.html"])
        if len(products) > 1:
            products_text = ", ".join(products[:-1]) + f" and {products[-1]}"
        else:
            products_text = products[0]
        print(f"[dummyindex watch] {products_text} updated in {out}")
        return True

    except Exception as exc:
        print(f"[dummyindex watch] Rebuild failed: {exc}")
        return False


def _build_structure_artifacts(
    extraction: dict,
    code_files: list[Path],
    watch_path: Path,
    out_dir: Path,
) -> bool:
    """Build structure_graph.json and structure_graph.html.

    Runs independently of the legacy graph pipeline. Failures are logged but
    never disturb graph.json / graph.html / GRAPH_REPORT.md.
    """
    try:
        from dummyindex.pipeline.structure import build_structure
        from dummyindex.pipeline.export import to_structure_json, to_structure_html
    except Exception as exc:
        print(f"[dummyindex watch] Structure module unavailable: {exc}")
        return False

    try:
        structure = build_structure(extraction, code_files, watch_path)
    except Exception as exc:
        print(f"[dummyindex watch] Structure build failed: {exc}")
        return False

    try:
        to_structure_json(structure, str(out_dir / "structure_graph.json"))
    except Exception as exc:
        print(f"[dummyindex watch] structure_graph.json failed: {exc}")
        return False

    try:
        to_structure_html(structure, str(out_dir / "structure_graph.html"))
    except Exception as exc:
        print(f"[dummyindex watch] structure_graph.html failed: {exc}")
        stale = out_dir / "structure_graph.html"
        if stale.exists():
            stale.unlink()
        return False

    return True


def _build_flow_artifacts(
    G,
    god_nodes_list: list[dict],
    community_labels: dict[int, str],
    out_dir: Path,
) -> bool:
    """Run deterministic flow synthesis and emit ``flow_graph.{json,html}``.

    Naming is *not* run here — it requires an LLM dispatch the watcher can't
    perform on its own. Instead, this re-uses any cached names from a
    previous full run (``.dummyindex_flow_names.json``) plus user overrides
    (``flows.yaml``) so flows display human names where they exist and fall
    back to provisional IDs otherwise.
    """
    try:
        from dummyindex.analysis.flows import synthesize_flows, overlap_index
        from dummyindex.analysis.flow_naming import apply_named_results
        from dummyindex.pipeline.export import to_flow_json, to_flow_html, attach_hyperedges
    except Exception as exc:
        print(f"[dummyindex watch] Flow module unavailable: {exc}")
        return False

    try:
        flows = synthesize_flows(G)
    except Exception as exc:
        print(f"[dummyindex watch] Flow synthesis failed: {exc}")
        return False

    if not flows:
        return False

    try:
        flows = apply_named_results(flows, G, out_dir, fresh_results=[])
    except Exception as exc:
        print(f"[dummyindex watch] Flow naming apply failed: {exc}")
        # keep going — provisional IDs still produce a usable artifact

    try:
        attach_hyperedges(G, flows)
        index = overlap_index(flows)
        to_flow_json(flows, G, str(out_dir / "flow_graph.json"), overlap_index=index)
    except Exception as exc:
        print(f"[dummyindex watch] flow_graph.json failed: {exc}")
        return False

    try:
        to_flow_html(flows, G, str(out_dir / "flow_graph.html"), overlap_index=index)
    except Exception as exc:
        print(f"[dummyindex watch] flow_graph.html failed: {exc}")
        stale = out_dir / "flow_graph.html"
        if stale.exists():
            stale.unlink()
        return False

    return True


def _build_feature_artifacts(
    G,
    communities: dict[int, list[str]],
    god_nodes_list: list[dict],
    community_labels: dict[int, str],
    out_dir: Path,
) -> bool:
    """Run Stage A feature synthesis + dependency derivation + apply cached
    names + emit feature_graph.{json,html}. Naming itself requires a subagent
    pass and is *not* run here — the watcher only re-applies cached names
    and YAML overrides so artifacts are usable between full runs."""
    try:
        from dummyindex.analysis.features import (
            synthesize_features, derive_feature_dependencies, overlap_matrix, detect_orphans,
        )
        from dummyindex.analysis.feature_naming import (
            apply_feature_named_results, apply_feature_overrides,
        )
        from dummyindex.pipeline.export import (
            to_feature_json, to_feature_html, attach_hyperedges,
        )
    except Exception as exc:
        print(f"[dummyindex watch] Feature module unavailable: {exc}")
        return False

    flows = [h for h in G.graph.get("hyperedges", []) if h.get("kind") == "flow"]

    try:
        features = synthesize_features(
            G, communities, flows=flows,
            god_nodes_data=god_nodes_list,
            community_labels=community_labels,
        )
    except Exception as exc:
        print(f"[dummyindex watch] Feature synthesis failed: {exc}")
        return False

    if not features:
        return False

    try:
        features = apply_feature_named_results(features, G, out_dir, fresh_results=[])
        features, _diff = apply_feature_overrides(features, G, out_dir)
    except Exception as exc:
        print(f"[dummyindex watch] Feature naming/override failed: {exc}")

    try:
        deps = derive_feature_dependencies(G, features, flows=flows)
        attach_hyperedges(G, features)
        idx = overlap_matrix(features)
        orphans = detect_orphans(G, features)
        to_feature_json(features, G, str(out_dir / "feature_graph.json"),
                        feature_dependencies=deps, overlap_matrix=idx, orphans=orphans)
    except Exception as exc:
        print(f"[dummyindex watch] feature_graph.json failed: {exc}")
        return False

    try:
        to_feature_html(features, G, str(out_dir / "feature_graph.html"),
                        feature_dependencies=deps, overlap_matrix=idx, orphans=orphans)
    except Exception as exc:
        print(f"[dummyindex watch] feature_graph.html failed: {exc}")
        stale = out_dir / "feature_graph.html"
        if stale.exists():
            stale.unlink()
        return False

    return True


def check_update(watch_path: Path) -> bool:
    """Check for pending semantic update flag and notify the user if set.

    Cron-safe: always returns True so cron jobs do not alarm.
    Non-code file changes (docs, papers, images) require LLM-backed
    re-extraction via `/dummyindex --update` — this function only signals
    that the update is needed.
    """
    flag = Path(watch_path) / "dummyindex-out" / "needs_update"
    if flag.exists():
        print(f"[dummyindex check-update] Pending non-code changes in {watch_path}.")
        print("[dummyindex check-update] Run `/dummyindex --update` to apply semantic re-extraction.")
    return True


def _notify_only(watch_path: Path) -> None:
    """Write a flag file and print a notification (fallback for non-code-only corpora)."""
    flag = watch_path / "dummyindex-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1", encoding="utf-8")
    print(f"\n[dummyindex watch] New or changed files detected in {watch_path}")
    print("[dummyindex watch] Non-code files changed - semantic re-extraction requires LLM.")
    print("[dummyindex watch] Run `/dummyindex --update` in Claude Code to update the graph.")
    print(f"[dummyindex watch] Flag written to {flag}")


def _has_non_code(changed_paths: list[Path]) -> bool:
    return any(p.suffix.lower() not in _CODE_EXTENSIONS for p in changed_paths)


def watch(watch_path: Path, debounce: float = 3.0) -> None:
    """
    Watch watch_path for new or modified files and auto-update the graph.

    For code-only changes: re-runs AST extraction + rebuild immediately (no LLM).
    For doc/paper/image changes: writes a needs_update flag and notifies the user
    to run /dummyindex --update (LLM extraction required).

    debounce: seconds to wait after the last change before triggering (avoids
    running on every keystroke when many files are saved at once).
    """
    try:
        from watchdog.observers import Observer
        from watchdog.observers.polling import PollingObserver
        from watchdog.events import FileSystemEventHandler
    except ImportError as e:
        raise ImportError("watchdog not installed. Run: pip install watchdog") from e

    last_trigger: float = 0.0
    pending: bool = False
    changed: set[Path] = set()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            nonlocal last_trigger, pending
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() not in _WATCHED_EXTENSIONS:
                return
            if any(part.startswith(".") for part in path.parts):
                return
            if "dummyindex-out" in path.parts:
                return
            last_trigger = time.monotonic()
            pending = True
            changed.add(path)

    handler = Handler()
    # Use polling observer on macOS — FSEvents can miss rapid saves in some editors
    observer = PollingObserver() if sys.platform == "darwin" else Observer()
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()

    print(f"[dummyindex watch] Watching {watch_path.resolve()} - press Ctrl+C to stop")
    print("[dummyindex watch] Code changes rebuild graph automatically. "
          "Doc/image changes require /dummyindex --update.")
    print(f"[dummyindex watch] Debounce: {debounce}s")

    try:
        while True:
            time.sleep(0.5)
            if pending and (time.monotonic() - last_trigger) >= debounce:
                pending = False
                batch = list(changed)
                changed.clear()
                print(f"\n[dummyindex watch] {len(batch)} file(s) changed")
                if _has_non_code(batch):
                    _notify_only(watch_path)
                else:
                    _rebuild_code(watch_path)
    except KeyboardInterrupt:
        print("\n[dummyindex watch] Stopped.")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Watch a folder and auto-update the dummyindex graph")
    parser.add_argument("path", nargs="?", default=".", help="Folder to watch (default: .)")
    parser.add_argument("--debounce", type=float, default=3.0,
                        help="Seconds to wait after last change before updating (default: 3)")
    args = parser.parse_args()
    watch(Path(args.path), debounce=args.debounce)
