from rest_framework import serializers
from shared.enums.career_level import CareerLevel
from .models import CV, CVVersion

class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key:['Unknown or read-only field.'] for key in unknown})
        return super().to_internal_value(data)

class CVWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255)
    target_role = serializers.CharField(max_length=255, allow_blank=True, required=False)
    career_level = serializers.ChoiceField(choices=['']+[v.value for v in CareerLevel], required=False)
    template_id = serializers.CharField(max_length=255, allow_blank=True, required=False)
    data = serializers.JSONField(required=False)

class CVPatchSerializer(CVWriteSerializer):
    name = serializers.CharField(max_length=255, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)
    def validate(self, attrs):
        if not set(attrs) - {'expected_version'}:
            raise serializers.ValidationError('Provide at least one editable field.')
        return attrs

class CheckpointSerializer(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1, required=False)

class DuplicateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255, required=False)

class CVReadSerializer(serializers.ModelSerializer):
    target_role = serializers.CharField(source='data.meta.target_role', read_only=True)
    career_level = serializers.CharField(source='data.meta.career_level', read_only=True)
    template_id = serializers.CharField(source='data.meta.template_id', read_only=True)
    class Meta:
        model = CV
        fields = ['id','name','target_role','career_level','template_id','data','version','created_at','updated_at']
        read_only_fields = fields

class CVVersionSerializer(CVReadSerializer):
    cv_id = serializers.IntegerField(read_only=True)
    class Meta:
        model = CVVersion
        fields = ['id','cv_id','name','target_role','career_level','template_id','data','version','created_at']
        read_only_fields = fields


class ChatImportSerializer(StrictSerializer):
    session_id = serializers.UUIDField()
    expected_version = serializers.IntegerField(min_value=1, required=False)
