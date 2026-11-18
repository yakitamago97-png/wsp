from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------
# 会社テーブル（company）
# ---------------------------------------------------------------
class Company(models.Model):
    company_name = models.CharField('会社名', max_length=100)
    # 電話番号は先頭の 0 が消えないよう、数値ではなく文字列にする
    tel = models.CharField('電話番号', max_length=11, blank=True, default='')
    # 設計書の列名「e-mail」は Django で使えないため email にする
    email = models.EmailField('メールアドレス', max_length=50, blank=True, default='')
    post_code = models.CharField('郵便番号', max_length=7, blank=True, default='')
    prefecture = models.CharField('都道府県', max_length=4, blank=True, default='')
    city = models.CharField('市町村', max_length=20, blank=True, default='')
    address_line1 = models.CharField('番地', max_length=50, blank=True, default='')
    address_line2 = models.CharField('建物名', max_length=50, blank=True, default='')

    class Meta:
        db_table = 'company'
        verbose_name = '会社'
        verbose_name_plural = '会社'

    def __str__(self):
        return self.company_name


# ---------------------------------------------------------------
# 体調テーブル（physical_condition）
#   0→良い / 1→やや良い / 2→普通 / 3→やや悪い / 4→悪い
#   中身は migrations/0002_master_data.py が自動で登録する
# ---------------------------------------------------------------
class PhysicalCondition(models.Model):
    id = models.CharField('体調ID', max_length=1, primary_key=True)
    name = models.CharField('体調名', max_length=20)

    class Meta:
        db_table = 'physical_condition'
        verbose_name = '体調'
        verbose_name_plural = '体調'

    def __str__(self):
        return self.name


# ---------------------------------------------------------------
# 気分テーブル（feeling）
#   0→絶好調・意欲的 / 1→良好・安定 / 2→普通
#   3→モヤモヤ・落ち込み / 4→焦り・イライラ
#   中身は migrations/0002_master_data.py が自動で登録する
# ---------------------------------------------------------------
class Feeling(models.Model):
    id = models.CharField('気分ID', max_length=1, primary_key=True)
    name = models.CharField('気分名', max_length=20)

    class Meta:
        db_table = 'feeling'
        verbose_name = '気分'
        verbose_name_plural = '気分'

    def __str__(self):
        return self.name


# ---------------------------------------------------------------
# ユーザーテーブル（users）
#   従業員ID（= 自動採番の id）とパスワードでログインする
# ---------------------------------------------------------------
class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        # ログインIDは数字の id。数字以外が入力されたら「該当なし」として扱う
        try:
            return super().get_by_natural_key(username)
        except (ValueError, TypeError):
            raise self.model.DoesNotExist

    def _create_user(self, id, password, **extra_fields):
        user = self.model(id=id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, id=None, password=None, **extra_fields):
        """一般の従業員／管理者を作る。id を省略すると自動採番される。"""
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(id, password, **extra_fields)

    def create_superuser(self, id=None, password=None, **extra_fields):
        """createsuperuser コマンドで使われる。管理者権限も True にする。"""
        extra_fields.setdefault('authority', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self._create_user(id, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    # id（従業員ID）は自動採番。Django が自動で作るので、ここには書かない
    # password は AbstractBaseUser が持つ（暗号化して保存される）
    last_name = models.CharField('姓', max_length=20)
    given_name = models.CharField('名', max_length=20)
    # 管理者 → True、一般 → False
    authority = models.BooleanField('権限（管理者）', default=False)
    email = models.EmailField('メールアドレス', max_length=100, unique=True, null=True, blank=True)
    company = models.ForeignKey(
        Company,
        verbose_name='会社',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    # 設計書にはないが、退職者を「削除せず無効にする」ために追加
    is_active = models.BooleanField('有効', default=True)

    objects = UserManager()

    # ログインに使う項目は従業員ID（id）
    USERNAME_FIELD = 'id'
    REQUIRED_FIELDS = ['last_name', 'given_name']

    class Meta:
        db_table = 'users'
        verbose_name = '従業員'
        verbose_name_plural = '従業員'

    @property
    def is_staff(self):
        # Django の管理サイト（/admin/）に入れるのは、スーパーユーザーだけにする
        return self.is_superuser

    @property
    def full_name(self):
        return f'{self.last_name} {self.given_name}'

    def __str__(self):
        return f'{self.id}: {self.full_name}'


# ---------------------------------------------------------------
# コンディションテーブル（condition）
# ---------------------------------------------------------------
class Condition(models.Model):
    employee = models.ForeignKey(User, verbose_name='従業員', on_delete=models.PROTECT)
    date = models.DateTimeField('日付', default=timezone.now)
    sleep_time = models.FloatField('睡眠時間', null=True, blank=True)
    physical_condition = models.ForeignKey(
        PhysicalCondition, verbose_name='体調', on_delete=models.PROTECT
    )
    feeling = models.ForeignKey(Feeling, verbose_name='気分', on_delete=models.PROTECT)
    # AI判定の結果（短い言葉）：良好 / 普通 / 休息推奨 / 要休息 など
    ai_judgement = models.CharField('AI判定', max_length=100, blank=True, default='')
    # AIの警告・アドバイス（長い文章）。判定前は空
    ai_comment = models.TextField('AIコメント', blank=True, default='')

    class Meta:
        db_table = 'condition'
        verbose_name = 'コンディション'
        verbose_name_plural = 'コンディション'

    def __str__(self):
        return f'{self.employee_id} {self.date:%Y-%m-%d}'


# ---------------------------------------------------------------
# 勤務記録テーブル（work_record）
# ---------------------------------------------------------------
class WorkRecord(models.Model):
    employee = models.ForeignKey(User, verbose_name='従業員', on_delete=models.PROTECT)
    working_date = models.DateField('対象日', default=timezone.localdate)
    clock_in = models.DateTimeField('出勤時間', default=timezone.now)
    # 退勤前は空（NULL）
    clock_out = models.DateTimeField('退勤時間', null=True, blank=True)
    # 出退勤を修正したときに入力する
    change_reason = models.TextField('変更理由', blank=True, default='')
    condition = models.ForeignKey(
        Condition,
        verbose_name='コンディション',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'work_record'
        verbose_name = '勤務記録'
        verbose_name_plural = '勤務記録'
        constraints = [
            # 1人につき1日1件まで（出勤打刻の二重登録を防ぐ）
            models.UniqueConstraint(
                fields=['employee', 'working_date'],
                name='unique_work_record_per_day',
            ),
        ]

    def __str__(self):
        return f'{self.employee_id} {self.working_date}'


# ---------------------------------------------------------------
# タスクテーブル（task）
# ---------------------------------------------------------------
class Task(models.Model):
    class Status(models.TextChoices):
        UNPROCESSED = '未処理', '未処理'
        IN_PROGRESS = '処理中', '処理中'
        DONE = '処理済み', '処理済み'

    # 担当者
    employee = models.ForeignKey(User, verbose_name='担当者', on_delete=models.PROTECT)
    task_name = models.CharField('タスク名', max_length=100)
    status = models.CharField(
        'ステータス',
        max_length=10,
        choices=Status.choices,
        default=Status.UNPROCESSED,
    )
    deadline = models.DateTimeField('期限', null=True, blank=True)
    detail = models.TextField('詳細', blank=True, default='')
    # 管理者が、従業員が更新した status を見て「完了している」と確認したら True、
    # 完了していなければ False にする（status とは別に、管理者だけが変更する）
    is_completed = models.BooleanField('完了フラグ', default=False)

    class Meta:
        db_table = 'task'
        verbose_name = 'タスク'
        verbose_name_plural = 'タスク'

    def __str__(self):
        return self.task_name