def validate_phone_numbers(phone_numbers):
    """Validate that all phone numbers are in international format (972XXXXXXXXX)."""
    for phone in phone_numbers:
        if not str(phone).isdigit() or not str(phone).startswith("972") or len(str(phone)) != 12:
            return False
    return True


def convert_to_international(phone_numbers):
    """Convert local Israeli phone numbers to international format."""
    converted_numbers = []
    for phone in phone_numbers:
        phone_str = str(phone).strip()
        if len(phone_str) == 10 and phone_str.startswith("0"):
            phone_str = "972" + phone_str[1:]
        converted_numbers.append(phone_str)
    return converted_numbers
