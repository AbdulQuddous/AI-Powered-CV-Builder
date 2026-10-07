from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
User = get_user_model()

class StrictSerializerMixin:
    def to_internal_value(self, data):
        if isinstance(data, dict):
            allowed = {k for k,v in self.fields.items() if not v.read_only}
            unknown = set(data) - allowed
            if unknown:
                raise serializers.ValidationError({k:['Unknown or read-only field.'] for k in unknown})
        return super().to_internal_value(data)

class ProfileSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='id', read_only=True)
    class Meta:
        model = User
        fields = ['user_id','email','full_name']
        read_only_fields = ['email']

class RegisterSerializer(StrictSerializerMixin, serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value
    def validate(self, attrs):
        try:
            validate_password(attrs['password'], User(email=attrs['email'], full_name=attrs.get('full_name','')))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password':exc.messages})
        return attrs
    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError:
            raise serializers.ValidationError({'email':['An account with this email already exists.']})

class LoginSerializer(StrictSerializerMixin, TokenObtainPairSerializer):
    def validate(self, attrs):
        attrs['email'] = attrs['email'].strip().lower()
        return super().validate(attrs)

class LogoutSerializer(StrictSerializerMixin, serializers.Serializer):
    refresh = serializers.CharField(trim_whitespace=False)
