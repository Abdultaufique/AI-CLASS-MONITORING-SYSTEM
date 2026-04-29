"""
Serializers for the accounts app.
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Organization, UserProfile


class OrganizationSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug', 'address', 'is_active',
                  'max_cameras', 'max_students', 'member_count',
                  'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.members.count()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)
    today_warnings_count = serializers.IntegerField(read_only=True)
    username = serializers.CharField(write_only=True, required=True)
    first_name = serializers.CharField(write_only=True, required=True)
    last_name = serializers.CharField(write_only=True, required=False, default='')
    email = serializers.EmailField(write_only=True, required=False, default='')
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'organization', 'role', 'student_id',
                  'phone', 'face_image', 'is_active', 'full_name',
                  'today_warnings_count', 'created_at', 'updated_at',
                  'username', 'first_name', 'last_name', 'email', 'password']
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

    def create(self, validated_data):
        username = validated_data.pop('username')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name', '')
        email = validated_data.pop('email', '')
        password = validated_data.pop('password')
        face_image = validated_data.pop('face_image', None)

        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
        )

        profile = UserProfile.objects.create(user=user, face_image=face_image, **validated_data)
        
        # Auto-generate encoding if image is provided
        if face_image:
            try:
                from apps.monitoring.services.face_service import FaceService
                import pickle
                svc = FaceService()
                encoding = svc.encode_face_from_image(profile.face_image.path)
                if encoding is not None:
                    profile.face_encoding = pickle.dumps(encoding)
                    profile.save()
            except Exception:
                pass
                
        return profile
