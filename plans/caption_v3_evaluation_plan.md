# Caption Schema v3 — Evaluation Plan

**For:** Sonnet 4.6 (separate session from the implementation agent)
**Goal:** Re-run v3 caption on the 50 photos previously captioned at v2, then judge whether v3 is good enough to scale to 23K. Compare per-field, per-photo against v2 and against the ground-truth labels in `caption_quality_report.md`.
**Prereq:** The implementation plan (`plans/caption_v3_implementation_plan.md`) has already merged. `CAPTION_SCHEMA_VERSION` is now `3`.

---

## Background

`caption_quality_report.md` is the v2 audit. It contains:

- A pass / partial / fail rubric per field (10 fields).
- Detailed per-row verdicts for the **first 30 photos** of the 50-photo v2 set.
- Failure-pattern explanations (rows are referenced by ordinal: row 1, row 2, ...).
- Recommended fixes 1–3.

The implementation plan applied fixes 1, 2, 3-lite (event_venue usage rule, no enum change) and a fourth fix the report identified by example but did not enumerate as a numbered fix: surface cultural / religious / military context in caption + tags.

Only 50 photos exist at `caption_schema_version = 2` in `data/photos.db`. After the schema bump to 3, the next `--step caption` run re-captions them automatically — no `--reindex` flag needed (see `app/indexer/CLAUDE.md`).

---

## Procedure

### Step 1 — Snapshot v2 outputs

Before running v3, dump the 50 v2 captions to a JSON file. Run from the repo root:

```bash
sqlite3 data/photos.db -json "
  SELECT id, original_filename, caption, tags, activities,
         content_type, subject_type, primary_focus,
         indoor_outdoor, setting_type, sharpness, face_clarity_score,
         caption_schema_version
  FROM photos
  WHERE caption_schema_version = 2
  ORDER BY original_filename;
" > plans/eval/v2_snapshot.json
```

Create `plans/eval/` if it does not exist. Sanity-check: the file should contain exactly 50 rows. If it contains more or fewer, stop and report — the assumption that "only the 50-photo sample is at v2" is the basis of this entire plan.

Map each row's `original_filename` to the row number from `caption_quality_report.md` (rows 1–30). Save that mapping to `plans/eval/row_to_id.json` so the report's per-row verdicts can be looked up by photo id later. Filenames in the report are listed in the "Examples (10)" table and in the failure-pattern sections (e.g. row 6 = `IMG_0564.jpg`). For any row number not directly named in the report, infer from the v2 snapshot ordering — the report says "Sample: 30 random photos … year 2013" and the audit was performed in row order. If the mapping is ambiguous for any row, mark it `"unknown"` and exclude that row from the strict-rubric scoring (but still include it in the v2-vs-v3 diff).

### Step 2 — Re-caption at v3

After confirming the snapshot, re-caption the 50 photos. The schema bump means a normal caption run picks them up automatically.

```bash
python -m app.indexer.cli --step caption --limit 50
```

This costs real OpenAI dollars. Confirm with the user (or with the orchestrating agent) before running. Expected cost: ~$0.10–0.30 for 50 photos at `gpt-4o-mini` or similar; verify against `app/config.py:caption_model` first.

After the run, re-query and dump v3:

```bash
sqlite3 data/photos.db -json "
  SELECT id, original_filename, caption, tags, activities,
         content_type, subject_type, primary_focus,
         indoor_outdoor, setting_type, sharpness, face_clarity_score,
         caption_schema_version
  FROM photos
  WHERE caption_schema_version = 3
    AND id IN (SELECT id FROM photos WHERE original_filename IN (
      <list of the 50 filenames from step 1>
    ))
  ORDER BY original_filename;
" > plans/eval/v3_snapshot.json
```

Sanity check: 50 rows, all with `caption_schema_version = 3`.

### Step 3 — Diff v2 → v3

For each photo, compare every field. Build a per-photo per-field diff. Categorize each cell as:

- `unchanged` — identical value (or identical-up-to-set for tags / activities)
- `changed` — different value
- `new_null` — v2 had a value, v3 returned null
- `new_value` — v2 was null, v3 returned a value

Save raw diff to `plans/eval/v2_v3_diff.json`.

### Step 4 — Score v3 against report ground truth (rows 1–30)

For each of the 30 photos that have ground-truth verdicts in `caption_quality_report.md`, score every field as **pass / partial / fail** using the same rubric the report used. The rubric is implicit in the report — infer from the failure-pattern descriptions and the Examples table. Specifically:

- `subject_type`: pass if the v3 value matches the corrected value the report names (e.g. row 3 = `portrait`, row 1 = `group`, row 2 = `candid_people`). Partial if v3 picked a related but suboptimal label (e.g. `mixed` instead of `group`). Fail otherwise. Use the corrections enumerated in failure-pattern §1.
- `face_clarity_score`: pass if v3 score is within 1 step of the report's stated correct range (rows 13, 22, 27 should now be 3+ instead of null; rows 3, 20, 24 should now be 4–5 instead of 3). Partial if direction is right but magnitude still off by 1. Fail if still null where face is visible, or still off by 2+.
- `setting_type`: pass if v3 matches the "Actual setting" column in failure-pattern §3 mapped to enum (synagogue → `event_venue`; military base event → `event_venue`; public park national event → `event_venue`; hotel bathroom → `domestic_interior`). Partial if v3 picked a less-wrong enum than v2.
- `caption` + `tags`: pass if v3 surfaces the missed context elements named in failure-pattern §4 (row 6: synagogue / tallit / tefillin / Hebrew; row 13: soldier / military / uniform; row 25: no `selfie` hallucination). Partial if some but not all elements appear. Fail otherwise.
- All other fields: pass if v3 matches v2 on photos the report marked PASS for that field. Any v2-pass → v3-not-pass is a regression and must be flagged separately.

For rows 31–50 (no ground truth in report), do an **ad-hoc audit**: spot-check each of the four target fields and flag anything that looks obviously wrong. Do not synthesize a strict pass rate for these 20.

### Step 5 — Summary table

Produce a per-field summary identical in format to the report's "Pass Rate per Field" table, but with **two columns** showing v2 strict % (from report) and v3 strict % (from this run). Row count is 30 (the report's audited subset) so percentages are comparable.

Also produce:

- **Regression list:** every photo + field where v2 was PASS in the report but v3 scored partial or fail.
- **Improvement list:** every photo + field where v2 was FAIL in the report but v3 scored pass.
- **Net-change-per-field:** v3 strict % minus v2 strict %, per field.

### Step 6 — Verdict

State a yes / no on scaling to 23K. The acceptance bar:

1. The four target fields each show v3 strict ≥ 85% on the 30-photo subset (`subject_type`, `face_clarity_score`, `setting_type`, `caption`).
2. Tags strict ≥ 85% (caption-context fix should pull this up too).
3. **Zero regressions** on fields that were 100% in v2 (`content_type`).
4. ≤1 regression on fields that were 97% in v2 (`indoor_outdoor`, `sharpness`).
5. The Bar Mitzvah photo (row 6, `IMG_0564.jpg`) caption explicitly names tallit / tefillin / synagogue OR Hebrew. This is the biggest single quality lever; if v3 still describes it as "room with windows", the caption-context fix is not working and v3 is not ready regardless of aggregate scores.

If all five hold → recommend scaling to 23K. If not → list which prompt rules likely need iteration and stop.

---

## Output

Write the final report to `plans/eval/caption_v3_audit.md`. Use the same section structure as `caption_quality_report.md` (Verdict, Pass Rate per Field, Failure Patterns, Examples, Recommendation). Add one extra section: **Delta vs v2** with the regression list, improvement list, and net change per field.

Commit the report with the message:

```
docs: caption v3 evaluation against 50-photo sample
```

Do not modify any other files. Do not run prompt iterations yourself — if v3 fails the bar, the next iteration is owned by the user.

---

## Out of Scope

- Editing the prompt or schema. Iteration on the prompt is a separate cycle.
- Running v3 against any photos beyond the 50 already at v2.
- Touching the search / embed / API layers.
- Auditing fields the report already marked at 93–100% in v2 unless v3 regresses on them (in which case flag, do not deep-dive).
