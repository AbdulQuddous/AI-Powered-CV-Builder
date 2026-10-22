"""Keep synthesized actions attached to the candidate's actual source prose.

These checks supplement the wording guard. A skill or job title establishes no
deployment or leadership, and an action by another person is not the candidate's.
"""
import re


_NON_PROSE = {
    'meta', 'personal', 'schema_version', 'skills', 'technologies', 'technology',
    'tools', 'name', 'full_name', 'job_title', 'title', 'company', 'employer',
    'institution', 'degree', 'field_of_study', 'specialization', 'issuer',
    'location', 'url', 'email', 'phone', 'linkedin', 'github', 'portfolio',
    'start_date', 'end_date', 'date', 'graduation_year', 'is_current', 'grade',
    'career_level', 'target_role', 'template_id', 'proficiency', 'language',
}
_ISO_DATE = re.compile(r'(?<!\d)\d{4}-\d{2}(?:-\d{2})?(?!\d)')
_ACTIONS = {
    'leadership': re.compile(r'\b(?:led|leads?|leading|managed|managing|supervised|supervising|oversaw|mentored|mentoring|directed|spearheaded)\b', re.I),
    'deployment': re.compile(r'\bdeploy(?:ed|ing|s|ments?)?\b', re.I),
    'training': re.compile(r'\b(?:train(?:ed|ing|s)?|fine[ -]?tun(?:ed|ing|es?))\b', re.I),
    'maintenance': re.compile(r'\b(?:maintain(?:ed|ing|s)?|maintenance|operat(?:ed|es|ing)|administer(?:ed|ing))\b', re.I),
    'architecture': re.compile(r'\b(?:architect(?:ed|ing|s)?|architectur(?:e|al))\b', re.I),
}
_COORDINATED_ACTION = (
    r'(?:deploy(?:ed|ing|s)?|train(?:ed|ing|s)?|fine[ -]?tun(?:ed|ing)|'
    r'maintain(?:ed|ing|s)?|architect(?:ed|ing|s)?|led|leading|managed|'
    r'built|building|developed|developing|created|creating|implemented|'
    r'tested|testing|reviewed|reviewing|reduced|reducing|designed|designing)'
)
_SENTENCES = re.compile(r'\n+|;|(?<=[.!?])\s+(?=[A-Z])')
_CLAUSES = re.compile(r'\b(?:and|while|but|then)\s+(?=(?:(?:I|we)\s+)?' + _COORDINATED_ACTION + r'\b)', re.I)
_SUPPORT = re.compile(r'\b(?:assisted|helped|supported|contributed|assisting|helping|supporting)\b', re.I)
_NON_CANDIDATE = re.compile(
    r'\b(?:observed|shadowed|watched|learned about|studied|planned to|intend(?:ed)? to|'
    r'hope(?:d)? to|will|would|could|should|did not|have not|never|not yet)\b', re.I)
_OTHER_ACTOR = re.compile(
    r'\b(?:team|manager|colleague|mentor|supervisor|instructor|engineer|developer|'
    r'system|service|application|model|company)\s+(?:(?:who|which|that)\s+)?'
    r'(?:(?:is|was|were|are|has|had)\s+)?$', re.I)


def claim_text(evidence):
    """Return prose only; labels, listed skills and dates are not action evidence."""
    if isinstance(evidence, str):
        return _ISO_DATE.sub('', evidence)
    if isinstance(evidence, (list, tuple)):
        return '\n'.join(filter(None, (claim_text(item) for item in evidence)))
    if isinstance(evidence, dict):
        return '\n'.join(filter(None, (
            claim_text(value) for key, value in evidence.items()
            if str(key).casefold() not in _NON_PROSE
            and not re.search(r'(?:^|_)(?:date|name|title|url|skills|technologies)(?:_|$)', str(key), re.I)
        )))
    return ''


def _clauses(text):
    for sentence in _SENTENCES.split(text):
        for clause in _CLAUSES.split(sentence):
            clause = clause.strip(' \t,.:•*-')
            if clause:
                yield clause


def _actor(clause, match, family):
    """Recognize direct CV verbs and keep explicit assistance as assistance."""
    prefix, suffix = clause[:match.start()], clause[match.end():]
    if _NON_CANDIDATE.search(prefix):
        return None
    # "Worked with a team led by its manager" belongs to the manager.
    if re.match(r'\s+by\b', suffix, re.I) and not re.match(r'\s+by\s+(?:me|us)\b', suffix, re.I):
        return None
    other = _OTHER_ACTOR.search(prefix)
    if other and (re.search(r'\b(?:team|manager|colleague|mentor|supervisor|instructor|system|service|application|model|company)\b', other[0], re.I)
                  or re.search(r'\b(?:with|for|of|by|whose)\b', prefix[:other.start()], re.I)):
        return None
    if re.search(r'\b(?:worked|working)\s+(?:on|with)\b', prefix, re.I):
        return 'support'
    if _SUPPORT.search(prefix):
        return 'support'
    # A training dataset/deployment dashboard does not say the author trained
    # models or deployed an application. Explicit action verbs do.
    nominal = (family == 'deployment' and re.fullmatch(r'deployments?', match[0], re.I)) or (
        family == 'maintenance' and match[0].casefold() == 'maintenance')
    if nominal and not re.search(r'\b(?:responsible for|performed|handled|managed|delivered|implemented)\b', prefix, re.I):
        return None
    if family == 'training' and match[0].casefold() == 'training' and re.match(
            r'\s+(?:data|datasets?|materials?|courses?|scripts?|pipelines?|dashboards?)\b', suffix, re.I):
        return None
    if family == 'architecture' and re.fullmatch(r'architectur(?:e|al)', match[0], re.I) and not re.search(
            r'\b(?:designed|designing|created|developed|responsible for|defined|implemented)\b', prefix, re.I):
        return None
    return 'direct'


def _records(text):
    # Lazy imports avoid a cycle when tailoring imports this module's helpers.
    from ai.services.tailoring import named_terms, normalized_technical_text

    result = []
    for clause in _clauses(normalized_technical_text(text)):
        for family, pattern in _ACTIONS.items():
            for match in pattern.finditer(clause):
                actor = _actor(clause, match, family)
                if not actor:
                    continue
                # Summary identity before the action is not a tool association.
                # A "Using Docker, deployed ..." preamble does associate a tool.
                associated = clause if re.match(r'(?:using|with|via|on)\b', clause, re.I) else clause[match.start():]
                terms = named_terms(associated)
                terms -= {word.casefold() for expression in _ACTIONS.values() for word in expression.findall(associated)}
                result.append((family, actor, terms))
    return result


def unsupported_action_association(original, rewritten, evidence):
    """Reject newly joined action/tool facts unless one source clause joins them.

    Existing associations stay usable. New deployment, training, leadership,
    maintenance or architecture must be stated by the candidate in prose, with
    the same named tools; unrelated list items cannot complete that evidence.
    """
    old, sources = _records(original), _records(claim_text(evidence))
    for family, actor, terms in _records(rewritten):
        def supports(record):
            source_family, source_actor, source_terms = record
            return (source_family == family and (actor == 'support' or source_actor == 'direct')
                    and terms <= source_terms)

        if not any(supports(record) for record in old) and not any(supports(record) for record in sources):
            return True
    return False
