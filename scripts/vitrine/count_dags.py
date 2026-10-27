"""Inventaire statique des DAGs Airflow (sans installer Airflow).

Parcourt dags/ via ast, repère chaque appel DAG(...) et affiche dag_id,
planification et statut « en pause » déclaré dans la description.

Usage : python scripts/vitrine/count_dags.py [--json out.json]
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _kw(call: ast.Call, *names: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg in names), None)


def inventory() -> list[dict]:
    rows = []
    for path in sorted((ROOT / "dags").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        consts = {
            t.id: n.value.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
            for t in n.targets
            if isinstance(t, ast.Name)
        }
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "DAG"):
                continue
            dag_id = _kw(node, "dag_id")
            if isinstance(dag_id, ast.Constant):
                dag_id = dag_id.value
            elif isinstance(dag_id, ast.Name):
                dag_id = consts.get(dag_id.id, dag_id.id)
            sched = _kw(node, "schedule", "schedule_interval")
            desc = _kw(node, "description")
            desc_txt = ast.unparse(desc) if desc is not None else ""
            rows.append(
                {
                    "file": path.relative_to(ROOT).as_posix(),
                    "dag_id": dag_id,
                    "schedule": ast.literal_eval(sched)
                    if isinstance(sched, ast.Constant)
                    else (ast.unparse(sched) if sched else None),
                    "paused_in_description": "PAUSED" in desc_txt.upper(),
                    "legacy": "legacy" in path.parts[-2],
                }
            )
    return rows


if __name__ == "__main__":
    rows = inventory()
    for r in rows:
        flag = " [PAUSED]" if r["paused_in_description"] else ""
        print(f"{r['dag_id']:<45} {r['schedule']!s:<22} {r['file']}{flag}")
    print(
        f"\n{len(rows)} DAGs déclarés, {sum(r['paused_in_description'] for r in rows)} marqués PAUSED, "
        f"{sum(r['legacy'] for r in rows)} legacy"
    )
    if "--json" in sys.argv:
        out = pathlib.Path(sys.argv[sys.argv.index("--json") + 1])
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
