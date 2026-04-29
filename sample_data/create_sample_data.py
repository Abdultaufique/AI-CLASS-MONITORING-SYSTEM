"""
Management command to create sample data for testing.
Run: python manage.py shell < sample_data/create_sample_data.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.contrib.auth.models import User
from apps.accounts.models import Organization, UserProfile
from apps.monitoring.models import Camera, Attendance
from apps.violations.models import Warning, Violation, RuleConfig
from apps.notifications.models import Notification
from django.utils import timezone
from datetime import timedelta
import random

print("Creating sample data...")

# 1. Create Organizations
org1, _ = Organization.objects.get_or_create(
    slug='greenfield-academy',
    defaults={'name': 'Greenfield Academy', 'address': '123 Education St', 'max_cameras': 10, 'max_students': 500}
)
org2, _ = Organization.objects.get_or_create(
    slug='city-library',
    defaults={'name': 'City Central Library', 'address': '456 Knowledge Ave', 'max_cameras': 5, 'max_students': 200}
)
print(f"  Organizations: {org1.name}, {org2.name}")

# 2. Create Admin User
admin_user, created = User.objects.get_or_create(
    username='admin',
    defaults={'first_name': 'Admin', 'last_name': 'User', 'email': 'admin@lsoys.com', 'is_staff': True, 'is_superuser': True}
)
if created:
    admin_user.set_password('admin123')
    admin_user.save()

admin_profile, _ = UserProfile.objects.get_or_create(
    user=admin_user,
    defaults={'organization': org1, 'role': 'admin'}
)
print(f"  Admin: {admin_user.username} / admin123")

# 3. Create Sample Students
students_data = [
    ('alice', 'Alice', 'Johnson', 'STU001'),
    ('bob', 'Bob', 'Smith', 'STU002'),
    ('charlie', 'Charlie', 'Brown', 'STU003'),
    ('diana', 'Diana', 'Williams', 'STU004'),
    ('eve', 'Eve', 'Davis', 'STU005'),
    ('frank', 'Frank', 'Miller', 'STU006'),
    ('grace', 'Grace', 'Wilson', 'STU007'),
    ('henry', 'Henry', 'Moore', 'STU008'),
]

for username, first, last, sid in students_data:
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'first_name': first, 'last_name': last, 'email': f'{username}@student.lsoys.com'}
    )
    if created:
        user.set_password('student123')
        user.save()
    UserProfile.objects.get_or_create(
        user=user,
        defaults={'organization': org1, 'role': 'student', 'student_id': sid}
    )
print(f"  Created {len(students_data)} students")

# 4. Create Cameras
cam1, _ = Camera.objects.get_or_create(
    organization=org1, name='Library Room A',
    defaults={'location': 'Building A, Floor 1', 'source_type': 'webcam', 'source_url': '0'}
)
cam2, _ = Camera.objects.get_or_create(
    organization=org1, name='Classroom 101',
    defaults={'location': 'Building B, Floor 1', 'source_type': 'webcam', 'source_url': '0'}
)
print(f"  Cameras: {cam1.name}, {cam2.name}")

# 5. Create Rule Config
RuleConfig.objects.get_or_create(
    organization=org1,
    defaults={'max_warnings_per_day': 3, 'max_violations_before_expel': 3, 'audio_threshold': 500, 'cooldown_seconds': 30}
)

# 6. Create Sample Attendance (last 7 days)
now = timezone.now()
student_users = User.objects.filter(profile__organization=org1, profile__role='student')

for day_offset in range(7):
    date = now - timedelta(days=day_offset)
    for user in random.sample(list(student_users), min(len(student_users), random.randint(4, 8))):
        Attendance.objects.get_or_create(
            user=user, organization=org1, date=date.date(),
            defaults={
                'camera': random.choice([cam1, cam2]),
                'face_confidence': random.uniform(0.75, 0.99),
            }
        )
print("  Sample attendance created")

# 7. Create Sample Warnings
for user in random.sample(list(student_users), 3):
    for level in range(1, random.randint(2, 4)):
        Warning.objects.create(
            user=user, organization=org1, level=min(level, 3),
            reason='Talking detected in quiet zone',
            camera_location=random.choice(['Library Room A', 'Classroom 101']),
        )

print("  Sample warnings created")

# 8. Create Sample Notifications
Notification.objects.get_or_create(
    organization=org1, title='System Started',
    defaults={'message': 'LSOYS AI Monitoring Platform is now active.', 'severity': 'info', 'notification_type': 'system'}
)

print("\n[OK] Sample data created successfully!")
print("   Login: admin / admin123")
print("   Students: alice, bob, charlie, etc. / student123")
