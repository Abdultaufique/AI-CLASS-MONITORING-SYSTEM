"""
Initial migration for apps.attention — creates AttentionSession and AttentionSnapshot.
"""
import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        ('monitoring', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttentionSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[('active', 'Active'), ('ended', 'Ended'), ('error', 'Error')],
                    default='active', max_length=10
                )),
                ('aggregate_only', models.BooleanField(
                    default=True,
                    help_text='When True, only class-wide attention % is displayed. No per-slot cards shown.',
                )),
                ('alert_threshold', models.FloatField(default=0.5)),
                ('alert_duration_secs', models.IntegerField(default=30)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='attention_sessions',
                    to='accounts.organization',
                )),
                ('camera', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='attention_sessions',
                    to='monitoring.camera',
                )),
            ],
            options={'ordering': ['-started_at']},
        ),
        migrations.CreateModel(
            name='AttentionSnapshot',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('timestamp', models.DateTimeField()),
                ('class_attention_pct', models.FloatField()),
                ('total_faces', models.IntegerField(default=0)),
                ('attentive_count', models.IntegerField(default=0)),
                ('distracted_count', models.IntegerField(default=0)),
                ('alert_active', models.BooleanField(default=False)),
                ('session', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='snapshots',
                    to='attention.attentionsession',
                )),
            ],
            options={'ordering': ['timestamp']},
        ),
        migrations.AddIndex(
            model_name='attentionsnapshot',
            index=models.Index(fields=['session', 'timestamp'],
                               name='attention_snapshot_session_ts_idx'),
        ),
    ]
