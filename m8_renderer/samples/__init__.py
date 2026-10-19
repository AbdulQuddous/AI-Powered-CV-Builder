"""Synthetic, M10-compatible examples. Never read private CV records here."""
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

PROFILES = {
    'backend': ('Python Backend Developer', 'experienced', ['Python', 'Django', 'PostgreSQL', 'Docker']),
    'graduate': ('Software Engineering Graduate', 'fresher', ['Python', 'JavaScript', 'Git', 'Testing']),
    'analyst': ('Data Analyst', 'experienced', ['SQL', 'Python', 'Data visualisation', 'Statistics']),
    'marketing': ('Marketing Specialist', 'experienced', ['Content strategy', 'Campaign analytics', 'SEO', 'Copywriting']),
    'administrator': ('Business Administrator', 'experienced', ['Office operations', 'Scheduling', 'Excel', 'Communication']),
    'designer': ('Graphic Designer', 'experienced', ['Typography', 'Brand identity', 'Figma', 'Art direction']),
    'manager': ('Project Manager', 'experienced', ['Project planning', 'Risk management', 'Agile', 'Stakeholder communication']),
    'senior': ('Senior Software Engineer', 'experienced', ['System design', 'Python', 'Mentoring', 'Distributed systems']),
}

@lru_cache(maxsize=1)
def _comparison():
    return json.loads(Path(__file__).with_name('comparison.json').read_text())


def sample_cv(profile='comparison'):
    cv = deepcopy(_comparison())
    if profile in PROFILES:
        role, level, skills = PROFILES[profile]
        cv['meta'].update(target_role=role, career_level=level)
        cv['skills'] = skills
        cv['summary'] = f'{role} focused on clear communication, reliable delivery, and practical problem-solving. Collaborates across teams to turn complex requirements into useful outcomes.'
        cv['experience'][0]['job_title'] = role
        cv['experience'][0]['highlights'] = ['Coordinated a cross-functional initiative from discovery through delivery.', 'Documented repeatable processes and shared practical guidance with colleagues.']
        cv['experience'][1]['job_title'] = 'Team Assistant' if level == 'fresher' else role
        cv['experience'][1]['highlights'] = ['Supported project delivery, tracked progress, and communicated updates to stakeholders.']
        cv['projects'][0].update(name='Community Collaboration Initiative', description='A volunteer project improving access to community resources.', technologies=skills[:3], highlights=['Gathered feedback and delivered an accessible, clearly documented outcome.'])
        if level == 'fresher':
            cv['experience'] = []
    return cv
