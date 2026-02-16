#!/usr/bin/env python3
"""
Input validation and sanitization for all file imports.
Prevents SQL injection, XSS, and other attacks.
"""

import re
import html
from typing import Any, Dict, List, Optional

# Maximum file size (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Maximum rows per file
MAX_ROWS = 100000

# Maximum string length for text fields
MAX_STRING_LENGTH = 1000

# Character filters
# Hebrew: \u0590-\u05FF
# Arabic: \u0600-\u06FF
# English: a-zA-Z
# Allowed special chars: space, hyphen
ALLOWED_NAME_CHARS = r'[\u0590-\u05FF\u0600-\u06FFa-zA-Z\s\-]'

# Email-safe characters: letters, numbers, @._-
ALLOWED_EMAIL_CHARS = r'[\u0590-\u05FF\u0600-\u06FFa-zA-Z0-9@._\-]'

# Dangerous patterns to reject
DANGEROUS_PATTERNS = [
    r'<script[^>]*>',  # Script tags
    r'javascript:',     # JavaScript protocol
    r'on\w+\s*=',      # Event handlers (onclick, onerror, etc.)
    r'<iframe[^>]*>',  # Iframes
    r'eval\s*\(',      # eval() calls
    r'expression\s*\(',  # CSS expression
]

# SQL keywords that shouldn't appear in normal data
SQL_KEYWORDS = [
    'DROP TABLE', 'DELETE FROM', 'INSERT INTO', 'UPDATE SET',
    'UNION SELECT', 'EXEC ', 'EXECUTE ', '--', '/*', '*/',
    'xp_cmdshell', 'sp_executesql'
]


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


def clean_name(text: str) -> str:
    """
    Clean name field - keep only Hebrew, Arabic, English, spaces, and hyphens.
    Silently strips all other characters.

    Args:
        text: Input text

    Returns:
        Cleaned text with only allowed characters
    """
    if not text:
        return ""

    # Keep only allowed characters
    cleaned = ''.join(c for c in text if re.match(ALLOWED_NAME_CHARS, c))

    # Normalize whitespace (collapse multiple spaces)
    cleaned = ' '.join(cleaned.split())

    return cleaned.strip()


def clean_email(text: str) -> str:
    """
    Clean email field - keep only email-safe characters.
    Allows: letters (all languages), numbers, @._-

    Args:
        text: Input text

    Returns:
        Cleaned email with only allowed characters
    """
    if not text:
        return ""

    # Keep only allowed characters
    cleaned = ''.join(c for c in text if re.match(ALLOWED_EMAIL_CHARS, c))

    return cleaned.strip()


def clean_phone(text: str) -> str:
    """
    Clean phone number - keep only digits, +, and hyphens.

    Args:
        text: Input text

    Returns:
        Cleaned phone with only digits and +
    """
    if not text:
        return ""

    # Keep only digits and +
    cleaned = re.sub(r'[^\d\+]', '', str(text))

    return cleaned.strip()


def sanitize_string(value: Any, max_length: int = MAX_STRING_LENGTH, field_type: str = 'name') -> str:
    """
    Sanitize a string value for safe storage and display.

    Args:
        value: Input value (will be converted to string)
        max_length: Maximum allowed length
        field_type: Type of field ('name', 'email', 'text')

    Returns:
        Sanitized string

    Raises:
        ValidationError: If validation fails
    """
    # Convert to string
    if value is None:
        return ""

    text = str(value).strip()

    # Character filtering based on field type
    if field_type == 'name':
        text = clean_name(text)
    elif field_type == 'email':
        text = clean_email(text)
    # else: 'text' type - no character filtering, only pattern checks

    # Check length (after cleaning)
    if len(text) > max_length:
        # Truncate instead of rejecting
        text = text[:max_length]

    # Check for dangerous patterns (after cleaning, should rarely trigger)
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            # Strip the pattern instead of rejecting
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Check for SQL injection attempts
    text_upper = text.upper()
    for keyword in SQL_KEYWORDS:
        if keyword in text_upper:
            # Remove SQL keywords instead of rejecting
            text = re.sub(re.escape(keyword), '', text, flags=re.IGNORECASE)

    # HTML escape to prevent XSS
    text = html.escape(text)

    return text.strip()


def sanitize_phone(value: Any) -> str:
    """
    Sanitize a phone number.
    Silently strips all non-digit characters except +.

    Args:
        value: Phone number (string or number)

    Returns:
        Sanitized phone string (digits and + only)
    """
    if value is None:
        return ""

    # Clean phone - keeps only digits and +
    cleaned = clean_phone(str(value))

    # Check reasonable length (5-15 digits)
    # If invalid, return empty instead of error
    digits_only = cleaned.replace('+', '')
    if digits_only and (len(digits_only) < 5 or len(digits_only) > 15):
        return ""  # Invalid length - return empty

    return cleaned


def validate_nicknames_data(data: List[Dict]) -> List[Dict]:
    """
    Validate and sanitize nicknames data from imported file.

    Args:
        data: List of dicts with 'formal_name' and 'all_names' keys

    Returns:
        List of sanitized dicts

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, list):
        raise ValidationError("Data must be a list")

    if len(data) > MAX_ROWS:
        raise ValidationError(f"Too many rows: {len(data)} (max {MAX_ROWS})")

    sanitized = []

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValidationError(f"Row {i}: Entry must be a dict")

        # Check required fields
        if 'formal_name' not in entry:
            raise ValidationError(f"Row {i}: Missing 'formal_name'")

        if 'all_names' not in entry:
            raise ValidationError(f"Row {i}: Missing 'all_names'")

        # Sanitize fields - use 'name' type for character filtering
        formal_name = sanitize_string(entry['formal_name'], max_length=200, field_type='name')
        all_names = sanitize_string(entry['all_names'], max_length=1000, field_type='name')

        # Validate formal_name is not empty
        if not formal_name:
            continue  # Skip empty entries

        # Validate all_names format (comma-separated)
        if all_names:
            # Split and sanitize each nickname
            nicknames = [sanitize_string(n, max_length=100, field_type='name') for n in all_names.split(',')]
            nicknames = [n for n in nicknames if n]  # Remove empty

            if not nicknames:
                continue  # Skip if no valid nicknames

            # Rebuild sanitized all_names
            all_names = ','.join(nicknames)

        sanitized.append({
            'formal_name': formal_name,
            'all_names': all_names
        })

    return sanitized


def validate_phone_data(data: List[Dict]) -> List[Dict]:
    """
    Validate and sanitize phone data from imported file.

    Args:
        data: List of dicts with phone number and optional name fields

    Returns:
        List of sanitized dicts

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, list):
        raise ValidationError("Data must be a list")

    if len(data) > MAX_ROWS:
        raise ValidationError(f"Too many rows: {len(data)} (max {MAX_ROWS})")

    sanitized = []

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValidationError(f"Row {i}: Entry must be a dict")

        try:
            sanitized_entry = {}

            # Sanitize each field
            for key, value in entry.items():
                key_clean = sanitize_string(key, max_length=100)

                # Phone fields need special handling
                if 'phone' in key.lower() or 'tel' in key.lower():
                    sanitized_entry[key_clean] = sanitize_phone(value)
                else:
                    # Regular text fields
                    sanitized_entry[key_clean] = sanitize_string(value, max_length=500)

            sanitized.append(sanitized_entry)

        except ValidationError as e:
            raise ValidationError(f"Row {i}: {str(e)}")

    return sanitized


def validate_file_size(file_size: int) -> None:
    """
    Validate file size is within limits.

    Args:
        file_size: Size in bytes

    Raises:
        ValidationError: If file too large
    """
    if file_size > MAX_FILE_SIZE:
        raise ValidationError(
            f"File too large: {file_size / 1024 / 1024:.1f}MB "
            f"(max {MAX_FILE_SIZE / 1024 / 1024}MB)"
        )


def validate_json_structure(data: Any, expected_type: type = list) -> None:
    """
    Validate JSON structure matches expected type.

    Args:
        data: Parsed JSON data
        expected_type: Expected Python type (list, dict)

    Raises:
        ValidationError: If structure invalid
    """
    if not isinstance(data, expected_type):
        raise ValidationError(
            f"Invalid JSON structure: expected {expected_type.__name__}, "
            f"got {type(data).__name__}"
        )
