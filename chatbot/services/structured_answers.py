"""Read explicit pasted JSON and object fragments without executing user text."""
import json
import re


def looks_structured(text):
    return text.lstrip().startswith(('{', '[', '```')) or bool(re.match(r'^\s*"[^"\n]+"\s*:', text))


def parse_structured(text):
    text = text.strip()
    fence = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.I)
    if fence:
        text = fence[1].strip()
    if re.match(r'^"[^"\n]+"\s*:', text):
        text = '{' + text.rstrip(',') + '}'

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Repeated property requires clarification.')
            result[key] = value
        return result
    try:
        result = json.loads(text, object_pairs_hook=unique_keys)
    except (ValueError, RecursionError):
        return None
    return result if isinstance(result, (dict, list)) else None


def section_list(text, section):
    """Read a labelled JSON list, or quoted list items copied without brackets.

    Only closing container punctuation may follow a copied string list. Ordinary
    prose and malformed objects are never repaired by guessing their contents.
    """
    value = parse_structured(text)
    if isinstance(value, dict):
        value = value[section] if set(value) == {section} else None
    if isinstance(value, list):
        return value
    remaining = text.strip()
    values, decoder = [], json.JSONDecoder()
    while remaining.startswith('"'):
        try:
            item, end = decoder.raw_decode(remaining)
        except ValueError:
            return None
        if not isinstance(item, str):
            return None
        values.append(item)
        remaining = remaining[end:].strip()
        if remaining.startswith(','):
            remaining = remaining[1:].strip()
        else:
            break
    return values if values and re.fullmatch(r'[\s\]},]*', remaining) else None
