# Integration Guide: Replacing the Old Scoring with ScoreEngine

## Files to Add

Copy these files to your project root (same directory as `server.py`):

- `scoring.py` — the new scoring engine
- `scoring_config.json` — adjustable weights and thresholds

## Changes to server.py

### 1. Import the new engine

At the top of `server.py`, add:

```python
from scoring import ScoreEngine
```

### 2. Replace the matching logic in web_query and web_process

**Before** (lines ~606–654 in server.py, the ME matching block):

```python
# Calculate matching score
if cal_name:
    cal_parts = cal_name.split()
    # ... 40+ lines of expanding, transliterating, building compare_words ...
    score = calculate_similarity(expanded_cal_name, text1, original_word_count)
    result["me.matching"] = score
```

**After**:

```python
# Calculate matching score
if cal_name:
    engine = ScoreEngine(conn=db)
    score_result = engine.score_match(
        cal_name=cal_name,
        api_first=me_first_name,
        api_last=me_last_name,
        api_common_name=me_common_name,
        api_source="ME"
    )
    result["me.matching"] = score_result["final_score"]
    result["me.risk_tier"] = score_result["risk_tier"]
    # Optional: store the explanation for debugging/audit
    result["me.score_explanation"] = score_result["explanation"]
```

Do the same for the SYNC matching block, using `api_source="SYNC"`.

### 3. For multi-API combined scoring (optional)

If both ME and SYNC are used, you can get a combined score:

```python
engine = ScoreEngine(conn=db)
combined = engine.score_multi_api(
    cal_name=cal_name,
    me_result={"first_name": me_first_name, "last_name": me_last_name, "common_name": me_common_name},
    sync_result={"first_name": sync_first, "last_name": sync_last}
)
result["combined_score"] = combined["final_score"]
result["combined_tier"] = combined["risk_tier"]
```

### 4. The translation logic stays

The existing transliteration + nickname lookup code in `server.py` that populates `me.translated` can stay — it's useful for display purposes in the output Excel. The ScoreEngine does its own transliteration internally for matching purposes.

## What You Can Remove

After switching to ScoreEngine, you can remove these from your matching code blocks:
- `expand_cal_name_with_nicknames()` calls (ScoreEngine handles this internally)
- `calculate_similarity()` calls (replaced by `engine.score_match()`)
- All the `compare_words` building logic
- The `nickname_source` / `nickname_variants` logic

These functions still exist in `functions.py` for backward compatibility, but the matching code in `server.py` no longer needs them.

## Output Format Changes

The new engine adds these optional fields to each result:

| Field | Example | Description |
|-------|---------|-------------|
| `me.risk_tier` | "HIGH" | Risk classification |
| `me.score_explanation` | (multiline text) | Full audit trail |

These can be added as new columns in the output Excel if desired.

## Tuning the Config

Edit `scoring_config.json` to adjust:

```json
{
    "weights": {
        "last_name": 0.65,    // ← increase to make last name more important
        "first_name": 0.35    // ← decrease accordingly (should sum to 1.0)
    },
    "risk_tiers": {
        "high_confidence": { "min": 85 },   // ← lower to accept more matches
        "medium_confidence": { "min": 60 },
        "low_confidence": { "min": 35 },
        "no_match": { "min": 0 }
    }
}
```

No code changes or restart needed — the config is read on each request.
