"""Compose presentation-only sections from M8's normalized canonical context."""
from copy import deepcopy

ORDERS = {
    'work': ['summary', 'experience', 'projects', 'education', 'skills', 'certifications', 'achievements', 'languages'],
    'skills': ['summary', 'skills', 'experience', 'projects', 'education', 'certifications', 'achievements', 'languages'],
    'education': ['summary', 'education', 'projects', 'experience', 'skills', 'certifications', 'achievements', 'languages'],
    'projects': ['summary', 'projects', 'experience', 'skills', 'education', 'certifications', 'achievements', 'languages'],
}
TWO_COLUMN = {'split', 'sidebar', 'asymmetry', 'portfolio'}


def design_context(context, row):
    design = deepcopy(row['design_config'])
    blocks = {section['key']: section for section in context['sections']}
    if context['summary']:
        blocks['summary'] = {'key': 'summary', 'label': 'Professional Summary', 'text': context['summary']}
    if context['skills']:
        blocks['skills'] = {'key': 'skills', 'label': 'Skills', 'skills': context['skills']}
    order = ORDERS[design['order']]
    side = ['skills', 'education', 'certifications', 'languages'] if design['family'] in TWO_COLUMN else []
    if design['family'] == 'portfolio':
        side = ['skills', 'certifications', 'languages']
    design['side_keys'] = ','.join(side)
    design['section_order'] = ','.join(order)
    design['font_stack'] = {'sans': 'Arial, sans-serif', 'serif': 'Georgia, serif', 'mono': 'DejaVu Sans Mono, monospace'}[design['font']]
    return {'design': design, 'template_name': row['name'],
            'main_sections': [blocks[key] for key in order if key in blocks and key not in side],
            'side_sections': [blocks[key] for key in order if key in blocks and key in side]}
