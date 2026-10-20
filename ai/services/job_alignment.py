"""Bound a Gemini job review to quoted job requirements and saved CV evidence."""
from jsonschema import Draft202012Validator
import re
from copy import deepcopy
from collections import Counter

from ai.exceptions import AIStructuredOutputError

ALIGNMENT_WARNING = 'Some job-fit notes could not be verified and were left out. Your saved CV is unchanged.'


def job_requirements(job_description):
    """Give Gemini stable references to literal JD excerpts, not a copying task."""
    requirements = {}
    for line in job_description.splitlines():
        line = line.strip().lstrip('•*- ').strip()
        if not line or line.casefold().rstrip(':') in ('key responsibilities', 'required qualifications & skills'):
            continue
        for sentence in re.split(r'(?<=[.!?])\s+', line):
            while sentence:
                excerpt = sentence[:500]
                if len(sentence) > 500 and ' ' in excerpt:
                    excerpt = excerpt.rsplit(' ', 1)[0]
                requirements[f'jd-{len(requirements) + 1}'] = excerpt
                if len(requirements) >= 32:
                    return requirements
                sentence = sentence[len(excerpt):].strip()
    return requirements


def reference_alignment_schema(requirements, paths):
    """The model selects references; the server supplies the displayed text."""
    return {
        'type': 'array', 'minItems': 1, 'maxItems': 6,
        'description': 'Select up to six important job_requirements and cite factual evidence_sources paths. Do not copy or paraphrase requirement/evidence text.',
        'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['requirement_id', 'status', 'evidence_paths'],
            'properties': {
                'requirement_id': {'type': 'string', 'enum': list(requirements)},
                'status': {'type': 'string', 'enum': ['supported', 'partial', 'missing']},
                'evidence_paths': {'type': 'array', 'maxItems': 3,
                                   'items': {'type': 'string', 'enum': list(paths)}},
            },
        },
    }


def resolve_alignment(alignment, requirements, sources):
    """Resolve only known references; malformed notes still fail strict validation."""
    if not isinstance(alignment, list):
        return alignment
    result = []
    for item in alignment:
        if not isinstance(item, dict) or 'requirement_id' not in item:
            result.append(item)  # Legacy quoted notes remain supported and checked.
            continue
        if (set(item) != {'requirement_id', 'status', 'evidence_paths'}
                or not isinstance(item['requirement_id'], str)
                or item['requirement_id'] not in requirements
                or not isinstance(item['evidence_paths'], list)
                or any(not isinstance(path, str) or path not in sources for path in item['evidence_paths'])):
            result.append({})  # Never promote unknown references into claims.
            continue
        result.append({'requirement': requirements[item['requirement_id']], 'status': item['status'],
                       'evidence': [{'path': path, 'quote': sources[path][:500].rstrip()}
                                    for path in item['evidence_paths']]})
    return result


def evidence_sources(context):
    """Expose factual text paths only; target-role metadata is never evidence."""
    sources = {}

    def visit(value, path):
        if isinstance(value, str) and value.strip():
            sources[path] = value
        elif isinstance(value, dict):
            for key, child in value.items():
                visit(child, f'{path}/{key}')
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f'{path}/{index}')

    for key, value in context.items():
        if key not in ('meta', 'personal', 'schema_version'):
            visit(value, '/' + key)
    return sources


def alignment_schema(paths):
    return {
        'type': 'array', 'minItems': 1, 'maxItems': 6,
        'description': 'The most important requirements quoted from the job description, with exact saved CV evidence or an explicit gap. This is advice, not CV content.',
        'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['requirement', 'status', 'evidence'],
            'properties': {
                'requirement': {'type': 'string', 'minLength': 1, 'maxLength': 500,
                                'description': 'A short verbatim requirement from job_description.'},
                'status': {'type': 'string', 'enum': ['supported', 'partial', 'missing']},
                'evidence': {
                    'type': 'array', 'maxItems': 3,
                    'items': {
                        'type': 'object', 'additionalProperties': False,
                        'required': ['path', 'quote'],
                        'properties': {
                            'path': {'type': 'string', 'enum': list(paths)},
                            'quote': {'type': 'string', 'minLength': 1, 'maxLength': 500,
                                      'description': 'An exact excerpt from evidence_sources[path].'},
                        },
                    },
                },
            },
        },
    }


def validate_alignment(alignment, job_description, sources):
    """Validate references on fresh and cached reviews; never save this advice."""
    if not job_description or not Draft202012Validator(alignment_schema(sources)).is_valid(alignment):
        raise AIStructuredOutputError('The job review has an invalid structure.', reason='schema_invalid')
    normalize = lambda value: ' '.join(value.split())
    seen = set()
    for item in alignment:
        requirement = normalize(item['requirement'])
        if not requirement or requirement in seen or requirement not in normalize(job_description):
            raise AIStructuredOutputError('The job review does not match the supplied job description.', reason='source_mismatch')
        seen.add(requirement)
        if bool(item['evidence']) != (item['status'] != 'missing'):
            raise AIStructuredOutputError('The job review does not identify its supporting evidence.', reason='source_mismatch')
        for evidence in item['evidence']:
            quote = normalize(evidence['quote'])
            if not quote or quote not in normalize(sources[evidence['path']]):
                raise AIStructuredOutputError('The job review evidence does not match the saved CV.', reason='source_mismatch')
    return alignment


def select_verified_notes(alignment, job_description, sources):
    """Keep independently verified notes, bounded for display, without CV edits."""
    if not isinstance(alignment, list) or not alignment:
        return [], Counter({'schema_invalid': 1})
    verified, seen, errors = [], set(), Counter()
    for raw in alignment:
        if len(verified) == 6:
            break
        note = deepcopy(raw)
        if isinstance(note, dict) and isinstance(note.get('evidence'), list):
            # The wire schema uses descriptive bounds. Retain at most three
            # distinct citations, then verify those citations against the CV.
            citations = []
            for citation in note['evidence']:
                if citation not in citations:
                    citations.append(citation)
                if len(citations) == 3:
                    break
            note['evidence'] = citations
        try:
            validate_alignment([note], job_description, sources)
        except AIStructuredOutputError as exc:
            errors[exc.reason] += 1
            continue
        key = ' '.join(note['requirement'].split())
        if key not in seen:
            seen.add(key)
            verified.append(note)
    return verified, errors
