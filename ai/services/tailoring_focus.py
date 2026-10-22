"""Small, source-bound editing briefs shared by part and whole-CV tailoring."""
import re


STOP_WORDS = set(('a an and are as at be by for from has have i in is it of on or our that the '
                 'their this to we will with work working you your experience experienced required '
                 'skills strong proficient proficiency knowledge developer engineer development '
                 'applications application systems system features feature using use build building '
                 'looking role responsibilities qualifications including modern').split())
ALIASES = {
    'apis': 'api', 'restful': 'rest', 'testing': 'test', 'tested': 'test', 'tests': 'test',
    'deploying': 'deploy', 'deployed': 'deploy', 'deployment': 'deploy',
    'integrations': 'integration', 'integrating': 'integration', 'integrated': 'integration',
    'llms': 'llm', 'models': 'model', 'databases': 'database', 'pipelines': 'pipeline',
}
PURPOSES = {
    'summary': 'Lead with the most relevant confirmed contributions, then supporting skills. Keep the actual career identity and proficiency. Synthesize only source_evidence; do not adopt the target role as an earned title.',
    'experience': 'Lead with the relevant action and contribution in this employment entry; connect the method and an existing outcome. Keep assisting, ownership, current status and all existing metrics accurate.',
    'projects': 'Lead with the relevant problem solved and the candidate contribution, then the confirmed implementation and outcome. Project experience remains project experience.',
    'achievements': 'Make the confirmed contribution and result clear, emphasizing its relevance without creating a metric or responsibility.',
}


def tokens(text):
    words = re.findall(r'[a-z][a-z0-9+#]*(?:\.[a-z0-9]+)*', text.casefold())
    return {ALIASES.get(word, word) for word in words if word not in STOP_WORDS and (len(word) > 2 or word in {'ai', 'ml', 'ui', 'ux', 'ci', 'cd'})}


def tailoring_brief(section, target_role, requirements, sources, *, selected_path=None):
    """Rank literal evidence hints, never treat keyword overlap as qualification."""
    matches = []
    for identifier, requirement in requirements.items():
        query = tokens(requirement)
        evidence = []
        for path, text in sources.items():
            overlap = query & tokens(text)
            if overlap:
                evidence.append((len(overlap), path, sorted(overlap)))
        evidence.sort(key=lambda item: (-item[0], item[1]))
        if evidence:
            matches.append((evidence[0][0], identifier, evidence))
    matches.sort(key=lambda item: -item[0])
    role_terms = tokens(target_role)
    role_paths = sorted(sources, key=lambda path: -len(role_terms & tokens(sources[path])))
    priorities = set().union(*(tokens(text) for text in requirements.values())) if requirements else role_terms
    contribution_paths = [path for path in sources if re.fullmatch(
        r'/(?:experience/\d+/highlights/\d+|projects/\d+/(?:description|highlights/\d+)|achievements/\d+)', path)
        and priorities & tokens(sources[path])]
    contribution_paths.sort(key=lambda path: -len(priorities & tokens(sources[path])))
    selected_terms = tokens(sources.get(selected_path, ''))
    return {
        'section_purpose': PURPOSES.get(section, 'Improve clarity while preserving the confirmed qualification and all factual details.'),
        'job_priorities': [{'requirement_id': identifier, 'evidence_paths': [item[1] for item in evidence[:3]],
                            'shared_terms': sorted({term for item in evidence[:3] for term in item[2]})[:12]}
                           for _, identifier, evidence in matches[:6]],
        'role_evidence_paths': [path for path in role_paths if role_terms & tokens(sources[path])][:3],
        'contribution_evidence_paths': contribution_paths[:4],
        'additional_evidence_to_consider': [path for path in contribution_paths
            if path != selected_path and tokens(sources[path]) - selected_terms][:3] if selected_path else [],
        'editing_goal': 'Reorganize relevant facts into clear, concise CV language. Prefer a relevant contribution, method and confirmed outcome to synonym substitutions. Integrate job terminology naturally only where these source facts support it. Do not stuff keywords or force a change to good text.',
        'evidence_note': 'These are lexical relevance hints, not proof of qualification. Read the actual source_evidence and JD; missing requirements are gaps, never candidate facts.',
    }
