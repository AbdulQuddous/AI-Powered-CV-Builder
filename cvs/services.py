from copy import deepcopy
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException
from .models import CV, CVVersion
from .validation import build_document

class VersionConflict(APIException):
    status_code = 409
    default_detail = 'CV has changed. Retrieve it and retry with its current version.'
    default_code = 'version_conflict'

def owned(*, user, cv_id, lock=False):
    qs = CV.objects.filter(owner=user)
    if lock:
        qs = qs.select_for_update()
    return get_object_or_404(qs, pk=cv_id)

def snapshot(cv):
    return CVVersion.objects.create(cv=cv, version=cv.version, name=cv.name, data=deepcopy(cv.data))

def check_version(cv, expected):
    if expected is not None and expected != cv.version:
        raise VersionConflict()

@transaction.atomic
def create_cv(*, user, values):
    cv = CV.objects.create(owner=user, name=values['name'], data=build_document(values))
    snapshot(cv)
    return cv

@transaction.atomic
def update_cv(*, user, cv_id, values):
    cv = owned(user=user, cv_id=cv_id, lock=True)
    check_version(cv, values.get('expected_version'))
    cv.data = build_document(values, current=cv.data)
    cv.name = values.get('name',cv.name)
    cv.version += 1
    cv.save(update_fields=['name','data','version','updated_at'])
    snapshot(cv)
    return cv

@transaction.atomic
def checkpoint_cv(*, user, cv_id, expected_version=None):
    cv = owned(user=user, cv_id=cv_id, lock=True)
    check_version(cv, expected_version)
    cv.version += 1
    cv.save(update_fields=['version','updated_at'])
    return snapshot(cv)

@transaction.atomic
def duplicate_cv(*, user, cv_id, name=None):
    source = owned(user=user, cv_id=cv_id, lock=True)
    return create_cv(user=user, values={'name':name or source.name[:248]+' (copy)', 'data':deepcopy(source.data)})

@transaction.atomic
def delete_cv(*, user, cv_id):
    owned(user=user, cv_id=cv_id, lock=True).delete()
