def validate_phone_numbers(phone_numbers):
    """Validate that all phone numbers are in international format (972XXXXXXXXX)."""
    for phone in phone_numbers:
        if not str(phone).isdigit() or not str(phone).startswith("972") or len(str(phone)) != 12:
            return False
    return True


def convert_to_local(phone):
    """Convert international format (972XXXXXXXXX) to local Israeli format (0XXXXXXXXX)."""
    phone_str = str(phone).strip()
    if phone_str.startswith("972") and len(phone_str) == 12:
        return "0" + phone_str[3:]
    return phone_str


def convert_to_international(phone_numbers):
    """Convert local Israeli phone numbers to international format."""
    converted_numbers = []
    for phone in phone_numbers:
        phone_str = str(phone).strip()
        if len(phone_str) == 10 and phone_str.startswith("0"):
            phone_str = "972" + phone_str[1:]
        elif len(phone_str) == 9 and phone_str.startswith("5"):
            phone_str = "972" + phone_str
        converted_numbers.append(phone_str)
    return converted_numbers
