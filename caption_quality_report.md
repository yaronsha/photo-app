# Caption Quality Audit — Schema v2

**Sample:** 30 random photos, all `caption_schema_version=2`, year 2013  
**Audited:** 2026-05-02

---

## Verdict

Caption output is **trustworthy enough to scale to 23K — but fix two prompts first.** Core fields (`content_type`, `indoor_outdoor`, `sharpness`, `activities`) are near-perfect. Free-text `caption` and `tags` are 83–87% accurate. The two critical weaknesses are:

1. **`subject_type` at 63% strict** — the model systematically labels visible-people photos as "unclear" instead of portrait/group/candid_people, making subject-based filtering unreliable.
2. **`face_clarity_score` at 67% strict** — systemic false-null and downward score bias; 7/30 rated only partial credit.

Biggest risk: scaling at current quality means ~37% of people photos land in the wrong `subject_type` bucket, degrading search queries that filter by subject. Both issues are prompt bugs fixable in ~30 minutes. After fixes, estimated ≥90% across all fields.

---

## Pass Rate per Field

| Field | Pass | Partial | Fail | N | Strict % | +Partial % |
|---|---|---|---|---|---|---|
| content_type | 30 | 0 | 0 | 30 | **100%** | 100% |
| indoor_outdoor | 29 | 1 | 0 | 30 | **97%** | 100% |
| sharpness | 29 | 1 | 0 | 30 | **97%** | 100% |
| activities | 28 | 2 | 0 | 30 | **93%** | 100% |
| primary_focus | 28 | 0 | 2 | 30 | **93%** | 93% |
| tags | 26 | 3 | 2 | 30 | **87%** | 97% |
| caption | 25 | 2 | 3 | 30 | **83%** | 90% |
| setting_type | 23 | 3 | 4 | 30 | **77%** | 87% |
| face_clarity_score | 20 | 7 | 3 | 30 | **67%** | 90% |
| subject_type | 19 | 2 | 9 | 30 | **63%** | 70% |

**Overall strict: 257/300 = 85.7%**

---

## Failure Patterns

### 1. `subject_type` — "unclear" over-applied to visible people (9 fails)

Affected rows: 1, 2, 3, 14, 15, 21, 24, 25, 27.

Every case: photo contains clearly identifiable people labeled "unclear". The model appears to treat "prefer unclear over guessing" as permission to avoid all subject classification when people are present but not posing perfectly. Correct values by case: portrait (rows 3, 15, 21 — single clear subject), group (rows 1, 14, 24 — 2+ people), candid_people (rows 2, 25, 27 — active/unposed people). The model correctly uses group/portrait/candid_people in 19/30 cases — the failures are not random, they cluster around non-frontal poses and person-plus-subject compositions (woman+dog, rider+horse, climbers).

### 2. `face_clarity_score` — false nulls and downward score bias (3 fails, 7 partial)

- **False null** (rows 13, 22, 27): null assigned when faces are prominently visible — e.g., row 13 has a soldier's face filling a quarter of the frame.
- **Under-scoring** (rows 3, 20, 24): close-up faces rated 3 when 4–5 is warranted. Row 3 is a selfie face at <30cm — rated 3.
- Pattern: the model appears calibrated one step too conservative throughout the 1–5 range.

### 3. `setting_type` — fails on event/institutional contexts (4 fails)

| Row | Actual setting | Model label |
|---|---|---|
| 1 | Hotel bathroom | `workplace` |
| 6 | Synagogue | `domestic_interior` |
| 7 | Public park (national event) | `landmark` |
| 13 | Military base event | `nature` |

Common cause: when a space doesn't map cleanly to one of the 11 categories, the model picks a plausible-but-wrong category rather than `other`. `event_venue` is underused — zero times in 30 photos despite rows 7, 13 being clear event contexts.

### 4. `caption` + `tags` — missed high-context scenes (3 fails)

- **Row 6** (Bar Mitzvah): boy wearing tallit and tefillin in a synagogue with a Hebrew memorial plaque on the wall. Caption: "Two children smiling inside a room with large windows." Tags contain no reference to synagogue, ceremony, prayer shawl, or Hebrew. Highest semantic loss in the sample — a search for "synagogue" or "Bar Mitzvah" returns nothing.
- **Row 13** (IDF event): soldiers in olive IDF uniform occupy the entire foreground. Caption calls it "family gathering...park...casual." Tags: no mention of soldier, military, or uniform.
- **Row 25** (scenic overlook): two people photographed by a third person. Caption and tags include "selfie" — the only outright hallucination in 30 samples. Low frequency but worth monitoring.

---

## Examples (10)

| Row | Filename | Image | Model output | Verdict |
|---|---|---|---|---|
| 6 | IMG_0564.jpg | Boy in tallit+tefillin, synagogue with Hebrew plaque | "room with large windows" / domestic_interior | **FAIL** — complete context miss |
| 13 | P1030358.JPG | IDF soldiers foreground, military base behind | "family gathering outdoors...casual" / nature | **FAIL** — context miss |
| 25 | 22.9.13 273-edited.jpg | Couple at overlook, photographed by 3rd person | "couple taking a selfie" | **FAIL** — hallucination |
| 1 | eti_s iphone 007.jpg | Woman's bathroom mirror selfie, hotel room | caption ✓ / subject_type=unclear, setting=workplace | **PARTIAL** |
| 2 | צפן יוון 2013 137-edited.jpg | Two women climbing canyon wall with helmets | caption ✓ / subject_type=unclear | **PARTIAL** |
| 3 | 22.9.13 144.jpg | Close-up selfie, woman + fluffy dog | caption ✓ / subject_type=unclear, face_clarity=3 (too low) | **PARTIAL** |
| 5 | 22.9.13 408.jpg | Meteora rock formations, landscape | All fields correct | **PASS** |
| 10 | P9180116-edited.JPG | Group whitewater rafting | caption ✓, group ✓, rafting ✓ | **PASS** |
| 19 | IMG_1875.jpg | Three people at restaurant, clear faces | All fields correct | **PASS** |
| 30 | צפן יוון 2013 023-edited.jpg | Two hikers, one drinking, forest trail | "Two people on rocky trail, one drinking" / candid_people ✓ | **PASS** |

---

## Recommendation

**Scale to 23K — fix two prompts first, one optional.**

**Required before scaling:**

**Fix 1 — `subject_type`:** Add explicit examples to the prompt:
> "If you can clearly see a person, do NOT use `unclear`. Single person (even from behind or in motion) → `portrait` or `candid_people`. Two or more people together → `group`. People not posing → `candid_people`. `unclear` only when you cannot identify whether a human is present."

**Fix 2 — `face_clarity_score`:** Add calibration note:
> "A face that fills >25% of the frame or that you can clearly describe → 4–5. A face visible at medium distance → 3. A partially obscured or small face → 2. `null` only when no human face is discernible at all. When in doubt, score rather than null."

**Optional Fix 3 — `setting_type`:** Add `event_venue` usage examples (military ceremonies, religious events, outdoor public gatherings with crowds). Also note: hotel bathroom → `domestic_interior`, not `workplace`.

**Cost-benefit:** At current quality (~85.7% strict), roughly 3,300 of 23,199 photos will have at least one field wrong. After the two required fixes, estimated ~91–93% overall, reducing per-photo errors to ~1,600–1,900. For a personal search app, that residual error rate is acceptable. Caption and tags quality (83–87%) is already strong enough for semantic search today.
