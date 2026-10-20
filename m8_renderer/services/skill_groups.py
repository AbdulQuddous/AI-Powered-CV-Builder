"""Present explicitly labelled skill groups without rewriting stored CV data."""
import re


# Recover category boundaries flattened by older comma-based collection. Only
# these full, explicit labels are recognized inside an item; ordinary skill
# words never cause an inferred category or a change to the user's wording.
INLINE_LABELS = (
    'Programming & Fundamentals', 'Full-Stack & APIs', 'Databases & AI',
    'Development Practices & Tools', 'Web & Backend',
    'AI Integration & Databases', 'Tools & Engineering',
)
_INLINE = re.compile(r'(?<!\w)(?:' + '|'.join(map(re.escape, INLINE_LABELS)) + r')\s*:(?=\s|$)', re.I)
_LABEL = re.compile(r'^([^:\n]{1,80}):(?:\s+|$)(.*)$')


def split_skills(value):
    """Split visual list separators, retaining commas inside qualifications."""
    items, start, depth = [], 0, 0
    for index, char in enumerate(value):
        if char in '([':
            depth += 1
        elif char in ')]':
            depth = max(0, depth - 1)
        elif char in ',;·•' and depth == 0:
            item = value[start:index].strip()
            if item:
                items.append(item)
            start = index + 1
    if value[start:].strip():
        items.append(value[start:].strip())
    return items


def group_skills(skills):
    """Return labelled rows only when an explicit heading is present.

    Unlabelled lists retain the existing template treatment. No categorization,
    deduplication, skill addition or persistence takes place here.
    """
    groups = []
    current = {'label': '', 'items': []}

    def flush():
        if current['items']:
            groups.append(current.copy())
        elif current['label']:
            # A heading with no values remains visible, rather than losing text.
            groups.append({'label': '', 'items': [current['label'] + ':']})

    for value in skills:
        for line in value.splitlines():
            offsets = [match.start() for match in _INLINE.finditer(line)]
            starts = sorted(set([0, *offsets]))
            for index, start in enumerate(starts):
                end = starts[index + 1] if index + 1 < len(starts) else len(line)
                part = line[start:end].strip()
                match = _LABEL.fullmatch(part)
                label = match[1].strip() if match else ''
                if (label and label[0].isalpha()
                        and label.casefold() not in ('http', 'https', 'mailto', 'urn')):
                    flush()
                    current = {'label': label, 'items': split_skills(match[2])}
                else:
                    current['items'].extend(split_skills(part))
    flush()
    return groups if any(group['label'] for group in groups) else []
