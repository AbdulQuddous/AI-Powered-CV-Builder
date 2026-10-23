"""Advisory M5 guidance over confirmed source facts. Never writes CV content."""
from copy import deepcopy
from hashlib import sha256
import json
import re

from rest_framework.exceptions import ValidationError
from chatbot.services.career_profiles import career_profile, PROFILES
from chatbot.services.field_validation import unique_skills
from chatbot.services.role_guidance import ROLES, COMPARISON_ALIASES, SENIOR_SKILLS, EXECUTIVE_SKILLS

EARLY = {'student', 'fresher'}
TECHNICAL = {'backend', 'frontend', 'fullstack', 'ai_ml', 'data', 'devops', 'security', 'java', 'node', 'dotnet'}
GENERAL_SKILLS = ('Communication', 'Problem solving', 'Research', 'Data literacy', 'Time management',
                  'Teamwork', 'Planning', 'Documentation', 'Critical thinking', 'Presentation')


def guidance_request(text):
    text = ' '.join(text.strip().casefold().split()).rstrip('.!?')
    if text in ('cv suggestions', 'career suggestions', 'suggestions', 'help with my cv',
                'how can i improve my cv', 'how can i shorten my cv'):
        return 'all'
    if text in ('remove duplicate skills', 'remove unrelated skills'):
        return 'skills'  # Advice is not permission to decide which facts to delete.
    match = re.fullmatch(r'(?:(?:please|can you|could you)\s+)?(?:suggest|recommend|prioriti[sz]e|help me choose)\s+'
                         r'(?:my\s+)?(skills|experiences?|projects?|certifications?|education|cv|resume)'
                         r'(?:\s+(?:for my cv|for this role|for my target role))?', text)
    if not match:
        match = re.fullmatch(r'(?:what|which)\s+(skills|experiences?|projects?|certifications?|education)\s+'
                             r'should i (?:include|highlight|prioriti[sz]e|add)(?: in my cv)?', text)
    if not match:
        return None
    noun = match[1]
    return {'experience': 'experience', 'experiences': 'experience', 'project': 'projects',
            'certification': 'certifications', 'cv': 'all', 'resume': 'all'}.get(noun, noun)


def comparable(value):
    value = unique_skills([value])[0] if value.strip() else ''
    value = ' '.join(value.casefold().split())
    return COMPARISON_ALIASES.get(value, value)


def contains(text, term):
    return bool(re.search(r'(?<!\w)' + re.escape(term.casefold()) + r'(?!\w)', text.casefold()))


def role_families(role):
    role = re.sub(r'[/_\-]+', ' ', role.casefold())
    matches = [key for key, row in ROLES.items() if any(contains(role, word) for word in row['roles'])]
    if len(matches) > 1 and 'fullstack' in matches:
        matches.remove('fullstack')
    if any(key in matches for key in ('java', 'node', 'dotnet')) and 'backend' in matches:
        matches.remove('backend')
    return matches


def guidance_data(state):
    """Use existing sparse merges so guidance also sees saved facts during edits."""
    from cvs.chat_import import merge_entries, IDENTITIES
    if state.get('mode') != 'edit_existing':
        data = deepcopy(state.get('collected_data') or {})
    else:
        data = deepcopy(state.get('existing_cv') or {})
        data.setdefault('projects', []).extend(deepcopy(state.get('edit_new_projects') or []))
        for section, value in (state.get('edit_updates') or {}).items():
            if not value:
                continue
            if section in IDENTITIES:
                entries = data.get(section) or []
                if section == 'experience':
                    entries = [dict(entry, role=entry.get('job_title', '')) for entry in entries]
                try:
                    data[section] = merge_entries(entries, value, section)
                except ValidationError:
                    continue  # Ambiguous edits are not invented or double-counted.
            elif section == 'skills':
                data[section] = unique_skills((data.get(section) or []) + value)
            elif section == 'personal':
                data.setdefault(section, {}).update(value)
            else:
                data[section] = deepcopy(value)
    for patch in state.get('entry_patches') or []:
        entries = data.get(patch['section']) or []
        if 0 <= patch['index'] < len(entries):
            entries[patch['index']].update(deepcopy(patch['updates']))
    removed = {comparable(value) for value in state.get('removed_skills') or []}
    data['skills'] = [value for value in data.get('skills') or [] if comparable(value) not in removed]
    return data


def candidate_skills(state):
    families = role_families(state.get('target_role') or '')
    pools = [ROLES[key]['skills'] for key in families] or [GENERAL_SKILLS]
    # Interleave multi-domain roles rather than letting one domain crowd out another.
    candidates = []
    for i in range(max(map(len, pools))):
        for pool in pools:
            if i < len(pool) and pool[i] not in candidates:
                candidates.append(pool[i])
    level = career_profile(state)
    if level == 'executive':
        candidates = list(EXECUTIVE_SKILLS) + candidates
    elif level == 'senior':
        extra = SENIOR_SKILLS if set(families) & TECHNICAL else ('Mentoring', 'Stakeholder management')
        candidates = list(extra) + candidates
    return unique_skills(candidates)[:15]


def skill_advice(state, data, *, include_count=True):
    skills = data.get('skills') or []
    families = role_families(state.get('target_role') or '')
    candidates = candidate_skills(state)
    prefix = 'Consider 8–15 relevant skills you can demonstrate; fewer are fine. '
    if not families:
        prefix += 'I need a more specific role or job description for domain-specific advice. General starting points: '
    else:
        prefix += 'Candidate skills (include only those you actually have): '
    messages = [prefix + ', '.join(candidates) + '.']
    seen, duplicates = set(), []
    for skill in skills:
        key = comparable(skill)
        if key in seen and skill not in duplicates:
            duplicates.append(skill)
        seen.add(key)
    if duplicates:
        messages.append('Review duplicate or equivalent skills: ' + ', '.join(duplicates) + '. Keep one clear label for each.')
    unrelated = []
    if families:
        expected = {comparable(skill) for key in families for skill in ROLES[key]['skills']}
        expected.update(comparable(skill) for skill in (*GENERAL_SKILLS, *SENIOR_SKILLS, *EXECUTIVE_SKILLS))
        if set(families) & {'backend', 'frontend', 'fullstack', 'java', 'node', 'dotnet'}:
            # Web fundamentals can support backend work and integration with a
            # frontend even when they are absent from the short candidate list.
            expected.update(comparable(skill) for skill in ('HTML', 'CSS', 'JavaScript', 'HTTP', 'JSON'))
        known = {comparable(skill) for row in ROLES.values() for skill in row['skills']}
        for skill in skills:
            key = comparable(skill)
            if key in known and key not in expected:
                unrelated.append(skill)
    if unrelated:
        messages.append('Check whether these skills support this target role: ' + ', '.join(unrelated[:10])
                        + '. Keep transferable skills where useful; nothing was removed. To remove a skill, say "remove NAME from my skills".')
    if include_count and len(skills) > 15:
        messages.append('You have a large skills list. Prioritize 8–15 strongest relevant skills for readability; all skills are retained until you choose.')
    return messages


def entry_text(entry):
    if isinstance(entry, str):
        return entry
    return ' '.join(str(value) if not isinstance(value, list) else ' '.join(map(str, value))
                    for key, value in entry.items() if key not in ('url', 'github_url', 'live_demo'))


def ranked_entries(state, section, data=None):
    data = guidance_data(state) if data is None else data
    families = role_families(state.get('target_role') or '')
    terms = list(dict.fromkeys(term for key in families for term in (*ROLES[key]['roles'], *ROLES[key]['skills'], *ROLES[key]['certifications'])))
    target_words = [word for word in re.findall(r'\w+', (state.get('target_role') or '').casefold())
                    if len(word) > 3 and word not in ('senior', 'junior', 'engineer', 'developer', 'level')]
    ranked = []
    for index, entry in enumerate(data.get(section) or []):
        text = entry_text(entry)
        matches = [term for term in terms if contains(text, term)]
        score = len(matches) + sum(contains(text, word) for word in target_words)
        title = (entry.get('name') or entry.get('job_title') or entry.get('role') or entry.get('company')
                 or f'Entry {index + 1}') if isinstance(entry, dict) else entry
        ranked.append({'index': index, 'title': title, 'score': score, 'matches': matches[:3]})
    return sorted(ranked, key=lambda item: -item['score'])  # Stable ties preserve source order.


def entry_advice(state, section, data):
    level = career_profile(state)
    count = len(data.get(section) or [])
    selection = (state.get('display_experience_indexes') if section == 'experience'
                 else (state.get('display_entry_indexes') or {}).get(section))
    displayed = len(selection) if selection is not None else count
    if section == 'projects':
        if level in EARLY:
            guidance = 'Aim for 2–3 strong academic, personal or volunteer projects if available. Internships and work experience are optional.'
        else:
            guidance = 'Consider 3–5 relevant projects if they add evidence beyond your employment history; fewer strong projects are fine.'
        maximum = 3 if level in EARLY else 5
        detail = 'Describe the problem, your own contribution, technologies actually used and a confirmed outcome.'
    else:
        maximum = 5
        guidance = ('Internships, freelance and work experience are optional; include any relevant experience you have.' if level in EARLY else
                    'Prioritize 3–5 recent, relevant experiences if available; do not add jobs just to reach a count.')
        detail = {
            'student': 'Academic or volunteer responsibilities can also demonstrate skills; identify them accurately.',
            'fresher': 'Focus on your contribution and what you learned or delivered.',
            'junior': 'Focus on hands-on delivery, growing responsibility and collaboration.',
            'mid_level': 'Show independent ownership, delivery decisions and cross-team impact.',
            'senior': 'Show architecture, technical decisions, mentoring and confirmed team impact.',
            'executive': 'Show strategy, leadership scope, governance and confirmed organizational outcomes.',
        }.get(level, 'Show your contribution and confirmed outcomes.')
    messages = [guidance + ' ' + detail + ' Use measurable achievements only when you can confirm them; a clear qualitative result is also useful.']
    if displayed > maximum:
        messages.append(f'You have {count} {section}. Consider prioritizing the strongest {"2–3" if maximum == 3 else "3–5"}; all source entries are retained.')
    if section == 'experience' and displayed > 5:
        messages.append('The canonical CV supports at most five displayed experiences. Use "select experiences 1, 2, 3" after reviewing the numbered suggestions; all source entries remain in this conversation.')
    return messages


def education_advice(data):
    entries = data.get('education') or []
    messages = []
    for index, entry in enumerate(entries):
        missing = [label for key, label in (('degree', 'degree'), ('institution', 'institution'),
                   ('field_of_study', 'field of study'), ('end_date', 'graduation/expected graduation date')) if not entry.get(key)]
        if missing:
            messages.append(f'Education entry {index + 1} is missing: ' + ', '.join(missing) + '. Complete confirmed details when available.')
        for field in ('start_date', 'end_date'):
            if re.fullmatch(r'\d{4}', str(entry.get(field, ''))):
                messages.append(f'Education entry {index + 1}: confirm the month for {field.replace("_", " ")} ({entry[field]}) before saving, or explicitly omit that date.')
        grade = re.fullmatch(r'(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)', str(entry.get('grade', '')).replace(' ', ''))
        if grade and float(grade[2]) > 0 and float(grade[1]) / float(grade[2]) < .6:
            messages.append('Grades are optional. You can omit your grade and focus on relevant coursework, projects and confirmed achievements if you prefer.')
    if not entries:
        messages.append('Include your degree or course, institution, field of study and graduation or expected completion date when applicable.')
    messages.append('Highlight relevant academic projects, coursework, awards or a strong grade only if confirmed. Grades and academic achievements are optional.')
    return messages[:5]


def certification_advice(state, data):
    families = role_families(state.get('target_role') or '')
    topics = list(dict.fromkeys(topic for key in families for topic in ROLES[key]['certifications']))[:5]
    text = 'Consider 3–5 relevant certifications if you already hold them; fewer or none is fine.'
    if topics:
        text += ' Relevant topic areas to check: ' + ', '.join(topics) + '.'
    text += ' Provide the actual title, issuer, date and credential link if available; no qualifications have been added.'
    messages = [text]
    if len(data.get('certifications') or []) > 5:
        messages.append('Consider featuring around 3–5 of your most relevant certifications. All certifications are retained until you choose.')
    return messages


def length_advice(state, data):
    words = sum(len(entry_text(value).split()) for key, values in data.items()
                if key in ('summary', 'skills', 'education', 'experience', 'projects', 'certifications', 'achievements')
                for value in (values if isinstance(values, list) else [values]))
    level = career_profile(state)
    text = ('Aim for a concise page when practical.' if level in EARLY else
            'One or two pages may be useful depending on relevant career history.')
    text += ' The selected template and rendered preview determine the actual page count.'
    if words > (450 if level in EARLY else 800):
        text += f' Your current content is about {words} words and may be lengthy; prioritize relevant evidence rather than shrinking text.'
    return [text]


def guidance_sections(state):
    data = guidance_data(state)
    return {'skills': skill_advice(state, data),
            'experience': entry_advice(state, 'experience', data),
            'projects': entry_advice(state, 'projects', data),
            'certifications': certification_advice(state, data),
            'education': education_advice(data), 'review': length_advice(state, data)}


def recommendations(state):
    sections = guidance_sections(state)
    # Put actionable overflow diagnostics ahead of the general advice in review.
    messages = [message for rows in sections.values() for message in rows[1:]]
    return list(dict.fromkeys(messages + [message for rows in sections.values() for message in rows[:1]]))


def guidance_message(state, topic='all'):
    sections = guidance_sections(state)
    rows = list(sections) if topic == 'all' else [topic]
    messages = [f'Suggestions for {state.get("target_role") or "your target role"} ({PROFILES[career_profile(state)][0]}). These are optional; confirm any facts you want included.']
    for section in rows:
        messages.extend(sections[section])
        if section in ('experience', 'projects', 'certifications'):
            maximum = 3 if section == 'projects' and career_profile(state) in EARLY else 5
            ranked = ranked_entries(state, section)[:min(maximum, 3) if topic == 'all' else maximum]
            if ranked:
                messages.append('Entries to review first (original numbers; keyword relevance is only a guide): ' + '; '.join(
                    f'{item["index"] + 1}. {str(item["title"])[:100]} — ' + (', '.join(item['matches']) if item['score'] else 'relevance needs your confirmation') for item in ranked))
                messages.append(f'To display a chosen subset in your preferred order, say "select {section} 1, 2". The source entries stay in chat.')
    if topic in ('all', 'experience', 'projects', 'certifications'):
        messages.append('Would you like to add an entry or prioritize existing entries? Use "add another project", "add another job", "add a certification", or "prioritize projects"; you can also continue without changes.')
    # Keep the chat envelope bounded even with many long, user-supplied titles.
    bounded, size = [], 0
    for message in messages:
        if size + len(message) > 3900:
            continue
        bounded.append(message)
        size += len(message) + 1
    if len(bounded) < len(messages):
        bounded.append('Ask for skills, education, experiences, projects or certifications separately for the full guidance.')
    return '\n'.join(bounded)


def fresh_skill_diagnostics(state):
    diagnostics = skill_advice(state, guidance_data(state), include_count=False)[1:]
    seen = state.setdefault('guidance_seen', {})
    digest = sha256(json.dumps(diagnostics).encode()).hexdigest()
    changed = seen.get('skill_diagnostics') != digest
    seen['skill_diagnostics'] = digest
    return diagnostics if changed else []


def automatic_guidance(state, response):
    """Show advice once on section entry; repeat only changed overflow diagnostics."""
    from chatbot.services.question_engine import next_step
    step = next_step(state)
    if state.get('section_followup'):
        # The count question already contains the optional advice. Retain useful
        # skill diagnostics, without asking the next section's question as well.
        if (response.get('cv_updates') or {}).get('skills'):
            return '\n'.join(fresh_skill_diagnostics(state))
        return ''
    if state.get('pending_field') or state.get('date_confirmation_pending') or state.get('pending_selection'):
        return ''
    sections = guidance_sections(state)
    seen = state.setdefault('guidance_seen', {})
    messages = []
    section = step['section']
    identity = [state.get('target_role'), career_profile(state)]
    if section in sections:
        key = sha256(json.dumps(identity).encode()).hexdigest()
        if seen.get(section) != key:
            seen[section] = key
            messages.append(sections[section][0])
            if section == 'review':
                messages.append('You can add another entry, ask for "CV suggestions", or finish when ready; no minimum number of entries is required.')
    data = guidance_data(state)
    if (response.get('cv_updates') or {}).get('skills'):
        messages.extend(fresh_skill_diagnostics(state))
    limits = {'skills': 15, 'experience': 5, 'projects': 3 if career_profile(state) in EARLY else 5, 'certifications': 5}
    for section, limit in limits.items():
        if (response.get('cv_updates') or {}).get(section) and len(data.get(section) or []) > limit:
            key = str(len(data[section]))
            if seen.get('overflow_' + section) != key:
                seen['overflow_' + section] = key
                messages.extend(sections[section][-1:] if section == 'skills' else sections[section][1:])
    return '\n'.join(dict.fromkeys(messages))
