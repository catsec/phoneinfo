# PhoneInfo Scoring Formula — Risk Team Reference

## Purpose

When a customer applies for a credit card from Cal, they provide a phone number and their official name (as written on their ID). We verify identity by querying external APIs (ME, SYNC) that have crowd-sourced phonebook data mapping phone numbers to names.

A **high score** means the phone number's registered owner matches the customer's claimed name — the phone likely belongs to them.

A **low score** means the names don't match — the phone may have been stolen or the identity may be forged.

## Why Not Just Do Exact Comparison?

Three real-world problems make exact string matching fail:

1. **Nicknames**: The customer's ID says "חביבה פראס" but everyone saves her as "חבי פראס" in their contacts. The API returns the crowd-sourced nickname, not the formal name.

2. **Transliteration**: Arabic, Russian, and English names must be converted to Hebrew for comparison. "محمد" → "מוחמד", "Александр" → "אלכסנדר". Transliteration is imperfect and produces fuzzy matches.

3. **Spelling variations**: "דויד" vs "דוד", "כהן" vs "כהאן" — legitimate variations that shouldn't cause false negatives.

## The Formula

### Step 1: Separate First and Last Name

The customer's name is split into first name and last name. The API result's first and last names are handled independently.

> **Why?** Last name is far more discriminating. There are roughly 50,000 unique last names in Israel but only about 3,000 common first names. A random person having the same first name "דוד" is much more likely than having the same last name "אפשטיין".

### Step 2: Score Each Component (0–100)

Each name component (first name and last name) is tested through a cascade of matching strategies, from strongest to weakest:

| Priority | Match Type | Score | Example |
|----------|-----------|-------|---------|
| 1 | **Exact match** | 100 | "כהן" == "כהן" |
| 2 | **Nickname match** *(first name only)* | 90 | "חבי" ↔ "חביבה" via nickname table |
| 3 | **Transliteration + exact** | 95 | "Ahmed" → "אחמד" == "אחמד" |
| 4 | **Transliteration + fuzzy (≥85%)** | 80 | "Alexander" → "אלכסנדר" ~ "אלכסנדר" |
| 5 | **Direct fuzzy (≥85%)** | 75 | "כהאן" ~ "כהן" = 86% |
| 6 | **Medium fuzzy (65–84%)** | 50 | Partial match |
| 7 | **Low fuzzy (45–64%)** | 25 | Weak match |
| 8 | **No match (<45%)** | 0 | Different names |

The first strategy that succeeds is used. This means an exact match stops the cascade immediately.

**Nickname matching** is only applied to first names (last name nicknames are not a meaningful pattern).

### Step 3: Weighted Combination

```
base_score = (last_name_score × 0.65) + (first_name_score × 0.35)
```

| Weight | Component | Rationale |
|--------|-----------|-----------|
| **0.65** | Last name | More discriminating, fewer possibilities |
| **0.35** | First name | Less discriminating but still important |

### Step 4: Bonuses and Penalties

| Adjustment | Value | Condition |
|-----------|-------|-----------|
| **+5** bonus | Both names are exact matches | Extra confidence when both match perfectly |
| **+5** bonus | ME and SYNC APIs agree (both ≥ 60) | Independent sources confirm each other |
| **-10** penalty | First name matches but last name doesn't | Common first name match alone is weak evidence |

### Step 5: Risk Classification

| Score Range | Tier | Recommended Action |
|------------|------|-------------------|
| **85–100** | HIGH confidence | Auto-approve |
| **60–84** | MEDIUM confidence | Manual review |
| **35–59** | LOW confidence | Flag for investigation |
| **0–34** | VERY LOW | High risk — likely not the phone owner |

## Example Audit Trails

### Example 1: Nickname Match (PASS)

```
Customer: חביבה פראס
ME API returned: Havi Prass

Last name: 'Prass' → 'פראס' == 'פראס'
  → transliteration_exact → score 95 × weight 0.65 = 61.8

First name: 'חביבה' ↔ 'Havi' (transliterated: 'חבי') via nickname(s): חבי, חביבה
  → nickname → score 90 × weight 0.35 = 31.5

Base score: 93.3
Final score: 93 → HIGH
```

### Example 2: Full Mismatch (FAIL)

```
Customer: דני לוי
ME API returned: משה כהן

Last name: 'לוי' vs 'כהן' = 0%
  → no_match → score 0 × weight 0.65 = 0.0

First name: 'דני' vs 'משה' = 22%
  → no_match → score 0 × weight 0.35 = 0.0

Base score: 0.0
Final score: 0 → VERY LOW
```

### Example 3: First Name Only (SUSPICIOUS)

```
Customer: דוד לוי
ME API returned: דוד כהן

Last name: 'לוי' vs 'כהן' = 0%
  → no_match → score 0 × weight 0.65 = 0.0

First name: 'דוד' == 'דוד'
  → exact → score 100 × weight 0.35 = 35.0

Base score: 35.0
Penalty: -10 first name matches but last name doesn't (weak evidence)
Final score: 25 → VERY LOW
```

This is important: "דוד" is a very common name. A first-name-only match with a different last name is statistically expected even for identity thieves and should NOT provide confidence.

### Example 4: Arabic Transliteration (PASS)

```
Customer: מוחמד חסן
ME API returned: محمد حسن

Last name: 'حسن' → 'חסן' == 'חסן'
  → transliteration_exact → score 95 × weight 0.65 = 61.8

First name: 'محمد' → 'מוחמד' == 'מוחמד'
  → transliteration_exact → score 95 × weight 0.35 = 33.3

Base score: 95.0
Final score: 95 → HIGH
```

## Adjustable Parameters

All weights, thresholds, and tier boundaries are stored in `scoring_config.json` and can be tuned without code changes:

- **weights.last_name / weights.first_name** — Adjust the relative importance
- **match_types.\*** — Change the score awarded for each match type
- **fuzzy_thresholds.\*** — Adjust what counts as "high", "medium", "low" fuzzy match
- **risk_tiers.\*.min** — Move the boundaries between risk tiers
- **bonuses / penalties** — Add or remove adjustments

## Statistical Rationale

The scoring formula reflects the following statistical realities:

1. **Base rate of random first-name collision is high** (~1/500 for common names like David, Mohammed). This is why first name alone gets only 35% weight and suffers a -10 penalty when the last name doesn't match.

2. **Base rate of random last-name collision is low** (~1/10,000 for most last names). This is why last name gets 65% weight and is the primary discriminator.

3. **The combination of first AND last name match is very strong** (~1/5,000,000 for non-trivial name pairs). The +5 bonus for both-exact reflects this.

4. **For a NEW phone number with no prior history**, even a partial match is more significant than for an established number (the prior probability of the legitimate owner having this name is higher). This context should be considered in manual review.
