import requests


def call_api(phone, api_url, sid, token):
    """Call the ME API to look up phone number information."""
    url = f"{api_url}?phone_number={phone}&sid={sid}&token={token}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        return None
    else:
        raise ValueError(f"API call failed for phone number {phone} with status code {response.status_code}")


def flatten_user_data(api_result, prefix="me"):
    """
    Flatten nested ME API result and replace None with an empty string.
    All columns are prefixed with the API name (e.g., me.common_name).
    """
    def replace_none(value):
        return "" if value is None else value

    user_data = api_result.get("user", {}) or {}
    social_profiles = user_data.get("social_profiles", {}) or {}
    user_keys = ["profile_picture", "first_name", "last_name", "email", "email_confirmed", "gender", "is_verified", "slogan"]
    social_keys = ["facebook", "twitter", "spotify", "instagram", "linkedin", "pinterest", "tiktok"]

    flattened_data = {
        f"{prefix}.common_name": replace_none(api_result.get("common_name", "")),
        f"{prefix}.profile_name": replace_none(api_result.get("me_profile_name", "")),
        f"{prefix}.result_strength": replace_none(api_result.get("result_strength", "")),
        **{f"{prefix}.{k}": replace_none(user_data.get(k, "")) for k in user_keys},
        **{f"{prefix}.social.{k}": replace_none(social_profiles.get(k, "")) for k in social_keys},
        f"{prefix}.whitelist": replace_none(api_result.get("whitelist", "")),
        f"{prefix}.api_call_time": "",
    }

    return flattened_data
