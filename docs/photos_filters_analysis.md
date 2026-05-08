# Photo Filters Analysis

Analysis of OpenAI-tagged metadata to identify low-value photos for filtered display and game modes.
Based on visual inspection of ~25 sampled photos + value distribution across 23,190 captioned photos.

## Photo Counts (denominator: 23,190 captioned)

| Filter | Photos hidden | % of library |
|---|---|---|
| Tier 1: docs/other | 421 | 1.8% |
| Type 2: utility objects (tag-based) | 30 | 0.1% |
| **Combined display filter** | **450** | **1.9%** |
| People-games exclusion | 8,703 | 37.5% |

## Field Value Distributions

| Field | Top values |
|---|---|
| `content_type` | photo: 22,769 · other: 365 · document: 56 |
| `subject_type` | group: 9,729 · landscape: 5,968 · portrait: 3,029 · candid_people: 1,234 · cityscape: 748 · object: 700 · other: 636 · unclear: 519 · pet: 504 |
| `primary_focus` | people: 13,349 · place: 7,764 · object: 1,788 · unclear: 216 · activity: 73 |
| `indoor_outdoor` | outdoor: 16,320 · indoor: 6,541 · unclear: 247 · mixed: 82 |
| `setting_type` | nature: 9,463 · urban_street: 3,995 · landmark: 2,839 · domestic_interior: 2,711 · other: 1,814 · event_venue: 1,514 · restaurant_cafe: 527 · workplace: 231 |
| `sharpness` | sharp: 22,043 · slightly_blurry: 1,141 · very_blurry: 6 |
| `face_clarity_score` | null (no face): 13,216 · 4: 7,117 · 3: 1,535 · 2: 1,206 · 5: 105 · 1: 11 |

## Key Findings from Visual Inspection

### `face_clarity_score IS NULL` ≠ no people
Silhouettes (e.g. person photographing Santorini sunset) and distant background figures
register as NULL score. Do NOT use this field to exclude "no-people" photos — will filter
high-value travel shots.

### `very_blurry` — do NOT filter
Old scanned family photos are classified `very_blurry`. These are valuable.
`slightly_blurry` (1,141 photos) may also include old scans — treat with caution.

### `object` + `domestic_interior` — two sub-populations
Visual inspection revealed a misclassification pattern:
- **Genuine junk**: kitchen/bathroom renovation documentation (sink, stove, tiles, cabinet)
- **Museum/palace misclassified as domestic**: ornate chandeliers, antique furniture, harps
  photographed inside landmark interiors (e.g. Romania palace shots). Model assigns
  `domestic_interior` when it sees ornate indoor setting.

Tag-based sub-filter rescues the museum shots. Kitchen/bathroom tags reliably identify
the junk subset.

### Landscape photos — valuable, not filterable from display
`subject_type IN ('landscape','cityscape')` photos are mostly trip memories (Colca Canyon
condors, Maras salt terraces, Sea of Galilee, Santorini). Filtering them from general
display would degrade the collection. Correct use: **exclude from people-focused games**.

---

## Recommended Filters

### 1. General display — hide non-photo content
Hides documents, screenshots, misc non-photos. Safe, no false positives.

```sql
-- Hide: documents, screenshots, misc non-photo files
WHERE content_type IN ('document', 'other')
```

**Photos hidden: 421 (1.8%)**

Note: `very_blurry` intentionally excluded — old scanned photos fall in this bucket.

---

### 2. General display — hide utility/renovation object photos
Hides kitchen/bathroom/renovation documentation. Tag-based to avoid filtering
museum/palace objects misclassified as `domestic_interior`.

```sql
-- Hide: utility object documentation (kitchen, bathroom, renovation shots)
WHERE subject_type = 'object'
  AND setting_type = 'domestic_interior'
  AND (
    tags LIKE '%kitchen%' OR tags LIKE '%bathroom%' OR tags LIKE '%sink%'
    OR tags LIKE '%stove%' OR tags LIKE '%faucet%' OR tags LIKE '%cabinet%'
    OR tags LIKE '%countertop%' OR tags LIKE '%tiles%'
  )
```

**Photos hidden: 30 (0.1%)**

---

### 3. Combined display filter (1 + 2)
Recommended default for curated/high-value display mode.

```sql
-- Hide: non-photo files OR utility object documentation
WHERE content_type IN ('document', 'other')
   OR (
     subject_type = 'object'
     AND setting_type = 'domestic_interior'
     AND (
       tags LIKE '%kitchen%' OR tags LIKE '%bathroom%' OR tags LIKE '%sink%'
       OR tags LIKE '%stove%' OR tags LIKE '%faucet%' OR tags LIKE '%cabinet%'
       OR tags LIKE '%countertop%' OR tags LIKE '%tiles%'
     )
   )
```

**Photos hidden: 450 (1.9%)**

---

### 4. People-focused games — exclude no-people photos
For games that require identifying/guessing people. Excludes landscapes, cityscapes,
objects, pets, food — keeps portraits, groups, candid people shots.

```sql
-- Include only: photos where people are the primary subject
WHERE subject_type IN ('portrait', 'group', 'candid_people')
  AND primary_focus = 'people'
  AND content_type = 'photo'
```

**Photos in pool: ~8,703 excluded → ~14,487 remain (62.5% of library)**

Alternatively, inverse (exclude non-people):
```sql
-- Exclude: photos with no people as primary subject
WHERE subject_type NOT IN ('portrait', 'group', 'candid_people')
   OR primary_focus != 'people'
```

---

## Schema Version Note

All filters above are calibrated against `caption_schema_version = 2`.
If schema is bumped, re-validate tag patterns — field semantics may shift.
