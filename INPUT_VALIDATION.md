# Input Validation & Security

## Overview

Comprehensive input validation protects against malicious file uploads and data injection attacks.

---

## Security Threats Mitigated

### 1. **SQL Injection** ✅
- Detects SQL keywords in user input
- Blocks: `DROP TABLE`, `DELETE FROM`, `UNION SELECT`, etc.
- All database queries use parameterized statements (already implemented)

### 2. **Cross-Site Scripting (XSS)** ✅
- Detects dangerous HTML/JavaScript patterns
- Blocks: `<script>`, `javascript:`, `<iframe>`, `onclick=`, etc.
- HTML-escapes all user input before storage

### 3. **Denial of Service (DoS)** ✅
- File size limit: 50MB
- Row count limit: 100,000 rows
- String length limits (200-1000 chars per field)

### 4. **Path Traversal** ✅
- Uses `werkzeug.secure_filename()` on all uploads
- Validates file extensions with whitelist

### 5. **Data Injection** ✅
- Schema validation for JSON/CSV/Excel files
- Type validation (phone numbers must be digits)
- Field sanitization before database insertion

---

## Implementation

### Validator Module: `input_validator.py`

**Core Functions:**

```python
sanitize_string(value, max_length)
- HTML escapes to prevent XSS
- Blocks SQL injection patterns
- Blocks dangerous HTML patterns
- Enforces length limits

sanitize_phone(value)
- Validates phone number format
- Allows only: digits, +, -, (), spaces
- Enforces reasonable length (5-15 digits)

validate_nicknames_data(data)
- Validates list structure
- Enforces max 100,000 rows
- Sanitizes formal_name and all_names
- Skips invalid/empty entries

validate_phone_data(data)
- Validates phone file imports
- Sanitizes all fields based on type
- Phone fields get special validation

validate_file_size(file_size)
- Enforces 50MB limit
- Prevents memory exhaustion attacks
```

### Protected Endpoints

**1. Nicknames Upload** ([server.py:1766](server.py))
```python
@app.route("/web/nicknames/upload", methods=["POST"])
- Validates file size (50MB max)
- Sanitizes all formal_name and all_names fields
- Validates JSON/CSV/Excel structure
- HTML-escapes before database insertion
```

**2. Phone Data Upload** ([server.py:1229](server.py))
```python
@app.route("/web/process", methods=["POST"])
- Validates file size (50MB max)
- Enforces row limit (100,000 max)
- Validates 3-column structure
- Phone validation via convert_israeli_phone()
```

**3. Nickname Management**
- `/web/nicknames/save` - Validates before update
- `/web/nicknames/edit` - Sanitizes output
- `/web/nicknames/delete` - Protected by authentication

---

## Validation Rules

### Phone Numbers
```python
Valid:   "972-50-123-4567", "+972501234567", "050-123-4567"
Invalid: "<script>alert(1)</script>", "../../etc/passwd"
Result:  "972501234567" (digits + plus only)
```

### Names (Hebrew/English/Arabic)
```python
Valid:   "דוד כהן", "محمد علي", "John Smith"
Invalid: "<script>", "'; DROP TABLE", "onclick='alert(1)'"
Result:  HTML-escaped, safe for display
```

### Nicknames Format
```python
Valid:   "אבי,אברום,אברם" (comma-separated)
Invalid: Empty, SQL keywords, script tags
Result:  Sanitized, sorted, deduplicated
```

---

## Example Attacks Blocked

### Attack 1: SQL Injection in Nickname
```json
{
  "formal_name": "'; DROP TABLE nicknames; --",
  "all_names": "test"
}
```
**Result:** ❌ Rejected - "Suspicious SQL keyword detected: DROP TABLE"

### Attack 2: XSS in Name Field
```json
{
  "formal_name": "דוד",
  "all_names": "<script>alert(document.cookie)</script>"
}
```
**Result:** ❌ Rejected - "Dangerous pattern detected: <script>"

### Attack 3: DoS via Large File
```bash
# Upload 200MB Excel file
```
**Result:** ❌ Rejected - "File too large: 200MB (max 50MB)"

### Attack 4: Schema Manipulation
```json
[
  {"formal_name": "test"},  # Missing all_names
  {"unexpected_field": "malicious"}  # Unexpected structure
]
```
**Result:** ❌ Rejected - "Missing 'all_names'" or "Entry must be a dict"

---

## Testing

### Manual Test
```bash
cd /path/to/phoneinfo
python input_validator.py

# Expected output:
# ✅ PASS: XSS blocked
# ✅ PASS: SQL injection blocked
# ✅ PASS: Valid data accepted
```

### Integration Test
```python
# Test malicious nickname upload
import requests

malicious_data = [
    {"formal_name": "<script>alert(1)</script>", "all_names": "test"}
]

response = requests.post(
    "http://localhost:5001/web/nicknames/upload",
    files={"file": ("evil.json", json.dumps(malicious_data))},
    cookies={"session": "your_session"}
)

# Expected: 400 Bad Request with validation error
```

---

## Security Checklist

- [x] File size limits enforced (50MB)
- [x] Row count limits enforced (100,000)
- [x] SQL injection detection active
- [x] XSS pattern detection active
- [x] HTML escaping on all user input
- [x] Phone number format validation
- [x] Schema validation for JSON imports
- [x] Secure filename handling (werkzeug.secure_filename)
- [x] Type validation (strings, phones)
- [x] Length limits on all fields

---

## Maintenance

### Adding New Upload Endpoints

When adding new file upload functionality:

1. **Import validator:**
   ```python
   from input_validator import validate_file_size, ValidationError
   ```

2. **Validate file size:**
   ```python
   file.seek(0, 2)
   validate_file_size(file.tell())
   file.seek(0)
   ```

3. **Sanitize data:**
   ```python
   from input_validator import sanitize_string
   safe_value = sanitize_string(user_input)
   ```

4. **Handle validation errors:**
   ```python
   except ValidationError as e:
       return jsonify({"error": f"Validation error: {e}"}), 400
   ```

---

## Future Enhancements

Consider adding:

1. **Rate limiting per user** - Limit upload frequency
2. **Virus scanning** - Integrate ClamAV for file scanning
3. **Content-Type validation** - Verify MIME types match extensions
4. **Audit logging** - Log all validation failures with IP
5. **Quarantine system** - Store suspicious files for review

---

## Related Documentation

- [SECURITY.md](SECURITY.md) - Overall security documentation
- [server.py](server.py) - Main application with protected endpoints
- [input_validator.py](input_validator.py) - Validation implementation

---

**Status:** ✅ **PROTECTED**

All file upload endpoints now validate and sanitize input to prevent malicious data injection.
