"""Transparent condition comparisons and context-preserving research exports."""
import json
from datetime import datetime, timezone

import pandas as pd

from src.evidence import material_label, sample_rows


def numeric_comparison(reported, assumed):
    if assumed is None or pd.isna(reported):
        return "unknown"
    return "equal" if abs(float(reported) - float(assumed)) < 0.000001 else "different"


def condition_comparison(rows, environment, assumptions):
    target = {"ISS": "microgravity", "Earth Lab": "normal gravity", "Moon Base": "lunar", "Mars Mission": None}[environment]
    output = []
    for _, row in rows.iterrows():
        gravity = "unknown" if target is None or pd.isna(row.gravity) else "equal" if row.gravity.casefold() == target else "different"
        oxygen = numeric_comparison(row.oxygen_pct, assumptions.get("oxygen"))
        pressure = numeric_comparison(row.pressure_kpa, assumptions.get("pressure"))
        state = "source_conflict" if row.get("review_status") == "conflict" else "different_conditions" if "different" in (gravity, oxygen, pressure) else "incomplete_conditions"
        if state == "incomplete_conditions" and all(v == "equal" for v in (gravity, oxygen, pressure)):
            state = "three_fields_equal"
        output.append({"record_id": row.record_id, "experiment_id": row.experiment_id, "material": row.material,
                       "gravity_match": gravity, "oxygen_match": oxygen, "pressure_match": pressure, "comparison": state})
    return pd.DataFrame(output, columns=["record_id", "experiment_id", "material", "gravity_match", "oxygen_match", "pressure_match", "comparison"])


def evidence_export(tests, selected, environment, assumptions, filters, snapshot):
    from src.extended_evidence import load_extension
    extended, _, extended_snapshot = load_extension()
    reference = tests[tests.material.isin(selected)].copy()
    if filters.get("oxygen_enabled"):
        reference = reference[reference.oxygen_pct.between(*filters["oxygen_range"])]
    records = []
    comparison = condition_comparison(reference, environment, assumptions).set_index("record_id").to_dict("index")
    for material in selected:
        rows = sample_rows(reference, material)
        if rows.empty:
            records.append({"material": material, "evidence_status": "no_matching_evidence", "test_count": None,
                            "ignition": "unknown", "comparison": "no_matching_evidence"})
        else:
            for row in json.loads(rows.to_json(orient="records", force_ascii=False)):
                records.append({**row, **comparison[row["record_id"]], "evidence_status": "compiled_reference"})
    for row in records:
        aliases = {'plastik (pmma)': 'PMMA', 'pamuklu kumaş': 'SIBAL'}
        term = aliases.get(row['material'])
        related = [r for r in extended if term and term.casefold() in r['material'].casefold()]
        row.update({"sample_group": material_label(row["material"]), "selected_environment": environment,
                    "related_study_records_json": json.dumps(related, ensure_ascii=False), "extended_snapshot_sha256": extended_snapshot,
                    "assumed_oxygen_pct": assumptions.get("oxygen"), "assumed_pressure_kpa": assumptions.get("pressure"),
                    "assumed_mission_phase": assumptions.get("atmosphere", ""), "filters_json": json.dumps(filters),
                    "snapshot_sha256": snapshot, "exported_utc": datetime.now(timezone.utc).isoformat(),
                    "risk_status": "unavailable", "human_approval": "pending"})
        if row.get("source_url") and row.get("source_page"):
            row["source_page_url"] = row["source_url"] + "#page=" + str(int(row["source_page"]))
    return pd.DataFrame(records)


def csv_bytes(frame):
    safe = frame.map(lambda x: "'" + x if isinstance(x, str) and x.lstrip().startswith(("=", "+", "-", "@")) else x)
    return safe.to_csv(index=False).encode("utf-8-sig")


def research_brief(frame, lang="EN"):
    tr = lang == "TR"
    title = "FLAMEGUARD araştırma özeti" if tr else "FLAMEGUARD research brief"
    lines = [f"# {title}", "", "İnsan uzman onayı bekliyor. Uçuşa uygunluk kararı içermez." if tr else
             "Human expert approval pending. No flight qualification decision.", ""]
    if frame.empty:
        return "\n".join(lines)
    first = frame.iloc[0]
    lines += [f"Environment / Ortam: {first.selected_environment}", f"Snapshot SHA-256: {first.snapshot_sha256}",
              f"Assumptions / Varsayımlar: O₂={first.assumed_oxygen_pct} %, P={first.assumed_pressure_kpa} kPa; {first.assumed_mission_phase}",
              f"Filters / Filtreler: {first.filters_json}", ""]
    for material, group in frame.groupby("sample_group", sort=False):
        lines += [f"## {material}"]
        for _, row in group.iterrows():
            if row.evidence_status == "no_matching_evidence":
                lines += ["Özgün derlemede eşleşen kanıt yok; ek çalışma kayıtları JSON alanındadır." if tr else "No matching evidence in the original compilation; related study records are preserved in the JSON field."]
            else:
                lines += [f"- {row.experiment_id}: {row.test_count} tests; ignition={row.ignition}; sustained={row.sustained}; spread={row.propagation}; extinction={row.extinction}",
                          f"  Source: {row.source_page_url}", f"  {row.source_note_tr if tr else row.source_note_en}"]
        lines += [""]
    return "\n".join(lines)
