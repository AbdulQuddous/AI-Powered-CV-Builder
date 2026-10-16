"""Explicit local-only provider smoke test using synthetic CV information."""
import json
import time
from types import SimpleNamespace

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from chatbot.services.extraction_guard import guard_extraction
from chatbot.services.field_validation import validated_updates
from chatbot.services.qwen_client import QwenClient, build_qwen_messages
from chatbot.services.state_manager import ensure_state


class Command(BaseCommand):
    help = 'Check installed Ollama and seven synthetic structured-extraction examples. Never calls Gemini or writes CVs.'

    def add_arguments(self, parser):
        parser.add_argument('--output', help='Optional JSON results file (no real user data).')

    def handle(self, *args, **options):
        try:
            with httpx.Client(timeout=5, trust_env=False) as client:
                response = client.get(settings.CHAT_QWEN_BASE_URL.rstrip('/') + '/api/tags')
                response.raise_for_status()
                models = [entry['name'] for entry in response.json()['models']]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise CommandError('Ollama is unavailable at the configured local endpoint.') from exc
        if settings.CHAT_QWEN_MODEL not in models:
            raise CommandError('The configured model is not installed. No model was downloaded.')
        examples = [
            ('My name is Ali Khan.', 'personal', 'full_name'),
            ('My email is ali@gmail.com.', 'personal', 'email'),
            ('I worked at ABC for six months.', 'experience', 'company'),
            ('I made a Django project using PostgreSQL.', 'projects', 'name'),
            ('I want to add Urdu to my CV.', 'languages', 'changes'),
            ('Change my email to ali@outlook.com.', 'personal', 'email'),
            ('Who won the cricket match?', 'skills', 'skills')]
        results = []
        for index, (message, section, field) in enumerate(examples):
            state = ensure_state({'target_role': 'Python Developer', 'career_level': 'fresher',
                                  'pending_field': {'section': section, 'field': field}})
            session = SimpleNamespace(conversation_state=state)
            start = time.monotonic()
            try:
                raw = QwenClient().generate(build_qwen_messages(session, message))
                guarded = guard_extraction(raw, message, state)
                clean, errors, _ = validated_updates(guarded, state)
                facts = clean['cv_updates']
                personal = facts.get('personal') or {}
                experience = (facts.get('experience') or [{}])[0]
                project = (facts.get('projects') or [{}])[0]
                language = (facts.get('languages') or [{}])[0]
                expected = [
                    personal.get('full_name') == 'Ali Khan',
                    personal.get('email') == 'ali@gmail.com',
                    experience.get('company') == 'ABC' and not any(experience.get(k) for k in ('role', 'technologies', 'employment_type')),
                    {'Django', 'PostgreSQL'} <= set(project.get('technologies') or []),
                    language.get('name') == 'Urdu' and not language.get('proficiency'),
                    personal.get('email') == 'ali@outlook.com',
                    (raw.get('_control') or {}).get('intent') == 'off_topic' and not any(facts.values()),
                ][index]
                item = {'message': message, 'seconds': round(time.monotonic()-start, 3),
                        'structured': True, 'intent': (raw.get('_control') or {}).get('intent'),
                        'expected_facts': expected and not errors,
                        'extracted': {k: v for k, v in clean['cv_updates'].items() if v},
                        'control': raw.get('_control'),
                        'validation_errors': errors,
                        'evidence_warning': guarded.get('_control', {}).get('evidence_warning')}
            except Exception as exc:
                item = {'message': message, 'seconds': round(time.monotonic()-start, 3), 'structured': False, 'error': type(exc).__name__}
            results.append(item)
            self.stdout.write(json.dumps(item, ensure_ascii=False))
            self.stdout.flush()
        report = {'model': settings.CHAT_QWEN_MODEL, 'models_installed': models, 'results': results,
                  'writes': 0, 'gemini_calls': 0}
        if options.get('output'):
            from pathlib import Path
            Path(options['output']).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        if not all(item['structured'] and item.get('expected_facts') for item in results):
            raise CommandError('One or more local extraction examples failed. See measured results.')
