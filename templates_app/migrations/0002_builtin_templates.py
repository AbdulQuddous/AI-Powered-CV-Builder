from django.db import migrations


def seed_templates(apps, schema_editor):
    Template = apps.get_model('templates_app', 'CVTemplate')
    for template_id, name, category in (
        ('modern', 'Modern', 'modern'),
        ('classic', 'Classic', 'professional'),
        ('developer', 'Developer', 'technical'),
    ):
        # Preserve existing catalogue entries and administrator customizations.
        if Template.objects.filter(id=template_id).exists() or Template.objects.filter(name=name).exists():
            continue
        Template.objects.create(id=template_id, name=name, category=category,
            description=f'{name} CV layout', ats_compatible=True,
            supported_levels=['fresher', 'experienced', 'other'], supported_roles=[],
            template_path=f'cv_templates/{template_id}.html', is_available=True)


class Migration(migrations.Migration):
    dependencies = [('templates_app', '0001_initial')]
    operations = [migrations.RunPython(seed_templates, migrations.RunPython.noop)]
