"""Rasterize actual M8 PDFs once; the gallery only serves optimized static assets."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageChops, ImageStat
from templates_app.catalogue import catalogue, definition
from templates_app.services import TemplateService
from m8_renderer.samples import sample_cv
from m8_renderer.services.pdf_exporter import PDFExporter


class Command(BaseCommand):
    help = 'Generate cached WebP previews from synthetic canonical CV data and M8 PDFs.'

    def add_arguments(self, parser):
        parser.add_argument('--template', action='append', dest='templates')
        parser.add_argument('--force', action='store_true')
        parser.add_argument('--check', action='store_true', help='Compare freshly rendered previews with cached references without writing them.')
        parser.add_argument('--output', type=Path)

    def handle(self, *args, **options):
        if not shutil.which('pdftoppm'):
            raise CommandError('Install Poppler (pdftoppm) to rasterize PDFs; no browser or AI service is needed.')
        output = options['output'] or settings.BASE_DIR / 'm8_renderer/static/cv_templates/previews'
        output.mkdir(parents=True, exist_ok=True)
        manifest_path = output / 'manifest.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        sources = sorted((settings.BASE_DIR / 'm8_renderer/templates/cv_templates').rglob('*'))
        sources += [settings.BASE_DIR / 'templates_app/catalogue.json']
        sources += [settings.BASE_DIR / 'm8_renderer/services' / name for name in ('renderer.py', 'context_builder.py', 'skill_groups.py', 'designs.py', 'pdf_exporter.py')]
        digest = hashlib.sha256(b''.join(p.read_bytes() for p in sources if p.is_file()) + json.dumps(sample_cv(), sort_keys=True).encode()).hexdigest()
        templates = list(TemplateService.list_available_templates())
        selected = options['templates'] or list(catalogue())
        available = {t.pk: t for t in templates}
        missing = set(selected) - set(available)
        if missing:
            raise CommandError('Missing or unavailable templates; migrate first: ' + ', '.join(sorted(missing)))
        mismatches = []
        for template_id in selected:
            template = available[template_id]
            if definition(template) is None:
                raise CommandError(f'{template_id}: customized renderer; generate and approve a custom preview separately.')
            path = output / f'{template_id}.webp'
            if not options['check'] and not options['force'] and path.exists() and manifest.get(template_id, {}).get('source_hash') == digest:
                continue
            pdf = PDFExporter.generate({'template_id': template_id, 'cv_data': sample_cv()})
            with tempfile.TemporaryDirectory(prefix='cv-thumbnail-') as tmp:
                source, destination = Path(tmp) / 'sample.pdf', Path(tmp) / 'page'
                source.write_bytes(pdf)
                subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '840', '-png', str(source), str(destination)], check=True, capture_output=True)
                with Image.open(destination.with_suffix('.png')) as img:
                    candidate = Path(tmp) / 'candidate.webp' if options['check'] else path
                    img.convert('RGB').save(candidate, 'WEBP', quality=85, method=6)
                if options['check']:
                    if not path.is_file():
                        mismatches.append(template_id + ': missing preview')
                    else:
                        with Image.open(candidate) as current, Image.open(path) as reference:
                            if current.size != reference.size or max(ImageStat.Stat(ImageChops.difference(current.convert('RGB'), reference.convert('RGB'))).rms) > 1:
                                mismatches.append(template_id + ': image differs')
                    if manifest.get(template_id, {}).get('source_hash') != digest:
                        mismatches.append(template_id + ': source hash is stale')
                    self.stdout.write(f'Checked {template_id}')
                    continue
            manifest[template_id] = {'source_hash': digest, 'pdf_sha256': hashlib.sha256(pdf).hexdigest(), 'bytes': path.stat().st_size, 'sample': 'comparison'}
            self.stdout.write(f'Generated {template_id}: {path.stat().st_size} bytes')
        if options['check']:
            if mismatches:
                raise CommandError('Preview verification failed: ' + '; '.join(mismatches))
            self.stdout.write(self.style.SUCCESS(f'{len(selected)} previews match current M8 rendering.'))
            return
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        self.stdout.write(self.style.SUCCESS(f'{len(selected)} renderable previews ready.'))
