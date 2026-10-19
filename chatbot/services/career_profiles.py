"""M5 interview profiles mapped onto the unchanged M10 career-level enum."""
import re

PROFILES = {
    'student': ('Student', 'other'),
    'fresher': ('Fresher', 'fresher'),
    'junior': ('Junior', 'experienced'),
    'mid_level': ('Mid-Level', 'experienced'),
    'senior': ('Senior', 'experienced'),
    'executive': ('Executive', 'experienced'),
    'other': ('Other', 'other'),
}
ALIASES = {'mid': 'mid_level', 'midlevel': 'mid_level', 'experienced': 'mid_level',
           'experienced professional': 'mid_level', 'fresh graduate': 'fresher'}


def profile_name(value):
    if not isinstance(value, str):
        return None
    label = re.sub(r'[\s-]+', '_', value.strip().casefold())
    label = ALIASES.get(label, ALIASES.get(value.strip().casefold(), label))
    return label if label in PROFILES else None


def career_profile(state):
    return profile_name(state.get('question_profile')) or profile_name(state.get('career_level')) or 'other'


def normalize_profile(state):
    """Normalize creation input without storing any profile in canonical CV data."""
    selected = profile_name(state.get('career_level'))
    if selected:
        state['career_level'] = PROFILES[selected][1]
        state['question_profile'] = profile_name(state.get('question_profile')) or selected
    return state
