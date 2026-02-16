import requests


def call_api(phone, api_url, token):
    """Call the SYNC API to look up phone number information."""
    # Phone must be international format without + prefix
    phone = phone.lstrip('+')

    payload = {
        "access_token": token,
        "phone_number": phone
    }

    response = requests.post(api_url, json=payload)

    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        return None
    elif response.status_code == 400:
        raise ValueError(f"Invalid phone number: {phone}")
    elif response.status_code == 403:
        raise ValueError("API rate limit or request limit reached")
    else:
        raise ValueError(f"API call failed for phone number {phone} with status code {response.status_code}")


def flatten_user_data(api_result, prefix="sync"):
    """
    Flatten SYNC API result and extract all fields.
    All columns are prefixed with the API name (e.g., sync.first_name).
    """
    def replace_none(value):
        return "" if value is None else value

    results = api_result.get("results", {}) or {}
    full_name = results.get("name", "") or ""

    # Split name into first and last
    name_parts = full_name.strip().split(maxsplit=1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    flattened_data = {
        f"{prefix}.name": replace_none(full_name),
        f"{prefix}.first_name": replace_none(first_name),
        f"{prefix}.last_name": replace_none(last_name),
        f"{prefix}.is_potential_spam": replace_none(results.get("is_potential_spam", "")),
        f"{prefix}.is_business": replace_none(results.get("is_business", "")),
        f"{prefix}.job_hint": replace_none(results.get("job_hint", "")),
        f"{prefix}.company_hint": replace_none(results.get("company_hint", "")),
        f"{prefix}.website_domain": replace_none(results.get("website_domain", "")),
        f"{prefix}.company_domain": replace_none(results.get("company_domain", "")),
        f"{prefix}.api_call_time": "",
    }

    return flattened_data
