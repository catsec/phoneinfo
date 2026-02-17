import json
import os


def apply_final_letter_rules(hebrew_name):
    """Replace the last letter of a Hebrew name with its final form, if applicable."""
    final_letter_map = {
        'כ': 'ך',
        'מ': 'ם',
        'נ': 'ן',
        'פ': 'ף',
        'צ': 'ץ'
    }
    if hebrew_name and hebrew_name[-1] in final_letter_map:
        hebrew_name = hebrew_name[:-1] + final_letter_map[hebrew_name[-1]]
    return hebrew_name


def transliterate_name(word):
    """Transliterate a name to Hebrew, auto-detecting the source language."""
    if not word:
        return ''

    language = detect_language(word)

    if language == "ar":
        return arabic_to_hebrew(word)
    elif language == "en":
        return english_to_hebrew(word)
    elif language == "ru":
        return russian_to_hebrew(word)
    elif language == "he":
        return word
    else:
        return word


def russian_to_hebrew(name):
    transliteration_map = {
        'А': 'א', 'а': 'א', 'Б': 'ב', 'б': 'ב', 'В': 'ו', 'в': 'ו', 'Г': 'ג', 'г': 'ג',
        'Д': 'ד', 'д': 'ד', 'Е': 'א', 'е': 'א', 'Ё': 'יו', 'ё': 'יו', 'Ж': 'ז', 'ж': 'ז',
        'З': 'ז', 'з': 'ז', 'И': 'י', 'и': 'י', 'Й': 'י', 'й': 'י', 'К': 'ק', 'к': 'ק',
        'Л': 'ל', 'л': 'ל', 'М': 'מ', 'м': 'מ', 'Н': 'נ', 'н': 'נ', 'О': 'ו', 'о': 'ו',
        'П': 'פ', 'п': 'פ', 'Р': 'ר', 'р': 'ר', 'С': 'ס', 'с': 'ס', 'Т': 'ת', 'т': 'ת',
        'У': 'ו', 'у': 'ו', 'Ф': 'פ', 'ф': 'פ', 'Х': 'ח', 'х': 'ח', 'Ц': 'צ', 'ц': 'צ',
        'Ч': 'צ', 'ч': 'צ', 'Ш': 'ש', 'ш': 'ש', 'Щ': 'שצ', 'щ': 'שצ', 'Ъ': '', 'ъ': '',
        'Ы': 'י', 'ы': 'י', 'Ь': '', 'ь': '', 'Э': 'א', 'э': 'א', 'Ю': 'יו', 'ю': 'יו',
        'Я': 'יא', 'я': 'יא', ' ': ' '
    }
    hebrew_name = ''.join(transliteration_map.get(char, '') for char in name)
    return apply_final_letter_rules(hebrew_name)


def arabic_to_hebrew(name):
    transliteration_map = {
        'ا': 'א', 'ب': 'ב', 'ت': 'ת', 'ث': 'ת', 'ج': 'ג', 'ح': 'ח', 'خ': 'ח',
        'د': 'ד', 'ذ': 'ד', 'ر': 'ר', 'ز': 'ז', 'س': 'ס', 'ش': 'ש', 'ص': 'צ',
        'ض': 'צ', 'ط': 'ט', 'ظ': 'ט', 'ع': 'ע', 'غ': 'ע', 'ف': 'פ', 'ق': 'ק',
        'ك': 'כ', 'ل': 'ל', 'م': 'מ', 'ن': 'נ', 'ه': 'ה', 'و': 'ו', 'ي': 'י',
        'ء': 'א', 'أ': 'א', 'إ': 'א', 'ؤ': 'ו', 'ئ': 'א', 'ى': 'א', 'ة': 'ה',
        'آ': 'א', ' ': ' '
    }
    hebrew_name = ''.join(transliteration_map.get(char, '') for char in name)
    return apply_final_letter_rules(hebrew_name)


# Cache loaded names
_common_names_cache = None
_structured_names_cache = None


def load_common_names_json(json_path="names.json"):
    """Load structured name mappings from JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            structured_data = json.load(f)

        flat_lookup = {}
        for hebrew_name, variants in structured_data.items():
            for lang_field in ['english', 'arabic', 'russian', 'russian_cyrillic']:
                variants_list = variants.get(lang_field)
                if variants_list:
                    for variant in variants_list:
                        flat_lookup[variant.lower().strip()] = hebrew_name

        return flat_lookup, structured_data

    except FileNotFoundError:
        return {}, {}


def get_common_names():
    """Get common names lookup dict, loading from file if needed."""
    global _common_names_cache, _structured_names_cache

    if _common_names_cache is None:
        flat_lookup, structured_data = load_common_names_json("names.json")
        _common_names_cache = flat_lookup if flat_lookup else {}
        _structured_names_cache = structured_data if structured_data else {}

    return _common_names_cache


def get_structured_names():
    """Get structured name data organized by Hebrew name."""
    global _structured_names_cache

    if _structured_names_cache is None:
        get_common_names()

    return _structured_names_cache


def get_names_for_db_import():
    """Get all names in a database-ready format."""
    structured = get_structured_names()

    db_records = []
    for hebrew_name, variants in structured.items():
        record = {
            'hebrew': hebrew_name,
            'english_variants': ','.join(variants['english']) if variants['english'] else None,
            'arabic_variants': ','.join(variants['arabic']) if variants['arabic'] else None,
            'russian_variants': ','.join(variants['russian']) if variants['russian'] else None,
            'russian_cyrillic_variants': ','.join(variants['russian_cyrillic']) if variants['russian_cyrillic'] else None
        }
        db_records.append(record)

    return db_records


def english_to_hebrew(name):
    """Transliterate English names to Hebrew."""
    name_lower = name.lower().strip()
    common_names = get_common_names()
    if name_lower in common_names:
        return common_names[name_lower]

    transliteration_map = {
        'a': '', 'b': 'ב', 'c': 'ק', 'd': 'ד', 'e': '', 'f': 'פ', 'g': 'ג', 'h': 'ה',
        'i': 'י', 'j': 'ג׳', 'k': 'ק', 'l': 'ל', 'm': 'מ', 'n': 'נ', 'o': 'ו', 'p': 'פ',
        'q': 'ק', 'r': 'ר', 's': 'ס', 't': 'ת', 'u': 'ו', 'v': 'ו', 'w': 'ו', 'x': 'קס',
        'y': 'י', 'z': 'ז', ' ': ' '
    }
    multi_char_map = {
        'ch': 'ח', 'sh': 'ש', 'th': 'ת', 'kh': 'ח', 'ph': 'פ',
        'oo': 'ו', 'ee': 'י', 'ei': 'יי', 'ie': 'י', 'ou': 'ו',
        'ai': 'יי', 'ay': 'יי', 'ey': 'יי', 'ae': 'יי',
        'ck': 'ק',
        'tt': 'ת', 'dd': 'ד', 'nn': 'נ', 'mm': 'מ', 'ss': 'ס',
        'll': 'ל', 'rr': 'ר', 'ff': 'פ', 'pp': 'פ', 'bb': 'ב', 'gg': 'ג', 'cc': 'ק',
    }
    hebrew_name = ''
    i = 0
    while i < len(name):
        found = False
        for multi_char in sorted(multi_char_map.keys(), key=len, reverse=True):
            if name[i:i + len(multi_char)].lower() == multi_char:
                hebrew_name += multi_char_map[multi_char]
                i += len(multi_char)
                found = True
                break
        if not found:
            char = name[i].lower()
            if char in {'a', 'e', 'o', 'u'} and i == 0:
                hebrew_name += 'א'
            else:
                hebrew_name += transliteration_map.get(char, '')
            i += 1
    if name.lower().endswith('a'):
        if hebrew_name.endswith('א'):
            hebrew_name = hebrew_name[:-1] + 'ה'
        else:
            hebrew_name += 'ה'
    return apply_final_letter_rules(hebrew_name)


def detect_language(word):
    """Detect the language of a word based on Unicode ranges."""
    hebrew_range = range(0x0590, 0x05FF + 1)
    arabic_range = range(0x0600, 0x06FF + 1)
    english_range = list(range(0x0041, 0x005A + 1)) + list(range(0x0061, 0x007A + 1))
    russian_range = range(0x0400, 0x04FF + 1)

    for char in word:
        code_point = ord(char)
        if code_point in hebrew_range:
            return "he"
        elif code_point in arabic_range:
            return "ar"
        elif code_point in english_range:
            return "en"
        elif code_point in russian_range:
            return "ru"

    return "other"


def is_hebrew(text):
    """Check if text contains Hebrew characters."""
    if not text or not text.strip():
        return False
    for word in text.split():
        if word and detect_language(word) == "he":
            return True
    return False
