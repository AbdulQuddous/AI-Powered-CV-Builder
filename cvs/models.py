from django.conf import settings
from django.db import models

class CV(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cvs')
    name = models.CharField(max_length=255)
    data = models.JSONField()
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [models.Index(fields=['owner', '-updated_at'], name='cv_owner_updated_idx')]
        constraints = [models.CheckConstraint(condition=models.Q(version__gte=1), name='cv_version_positive')]

class CVVersion(models.Model):
    cv = models.ForeignKey(CV, on_delete=models.CASCADE, related_name='versions')
    version = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-version']
        constraints = [models.UniqueConstraint(fields=['cv','version'], name='cv_snapshot_unique'),
                       models.CheckConstraint(condition=models.Q(version__gte=1), name='cv_snapshot_positive')]
