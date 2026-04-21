# Face Recognition

## Approach: Supervised Anchor Matching

For ~20 known family members, skip unsupervised clustering entirely.

**How it works:**
1. Collect 3-5 anchor photos per person covering different decades
2. On indexing: detect all faces in every photo
3. For each detected face → compare embedding against all anchors → pick best match above threshold
4. Store `person_id` + `confidence` in `photo_people` table

**Why not clustering:**
- Clustering = algorithm groups faces first, you label clusters after
- Useful for unknown open sets (party photos with strangers)
- For 20 known people → supervised is simpler, more accurate, easier to debug

---

## Installation (Hardest Part)

`face_recognition` wraps `dlib` which requires CMake + C++ compiler.

```bash
# macOS
brew install cmake
pip install face_recognition

# if that fails
brew install dlib
pip install face_recognition
```

On failure: check dlib install logs first, not face_recognition logs.

---

## Anchor Photos — Best Practices

- 3-5 photos per person minimum
- Cover age ranges: childhood, young adult, current
- Good lighting, face forward, unobstructed
- One face per anchor photo (avoid group shots as anchors)
- Store in `data/anchors/{person_id}/`

---

## Age Gap Problem

Same person at age 5 vs 45 = very different face embedding. `face_recognition` will miss matches across large age gaps.

### Solution 1: Multiple anchors spanning decades (primary fix)
```
grandma_anchors/
  grandma_1965.jpg   ← young
  grandma_1985.jpg   ← middle
  grandma_2010.jpg   ← older
  grandma_2024.jpg   ← current
```
Match against all anchors, use best score. Covers most cases.

### Solution 2: Decade-aware matching
Use EXIF `taken_at` to narrow anchor comparison:
```python
photo_year = exif_date.year
# only compare against anchors within ±15 years of photo date
relevant_anchors = [a for a in anchors if abs(a.year - photo_year) <= 15]
```
Reduces false matches between young/old versions of different people.

### Solution 3: Skip face matching on old/scanned photos
Photos pre-1990 are often low resolution, B&W, or scanned — `face_recognition` accuracy drops significantly. Options:
- Accept lower accuracy
- Fall back to caption-based search for old photos
- Use LLM vision on small result sets (send 20 candidates, ask "is grandma in this photo?")

---

## Accuracy Limits

| Scenario | Accuracy |
|---|---|
| Clear face, same decade as anchor | Very high |
| Profile view or partial occlusion | Reduced |
| Age gap > 20 years, single anchor | Poor |
| Pre-1990 scanned photos | Poor |
| Siblings or similar-looking people | May confuse |

Library limit: ~50-100 people reliably. For 20 people, nowhere near limit.
For 500+ people: switch to DeepFace + ArcFace model.

---

## Confidence Threshold

Default threshold in `face_recognition`: 0.6 (lower = stricter).

Recommended:
- Start at 0.5 for family photos (stricter, fewer false positives)
- Lower to 0.6 if missing too many true matches
- Store raw confidence score in DB — can re-threshold without re-running face detection

```python
results = face_recognition.compare_faces(anchor_encodings, face_encoding, tolerance=0.5)
distances = face_recognition.face_distance(anchor_encodings, face_encoding)
best_match_idx = distances.argmin()
confidence = 1 - distances[best_match_idx]
```

---

## Re-indexing Faces

Face indexing is independent of caption/vector indexing. Re-run anytime:

```bash
python index.py --step faces --reindex        # redo all
python index.py --step faces --person grandma # redo one person only
python index.py --step faces --since 2024-01-01 # only new photos
```

Adding a new person = add their anchors + run `--person new_person`. Does not affect other people's matches.
