# Character Filtering Rules

## Overview

All imported data is **silently cleaned** by removing unwanted characters. No errors are thrown - invalid characters are simply stripped.

---

## Filtering Rules

### **Names (Hebrew/Arabic/English)**

**Allowed:**
- Hebrew characters (א-ת)
- Arabic characters (ا-ي)
- English letters (a-z, A-Z)
- Spaces
- Hyphens (-)

**Stripped:**
- Numbers (0-9)
- Special characters (!@#$%^&*()_+=[]{}|;:'",.<>?/)
- Script tags, SQL keywords
- Control characters

**Examples:**
```
Input:  "דוד <script>alert(1)</script> כהן"
Output: "דוד כהן"

Input:  "David'; DROP TABLE users; --"
Output: "David DROP TABLE users"  # Then SQL keywords stripped → "David"

Input:  "محمد 123 !@# David"
Output: "محمد David"
```

### **Emails**

**Allowed:**
- Hebrew/Arabic/English letters
- Numbers (0-9)
- Email special chars: @ . _ -

**Stripped:**
- Script tags
- Spaces (emails can't have spaces)
- Other special chars

**Examples:**
```
Input:  "user@example.com<script>"
Output: "user@example.comscript"  # "script" is just text

Input:  "test user@domain.com"
Output: "testuser@domain.com"  # Space removed
```

### **Phone Numbers**

**Allowed:**
- Digits (0-9)
- Plus sign (+)

**Stripped:**
- All letters
- Dashes, spaces, parentheses
- All other characters

**Examples:**
```
Input:  "972-50-ABC-123-4567"
Output: "972501234567"

Input:  "+972 (50) 123-4567"
Output: "+972501234567"

Input:  "050-123-CALL-ME"
Output: "050123"
```

---

## Processing Pipeline

### Nicknames Upload

```
1. Read file (JSON/CSV/Excel)
2. For each formal_name:
   - Strip to Hebrew/Arabic/English/spaces/hyphens
   - Remove script tags, SQL keywords
   - Truncate to 200 chars if needed
   - HTML escape
3. For each nickname in all_names:
   - Same cleaning as formal_name
   - Join with commas
4. Insert into database
```

### Phone Data Upload

```
1. Read file (CSV/Excel)
2. For each phone number:
   - Strip to digits and + only
   - Validate length (5-15 digits)
   - If invalid, skip row
3. For each name field:
   - Strip to allowed characters
   - Truncate if needed
4. Process with APIs
```

---

## Silent Cleaning Benefits

### ✅ **User-Friendly**
- No cryptic error messages
- Data is cleaned automatically
- Users don't need to manually fix files

### ✅ **Secure**
- Malicious scripts removed
- SQL injection prevented  
- XSS attacks blocked

### ✅ **Forgiving**
- Copy-paste from Excel/WhatsApp works
- Phone numbers with formatting accepted
- Mixed language input handled

---

## Examples by Attack Type

### SQL Injection Attempt
```
Input:  formal_name = "'; DROP TABLE nicknames; --"
Step 1: Character filter → " DROP TABLE nicknames --"
Step 2: SQL keyword strip → ""
Result: Empty (row skipped)
```

### XSS Attack
```
Input:  all_names = "<script>alert(document.cookie)</script>"
Step 1: Character filter → "scriptalertdocumentcookie"
Step 2: Pattern check → (no <script> tags remain)
Result: "scriptalertdocumentcookie" (harmless text)
```

### Mixed Valid Data
```
Input:  formal_name = "דוד (David) כהן-לוי"
Step 1: Character filter → "דוד David כהן-לוי"
Result: "דוד David כהן-לוי" (valid, kept)
```

---

## Character Filter Functions

### `clean_name(text)`
Returns: Hebrew + Arabic + English + spaces + hyphens

### `clean_email(text)`
Returns: Letters + numbers + @ . _ -

### `clean_phone(text)`
Returns: Digits + plus sign

### `sanitize_string(text, field_type)`
1. Applies appropriate character filter
2. Removes script patterns
3. Removes SQL keywords
4. HTML escapes
5. Truncates if too long

---

## Edge Cases Handled

### Empty Results
```python
# If all characters stripped, row is skipped
Input:  "!@#$%^&*()"
Output: ""  → Row skipped (empty)
```

### Length Violations
```python
# Truncated instead of rejected
Input:  "A" * 5000
Output: "A" * 200  (truncated to max length)
```

### Invalid Phone Lengths
```python
# Too short or too long → return empty
Input:  "123"  # Only 3 digits
Output: ""  → Row skipped

Input:  "12345678901234567890"  # 20 digits
Output: ""  → Row skipped
```

---

## Testing

### Test Character Filters

```python
from input_validator import clean_name, clean_email, clean_phone

# Test name
assert clean_name("דוד <script>") == "דוד"

# Test email  
assert clean_email("user@test.com<evil>") == "user@test.comevil"

# Test phone
assert clean_phone("050-123-4567") == "0501234567"
```

### Test Malicious Input

```python
from input_validator import validate_nicknames_data

malicious = [
    {"formal_name": "'; DROP TABLE --", "all_names": "test"}
]

result = validate_nicknames_data(malicious)
assert len(result) == 0  # Row filtered out
```

---

## Configuration

### Adjust Allowed Characters

Edit [input_validator.py](input_validator.py):

```python
# Add more characters to names
ALLOWED_NAME_CHARS = r'[\u0590-\u05FF\u0600-\u06FFa-zA-Z\s\-\.]'  # Added .

# Add numbers to names
ALLOWED_NAME_CHARS = r'[\u0590-\u05FF\u0600-\u06FFa-zA-Z0-9\s\-]'
```

### Adjust Length Limits

```python
MAX_STRING_LENGTH = 1000   # General text
# In function calls:
sanitize_string(value, max_length=500)  # Custom limit
```

---

## Related Files

- [input_validator.py](input_validator.py) - Character filtering implementation
- [server.py](server.py) - Uses validators in upload endpoints
- [INPUT_VALIDATION.md](INPUT_VALIDATION.md) - Overall validation strategy

---

**Status:** ✅ **ACTIVE**

All file imports now silently strip unwanted characters - user-friendly and secure!
