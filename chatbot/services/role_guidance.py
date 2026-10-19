"""Stable skill vocabularies and certification topics, not claims of credentials.

These are candidate areas to discuss. No provider, course marketplace or live
certification catalogue is involved, and none of these values enter CV updates.
"""

ROLES = {
    'java': {
        'roles': ('java developer', 'java engineer', 'spring boot', 'java backend', 'java backend developer'),
        'skills': ('Java', 'Spring Boot', 'REST APIs', 'SQL', 'Git', 'Unit testing', 'Hibernate', 'Maven', 'Application security', 'Docker', 'Debugging', 'Software design'),
        'certifications': ('Java programming', 'backend development', 'database systems', 'cloud fundamentals'),
    },
    'node': {
        'roles': ('node', 'nodejs', 'node.js'),
        'skills': ('JavaScript', 'TypeScript', 'Node.js', 'REST APIs', 'SQL', 'Git', 'Unit testing', 'Asynchronous programming', 'Application security', 'Docker', 'Express', 'Debugging'),
        'certifications': ('JavaScript', 'backend development', 'database systems', 'cloud fundamentals'),
    },
    'dotnet': {
        'roles': ('.net', 'dotnet', 'c#'),
        'skills': ('C#', '.NET', 'ASP.NET Core', 'REST APIs', 'SQL', 'Git', 'Unit testing', 'Entity Framework', 'Application security', 'Debugging', 'Docker', 'Software design'),
        'certifications': ('.NET development', 'database systems', 'cloud fundamentals', 'application security'),
    },
    'backend': {
        'roles': ('backend', 'back end', 'django', 'python', 'api developer'),
        'skills': ('Python', 'Django', 'REST APIs', 'SQL', 'PostgreSQL', 'Git', 'Unit testing', 'API security', 'Docker', 'Linux', 'Caching', 'Asynchronous programming'),
        'certifications': ('backend development', 'database systems', 'cloud fundamentals', 'application security'),
    },
    'frontend': {
        'roles': ('frontend', 'front end', 'react', 'web designer'),
        'skills': ('HTML', 'CSS', 'JavaScript', 'TypeScript', 'React', 'Responsive web design', 'Web accessibility', 'Git', 'Unit testing', 'Browser debugging', 'REST APIs', 'Web performance'),
        'certifications': ('web development', 'web accessibility', 'JavaScript', 'user experience'),
    },
    'fullstack': {
        'roles': ('fullstack', 'full stack', 'software engineer', 'software developer', 'web developer', 'developer'),
        'skills': ('Programming', 'Data structures', 'SQL', 'REST APIs', 'Git', 'Unit testing', 'Debugging', 'Software design', 'Web development', 'Application security', 'Continuous integration', 'Technical documentation'),
        'certifications': ('software development', 'cloud fundamentals', 'database systems', 'application security'),
    },
    'ai_ml': {
        'roles': ('ai', 'ml', 'machine learning', 'artificial intelligence', 'data scientist', 'nlp'),
        'skills': ('Python', 'Machine learning', 'Deep learning', 'Natural language processing', 'Data preprocessing', 'Model evaluation', 'Statistics', 'SQL', 'Git', 'PyTorch', 'scikit-learn', 'MLOps'),
        'certifications': ('machine learning', 'data science', 'responsible AI', 'cloud machine learning'),
    },
    'data': {
        'roles': ('data analyst', 'business intelligence', 'analytics', 'data engineer'),
        'skills': ('SQL', 'Python', 'Data cleaning', 'Data visualization', 'Statistics', 'Excel', 'Power BI', 'Data modeling', 'ETL', 'Data quality', 'Git', 'Stakeholder communication'),
        'certifications': ('data analytics', 'business intelligence', 'database systems', 'data engineering'),
    },
    'devops': {
        'roles': ('devops', 'cloud engineer', 'site reliability', 'platform engineer', 'sre'),
        'skills': ('Linux', 'Git', 'Docker', 'Kubernetes', 'Continuous integration', 'Infrastructure as code', 'Cloud networking', 'Monitoring', 'Incident response', 'Python', 'Shell scripting', 'Security practices'),
        'certifications': ('cloud infrastructure', 'container orchestration', 'Linux administration', 'cloud security'),
    },
    'security': {
        'roles': ('cybersecurity', 'security engineer', 'security analyst', 'penetration tester'),
        'skills': ('Network security', 'Linux', 'Threat analysis', 'Incident response', 'Risk assessment', 'Vulnerability assessment', 'Python', 'Identity and access management', 'Security monitoring', 'Application security', 'Technical documentation', 'Security awareness'),
        'certifications': ('security fundamentals', 'network security', 'incident response', 'risk management'),
    },
    'design': {
        'roles': ('ux', 'ui', 'product designer', 'graphic designer', 'visual designer'),
        'skills': ('User research', 'Wireframing', 'Prototyping', 'Figma', 'Information architecture', 'Usability testing', 'Interaction design', 'Visual design', 'Design systems', 'Accessibility', 'User journey mapping', 'Stakeholder communication'),
        'certifications': ('user experience design', 'usability research', 'accessibility', 'interaction design'),
    },
    'product': {
        'roles': ('product manager', 'product owner'),
        'skills': ('Product strategy', 'User research', 'Roadmap planning', 'Prioritization', 'Product analytics', 'Requirements gathering', 'Stakeholder management', 'Agile delivery', 'Experiment design', 'Market research', 'Communication', 'Outcome measurement'),
        'certifications': ('product management', 'Agile delivery', 'product analytics', 'user research'),
    },
    'project': {
        'roles': ('project manager', 'program manager', 'programme manager', 'scrum master'),
        'skills': ('Project planning', 'Risk management', 'Budget tracking', 'Stakeholder management', 'Agile delivery', 'Requirements gathering', 'Resource planning', 'Communication', 'Change management', 'Reporting', 'Delivery coordination', 'Quality assurance'),
        'certifications': ('project management', 'Agile delivery', 'risk management', 'change management'),
    },
    'marketing': {
        'roles': ('marketing', 'seo', 'content strategist', 'social media'),
        'skills': ('Content strategy', 'SEO', 'Campaign planning', 'Marketing analytics', 'Copywriting', 'Audience research', 'Email marketing', 'Social media strategy', 'A/B testing', 'Brand communication', 'Reporting', 'Conversion optimization'),
        'certifications': ('digital marketing', 'analytics', 'content marketing', 'search marketing'),
    },
    'finance': {
        'roles': ('accountant', 'accounting', 'finance', 'financial analyst', 'auditor'),
        'skills': ('Financial reporting', 'Excel', 'Budgeting', 'Reconciliation', 'Financial analysis', 'Internal controls', 'Data accuracy', 'Forecasting', 'Risk assessment', 'Audit documentation', 'Communication', 'Financial modeling'),
        'certifications': ('financial analysis', 'accounting', 'internal audit', 'risk management'),
    },
    'leadership': {
        'roles': ('executive', 'director', 'chief', 'cto', 'ceo', 'vp', 'vice president', 'head of'),
        'skills': ('Strategy', 'Organizational leadership', 'Budget ownership', 'Stakeholder management', 'Governance', 'Risk management', 'Change management', 'Team development', 'Decision making', 'Business planning', 'Performance management', 'Communication'),
        'certifications': ('organizational leadership', 'governance', 'strategy', 'risk management'),
    },
}

SENIOR_SKILLS = ('System design', 'Technical leadership', 'Mentoring')
EXECUTIVE_SKILLS = ('Strategy', 'Organizational leadership', 'Budget ownership')
# Narrow aliases used only for comparison and ranking; user text is retained.
COMPARISON_ALIASES = {
    'ml': 'machine learning', 'dl': 'deep learning', 'nlp': 'natural language processing',
    'rest api': 'rest apis', 'restapi': 'rest apis', 'restapis': 'rest apis',
    'ui design': 'visual design', 'ux research': 'user research', 'ci/cd': 'continuous integration',
}
