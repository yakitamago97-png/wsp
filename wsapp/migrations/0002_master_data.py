from django.db import migrations

# 体調テーブル（physical_condition）
PHYSICAL_CONDITIONS = [
    ('0', '良い'),
    ('1', 'やや良い'),
    ('2', '普通'),
    ('3', 'やや悪い'),
    ('4', '悪い'),
]

# 気分テーブル（feeling）
FEELINGS = [
    ('0', '絶好調・意欲的'),
    ('1', '良好・安定'),
    ('2', '普通'),
    ('3', 'モヤモヤ・落ち込み'),
    ('4', '焦り・イライラ'),
]


def add_master_data(apps, schema_editor):
    PhysicalCondition = apps.get_model('wsapp', 'PhysicalCondition')
    Feeling = apps.get_model('wsapp', 'Feeling')

    for id_, name in PHYSICAL_CONDITIONS:
        PhysicalCondition.objects.update_or_create(id=id_, defaults={'name': name})
    for id_, name in FEELINGS:
        Feeling.objects.update_or_create(id=id_, defaults={'name': name})


class Migration(migrations.Migration):

    dependencies = [
        ('wsapp', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_master_data, migrations.RunPython.noop),
    ]