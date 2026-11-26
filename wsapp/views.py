import calendar
from datetime import date, datetime, time
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .models import Condition, Feeling, PhysicalCondition, Task, WorkRecord

WEEKDAYS_JP = ['月', '火', '水', '木', '金', '土', '日']
User = get_user_model()


# ---------------------------------------------------------------
# 共通ヘルパー関数
# ---------------------------------------------------------------
def _parse_year_month(month_str, fallback_date):
    """'YYYY-MM' 文字列を (year, month) に変換。不正や未指定時は fallback_date の年月を返す"""
    if month_str:
        try:
            parsed = datetime.strptime(month_str.strip(), '%Y-%m')
            return parsed.year, parsed.month
        except ValueError:
            pass
    return fallback_date.year, fallback_date.month


def _shift_year_month(year, month, delta_months):
    """year, month を delta_months ヶ月分ずらした (year, month) を返す"""
    total = (year * 12 + (month - 1)) + delta_months
    new_year = total // 12
    new_month = (total % 12) + 1
    return new_year, new_month


def _build_month_history_payload(user, year, month, latest_year, latest_month):
    last_day = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    records = (
        WorkRecord.objects.filter(
            employee=user,
            working_date__range=(start_date, end_date),
        )
        .select_related('condition', 'condition__physical_condition', 'condition__feeling')
        .order_by('-working_date', '-id')
    )

    rows = []
    for rec in records:
        wdate = rec.working_date
        cond = getattr(rec, 'condition', None)

        clock_in_str = (
            timezone.localtime(rec.clock_in).strftime('%H:%M')
            if rec.clock_in else '--:--'
        )
        clock_out_str = (
            timezone.localtime(rec.clock_out).strftime('%H:%M')
            if rec.clock_out else '--:--'
        )

        sleep_val = getattr(cond, 'sleep_time', None) if cond else None
        sleep_str = f"{float(sleep_val):.1f}時間" if sleep_val is not None else '-'

        physical_obj = getattr(cond, 'physical_condition', None) if cond else None
        physical_str = (
            getattr(physical_obj, 'name', None)
            or getattr(physical_obj, 'label', None)
            or (str(physical_obj) if physical_obj is not None else '-')
        )

        feeling_obj = getattr(cond, 'feeling', None) if cond else None
        feeling_str = (
            getattr(feeling_obj, 'name', None)
            or getattr(feeling_obj, 'label', None)
            or (str(feeling_obj) if feeling_obj is not None else '-')
        )

        ai_judgement = getattr(cond, 'ai_judgement', None) or '良好'

        rows.append({
            'id': rec.pk,
            'condition_id': cond.pk if cond else None,
            'date_label': f"{wdate:%Y/%m/%d} ({WEEKDAYS_JP[wdate.weekday()]})",
            'clock_in': clock_in_str,
            'clock_out': clock_out_str,
            'sleep_hours': sleep_str,
            'physical_condition': physical_str,
            'feeling': feeling_str,
            'ai_judgment': ai_judgement,
        })

    prev_y, prev_m = _shift_year_month(year, month, -1)
    next_y, next_m = _shift_year_month(year, month, 1)
    is_latest_month = (year, month) >= (latest_year, latest_month)

    return {
        'selected_month': f"{year:04d}-{month:02d}",
        'month_display': f"{year}年{month:02d}月",
        'prev_month': f"{prev_y:04d}-{prev_m:02d}",
        'next_month': f"{next_y:04d}-{next_m:02d}",
        'is_latest_month': is_latest_month,
        'rows': rows,
    }


def _to_aware_datetime(target_date, time_str):
    """'HH:MM' または ISO日時文字列を、タイムゾーン付きの datetime に変換"""
    if 'T' in time_str:
        dt = datetime.fromisoformat(time_str)
    else:
        parsed_time = datetime.strptime(time_str, '%H:%M').time()
        dt = datetime.combine(target_date, parsed_time)
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


# ---------------------------------------------------------------
# 00 / 01 / 02 / 03 / 20: エラー・認証・トップ・パスワード変更
# ---------------------------------------------------------------
def error_view(request):
    return render(request, '00-error.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('wsapp:03-top')

    if request.method == 'POST':
        employee_id = request.POST.get('emp_id', '').strip()
        password = request.POST.get('password', '')

        # USERNAME_FIELD = 'id' なので username に従業員IDを渡す
        user = authenticate(request, username=employee_id, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'{user.full_name} さん、ログインしました。')
            return redirect('wsapp:03-top')
        messages.error(request, '従業員IDまたはパスワードが正しくありません。')

    return render(request, '01-login.html')


@never_cache
@login_required
def logout_view(request):
    logout(request)
    response = render(request, '02-logout.html')
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@login_required
def index_view(request):
    today = timezone.localdate()
    today_record = WorkRecord.objects.filter(
        employee=request.user,
        working_date=today,
    ).first()

    recent_conditions = (
        Condition.objects.filter(employee=request.user)
        .select_related('physical_condition', 'feeling')
        .order_by('-date')[:5]
    )

    my_tasks = Task.objects.filter(employee=request.user).order_by('deadline', 'id')

    context = {
        'today': today,
        'today_record': today_record,
        'recent_conditions': recent_conditions,
        'my_tasks': my_tasks,
    }
    return render(request, '03-top.html', context)


@login_required
def password_update_view(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        new_password_confirm = request.POST.get('new_password_confirm', '')

        errors = []

        if not current_password:
            errors.append('現在のパスワードを入力してください。')
        elif not request.user.check_password(current_password):
            errors.append('現在のパスワードが正しくありません。')

        if not new_password or not new_password_confirm:
            errors.append('新しいパスワード（確認を含む）を入力してください。')
        elif new_password != new_password_confirm:
            errors.append('新しいパスワードと確認用パスワードが一致しません。')
        elif current_password and new_password == current_password:
            errors.append('新しいパスワードは現在のパスワードと異なるものを指定してください。')

        if new_password and new_password == new_password_confirm:
            try:
                validate_password(new_password, user=request.user)
            except ValidationError as exc:
                errors.extend(exc.messages)

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, '20-password-update.html')

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)

        messages.success(request, 'パスワードを更新しました。')
        return redirect('wsapp:03-top')

    return render(request, '20-password-update.html')


# ---------------------------------------------------------------
# 04 / 05 / 09 / 17 / 18: 勤怠打刻・勤務履歴・打刻一覧・打刻修正
# ---------------------------------------------------------------
@login_required
def clock_in(request):
    if request.method != 'POST':
        return redirect('wsapp:03-top')

    today = timezone.localdate()
    now = timezone.now()

    latest_condition = (
        Condition.objects.filter(employee=request.user, date__date=today)
        .order_by('-date')
        .first()
    )

    try:
        WorkRecord.objects.create(
            employee=request.user,
            working_date=today,
            clock_in=now,
            condition=latest_condition,
        )
        messages.success(
            request,
            f'出勤打刻が完了しました（{timezone.localtime(now):%H:%M}）。',
        )
    except IntegrityError:
        messages.warning(request, '本日の出勤記録はすでに登録されています。')

    return redirect('wsapp:03-top')


@login_required
def clock_out(request):
    if request.method != 'POST':
        return redirect('wsapp:03-top')

    today = timezone.localdate()
    record = get_object_or_404(WorkRecord, employee=request.user, working_date=today)

    if record.clock_out is not None:
        messages.warning(request, '本日の退勤打刻はすでに完了しています。')
    else:
        now = timezone.now()
        record.clock_out = now
        record.save(update_fields=['clock_out'])
        messages.success(
            request,
            f'退勤打刻が完了しました（{timezone.localtime(now):%H:%M}）。',
        )

    return redirect('wsapp:03-top')


@login_required
def attendance_view(request):
    if request.method == 'POST':
        return clock_in(request)

    today = timezone.localdate()
    today_record = WorkRecord.objects.filter(
        employee=request.user,
        working_date=today,
    ).first()
    return render(request, '04-attendance.html', {'today_record': today_record})


@login_required
def leaving_work_view(request):
    if request.method == 'POST':
        return clock_out(request)

    today = timezone.localdate()
    today_record = WorkRecord.objects.filter(
        employee=request.user,
        working_date=today,
    ).first()
    return render(request, '05-leaving-work.html', {'today_record': today_record})


@login_required
def working_history_view(request):
    today = timezone.localdate()
    year, month = _parse_year_month(request.GET.get('month'), today)
    payload = _build_month_history_payload(
        request.user, year, month, today.year, today.month
    )
    records = WorkRecord.objects.filter(employee=request.user).order_by('-working_date')
    return render(request, '09-working-history.html', {
        'records': records,
        'history_data': payload,
    })


@login_required
def working_history_api(request):
    today = timezone.localdate()
    year, month = _parse_year_month(request.GET.get('month'), today)
    payload = _build_month_history_payload(
        request.user, year, month, today.year, today.month
    )
    return JsonResponse(payload)


@login_required
def clock_in_list_view(request):
    target_date_str = request.GET.get('target_date', '').strip()

    base_qs = WorkRecord.objects.select_related('employee')
    if not getattr(request.user, 'authority', False):
        base_qs = base_qs.filter(employee=request.user)

    if target_date_str:
        try:
            selected_date_obj = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date_obj = timezone.localdate()
    else:
        selected_date_obj = timezone.localdate()

    field_obj = WorkRecord._meta.get_field('working_date')
    if field_obj.get_internal_type() == 'DateTimeField':
        start_dt = timezone.make_aware(datetime.combine(selected_date_obj, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(selected_date_obj, datetime.max.time()))
        qs = base_qs.filter(working_date__range=(start_dt, end_dt))
    else:
        qs = base_qs.filter(working_date=selected_date_obj)

    qs = qs.order_by('employee__id', 'id')

    def format_time_value(val):
        if not val:
            return '--:--'
        if hasattr(val, 'astimezone'):
            return timezone.localtime(val).strftime('%H:%M')
        if hasattr(val, 'strftime'):
            return val.strftime('%H:%M')
        return str(val)

    records = []
    for rec in qs:
        clock_in_val = (
            getattr(rec, 'clock_in', None)
            or getattr(rec, 'start_time', None)
            or getattr(rec, 'check_in', None)
        )
        clock_out_val = (
            getattr(rec, 'clock_out', None)
            or getattr(rec, 'end_time', None)
            or getattr(rec, 'check_out', None)
        )
        records.append(
            {
                'record_pk': rec.pk,
                'employee': rec.employee,
                'target_date': selected_date_obj,
                'clock_in_str': format_time_value(clock_in_val),
                'clock_out_str': format_time_value(clock_out_val),
            }
        )

    return render(
        request,
        '17-clock-in-list.html',
        {
            'records': records,
            'selected_date': selected_date_obj.strftime('%Y-%m-%d'),
        },
    )


@login_required
def clock_in_update_view(request, pk):
    qs = WorkRecord.objects.select_related('employee')
    if not getattr(request.user, 'authority', False):
        qs = qs.filter(employee=request.user)
    record = get_object_or_404(qs, pk=pk)

    if request.method == 'POST':
        work_date_str = request.POST.get('work_date', '').strip()
        clock_in_str = request.POST.get('clock_in', '').strip()
        clock_out_str = request.POST.get('clock_out', '').strip()
        change_reason = (
            request.POST.get('change_reason', '').strip()
            or request.POST.get('reason', '').strip()
        )

        if not change_reason:
            messages.error(request, '出退勤を修正する場合は変更理由を入力してください。')
            return render(request, '18-clock-in-update.html', {'record': record})

        target_date = record.working_date
        if work_date_str:
            try:
                target_date = datetime.strptime(work_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, '対象日の形式が正しくありません。')
                return render(request, '18-clock-in-update.html', {'record': record})

        try:
            if clock_in_str:
                record.clock_in = _to_aware_datetime(target_date, clock_in_str)

            if clock_out_str:
                record.clock_out = _to_aware_datetime(target_date, clock_out_str)
            else:
                record.clock_out = None
        except ValueError:
            messages.error(request, '出勤・退勤時間の形式が正しくありません。')
            return render(request, '18-clock-in-update.html', {'record': record})

        record.working_date = target_date
        record.change_reason = change_reason

        try:
            with transaction.atomic():
                record.save()
        except IntegrityError:
            messages.error(request, '指定した対象日の勤務記録がすでに存在します。')
            return render(request, '18-clock-in-update.html', {'record': record})

        messages.success(request, '勤務記録を更新しました。')
        return redirect('wsapp:17-clock-in-list')

    return render(request, '18-clock-in-update.html', {'record': record})


# ---------------------------------------------------------------
# 06 / 07 / 08 / 13: コンディション登録・AI判定・編集・一覧
# ---------------------------------------------------------------
@login_required
def condition_create(request):
    physical_conditions = PhysicalCondition.objects.order_by('id')
    feelings = Feeling.objects.order_by('id')

    if request.method == 'POST':
        sleep_raw = request.POST.get('sleep_time', '').strip()
        physical_id = request.POST.get('physical_condition', '').strip()
        feeling_id = request.POST.get('feeling', '').strip()

        physical = get_object_or_404(PhysicalCondition, pk=physical_id)
        feeling = get_object_or_404(Feeling, pk=feeling_id)

        sleep_time = None
        if sleep_raw:
            try:
                sleep_time = float(sleep_raw)
            except ValueError:
                messages.error(request, '睡眠時間は数値で入力してください。')
                return render(
                    request,
                    '06-condition-create.html',
                    {
                        'physical_conditions': physical_conditions,
                        'feelings': feelings,
                    },
                )

        condition = Condition.objects.create(
            employee=request.user,
            sleep_time=sleep_time,
            physical_condition=physical,
            feeling=feeling,
        )

        # 本日の勤務記録があれば最新のコンディションを紐付け
        today_record = WorkRecord.objects.filter(
            employee=request.user,
            working_date=timezone.localdate(),
        ).first()
        if today_record is not None:
            today_record.condition = condition
            today_record.save(update_fields=['condition'])

        messages.success(request, 'コンディションを登録しました。')
        return redirect('wsapp:03-top')

    context = {
        'physical_conditions': physical_conditions,
        'feelings': feelings,
    }
    return render(request, '06-condition-create.html', context)


@login_required
def condition_judgement_view(request, pk):
    condition = get_object_or_404(Condition, pk=pk, employee=request.user)
    return render(request, '07-condition-judgement.html', {'condition': condition})


@login_required
def condition_update_view(request, pk):
    condition = get_object_or_404(Condition, pk=pk, employee=request.user)
    return render(request, '08-condition-update.html', {'condition': condition})


@login_required
def condition_list_view(request):
    target_date_str = request.GET.get('target_date', '').strip()

    if target_date_str:
        try:
            parsed_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            parsed_date = timezone.localdate()
    else:
        parsed_date = timezone.localdate()

    selected_date = parsed_date.strftime('%Y-%m-%d')

    conditions = (
        Condition.objects.select_related('employee', 'physical_condition', 'feeling')
        .filter(date__date=parsed_date)
        .order_by('-date', 'employee_id')
    )

    return render(
        request,
        '13-condition-list.html',
        {
            'conditions': conditions,
            'selected_date': selected_date,
        },
    )


# ---------------------------------------------------------------
# 10 / 11 / 12: 従業員登録・編集・一覧
# ---------------------------------------------------------------
@login_required
def employee_create_view(request):
    if request.method == 'POST':
        last_name = request.POST.get('last_name', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        email = request.POST.get('email', '').strip()
        temp_password = request.POST.get('password', '').strip()
        role = request.POST.get('role', 'general').strip()

        if not all([last_name, first_name, email, temp_password]):
            messages.error(request, '必須項目を入力してください。')
            return render(request, '10-employee-create.html')

        is_admin = (role == 'admin')
        role_label = '管理者' if is_admin else '一般'

        try:
            user = User.objects.create_user(
                id=None,
                password=temp_password,
                last_name=last_name,
                given_name=first_name,
                email=email,
                authority=is_admin,
            )
        except IntegrityError:
            messages.error(request, 'すでに登録されているメールアドレスまたはユーザー情報です。')
            return render(request, '10-employee-create.html')

        subject = '【WORK STATUS】アカウント登録のご案内'
        message = (
            f"{user.full_name} さん\n\n"
            f"WORK STATUS のアカウントが登録されました。\n"
            f"ログイン情報は以下の通りです。\n\n"
            f"・メールアドレス：{email}\n"
            f"・仮パスワード：{temp_password}\n"
            f"・権限：{role_label}\n\n"
            f"ログイン後はセキュリティのためパスワードの変更をおすすめします。"
        )
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')

        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[email],
                fail_silently=False,
            )
            messages.success(
                request,
                f'{user.full_name} さんのアカウントを登録し、{email} へ仮パスワードを送信しました。',
            )
        except Exception:
            messages.warning(
                request,
                f'{user.full_name} さんのアカウントは登録しましたが、メール送信に失敗しました。メール設定を確認してください。',
            )

        return redirect('wsapp:12-employee-list')

    return render(request, '10-employee-create.html')


@login_required
def employee_update_view(request, pk):
    employee = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        last_name = request.POST.get('last_name', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        role = request.POST.get('role', 'general').strip()

        if not last_name or not first_name:
            messages.error(request, '姓と名を入力してください。')
            return render(
                request,
                '11-employee-update.html',
                {
                    'employee': employee,
                    'initial_last_name': last_name,
                    'initial_first_name': first_name,
                    'is_admin': (role == 'admin'),
                },
            )

        is_admin = (role == 'admin')
        employee.last_name = last_name
        employee.given_name = first_name
        employee.authority = is_admin

        try:
            employee.save(update_fields=['last_name', 'given_name', 'authority'])
        except IntegrityError:
            messages.error(request, '更新処理中にデータベースエラーが発生しました。')
            return render(
                request,
                '11-employee-update.html',
                {
                    'employee': employee,
                    'initial_last_name': last_name,
                    'initial_first_name': first_name,
                    'is_admin': is_admin,
                },
            )

        messages.success(request, f'{employee.full_name} さんの従業員情報を更新しました。')
        return redirect('wsapp:12-employee-list')

    return render(
        request,
        '11-employee-update.html',
        {
            'employee': employee,
            'initial_last_name': employee.last_name or '',
            'initial_first_name': employee.given_name or '',
            'is_admin': bool(employee.authority),
        },
    )


@login_required
def employee_list_view(request):
    employees = User.objects.order_by('id')
    return render(request, '12-employee-list.html', {'employees': employees})


# ---------------------------------------------------------------
# 14 / 15 / 16 / 19: タスク作成・更新・一覧・完了・完了確認
# ---------------------------------------------------------------
@login_required
def task_create_view(request):
    employees = User.objects.filter(is_active=True).order_by('id')

    if request.method == 'POST':
        task_name = request.POST.get('task_name', '').strip()
        assignee_id = request.POST.get('assignee', '').strip()
        deadline_str = request.POST.get('deadline', '').strip()
        detail = request.POST.get('detail', '').strip()

        form_data = {
            'task_name': task_name,
            'assignee': assignee_id,
            'deadline': deadline_str,
            'detail': detail,
        }

        if not all([task_name, assignee_id, deadline_str]):
            messages.error(request, 'タスク名・担当者・期限は必須です。')
            return render(
                request,
                '14-task-create.html',
                {'employees': employees, 'form_data': form_data},
            )

        assignee = get_object_or_404(User, pk=assignee_id)

        try:
            parsed_deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, '期限の日付形式が正しくありません。')
            return render(
                request,
                '14-task-create.html',
                {'employees': employees, 'form_data': form_data},
            )

        create_kwargs = {
            'task_name': task_name,
            'employee': assignee,
            'deadline': parsed_deadline,
            'detail': detail,
            'status': Task.Status.UNPROCESSED,
        }

        try:
            Task.objects.create(**create_kwargs)
        except IntegrityError:
            messages.error(request, 'タスクの登録中にデータベースエラーが発生しました。')
            return render(
                request,
                '14-task-create.html',
                {'employees': employees, 'form_data': form_data},
            )

        messages.success(request, f'タスク「{task_name}」を登録しました。')
        return redirect('wsapp:16-task-list')

    return render(
        request,
        '14-task-create.html',
        {'employees': employees, 'form_data': {}},
    )


@login_required
def task_update_view(request, pk):
    task = get_object_or_404(Task, pk=pk)
    employees = User.objects.filter(is_active=True).order_by('id')

    if request.method == 'POST':
        form_data = {
            'task_name': request.POST.get('task_name', '').strip(),
            'assignee': request.POST.get('assignee', '').strip(),
            'deadline': request.POST.get('deadline', '').strip(),
            'detail': request.POST.get('detail', '').strip(),
        }

        errors = []
        if not form_data['task_name']:
            errors.append('タスク名を入力してください。')

        assignee_user = None
        if not form_data['assignee']:
            errors.append('担当者を選択してください。')
        else:
            assignee_user = employees.filter(pk=form_data['assignee']).first()
            if not assignee_user:
                errors.append('有効な担当者を選択してください。')

        parsed_deadline = None
        if form_data['deadline']:
            try:
                parsed_date = datetime.strptime(form_data['deadline'], '%Y-%m-%d').date()
                naive_dt = datetime.combine(parsed_date, time(23, 59, 59))
                parsed_deadline = timezone.make_aware(naive_dt, timezone.get_current_timezone())
            except ValueError:
                errors.append('期限の日付形式が正しくありません。')

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(
                request,
                '15-task-update.html',
                {
                    'task': task,
                    'employees': employees,
                    'form_data': form_data,
                    'current_assignee_id': form_data['assignee'],
                },
            )

        task.task_name = form_data['task_name']
        task.employee = assignee_user
        task.deadline = parsed_deadline
        task.detail = form_data['detail']
        task.save()

        messages.success(request, 'タスクを更新しました。')
        return redirect('wsapp:16-task-list')

    current_deadline_str = ''
    if task.deadline:
        current_deadline_str = timezone.localtime(task.deadline).strftime('%Y-%m-%d')

    return render(
        request,
        '15-task-update.html',
        {
            'task': task,
            'employees': employees,
            'form_data': {
                'deadline': current_deadline_str,
            },
            'current_assignee_id': task.employee_id,
        },
    )


@login_required
def task_list_view(request):
    tasks = list(
        Task.objects.select_related('employee')
        .filter(is_completed=False)
        .order_by('deadline', '-id')
    )

    # 担当者ごとの最新コンディションを取得
    latest_condition_by_emp = {}
    for cond in Condition.objects.select_related('employee', 'physical_condition', 'feeling').order_by('-date', '-id'):
        if cond.employee_id and cond.employee_id not in latest_condition_by_emp:
            latest_condition_by_emp[cond.employee_id] = cond

    # 担当者ごとの残タスク数（is_completed=False の件数）を集計して業務負荷の判定に利用
    active_task_count_by_emp = {}
    for t in tasks:
        if not t.is_completed and t.employee_id:
            active_task_count_by_emp[t.employee_id] = active_task_count_by_emp.get(t.employee_id, 0) + 1

    def resolve_status_label(t):
        return t.get_status_display() or t.status or Task.Status.UNPROCESSED

    task_rows = []
    for t in tasks:
        cond = latest_condition_by_emp.get(t.employee_id)
        judgment = getattr(cond, 'ai_judgement', None) if cond else None
        if not judgment and cond:
            phys = getattr(getattr(cond, 'physical_condition', None), 'name', '') or ''
            feel = getattr(getattr(cond, 'feeling', None), 'name', '') or ''
            sleep_val = getattr(cond, 'sleep_time', None)
            if any(k in (phys + feel) for k in ('悪', '不調', 'イライラ', 'つら', '眠')) or (
                sleep_val is not None and float(sleep_val) < 5.0
            ):
                judgment = '要休息'
            else:
                judgment = '良好'
        cond_label = judgment or '良好'
        is_bad = any(k in cond_label for k in ('要', '注意', '悪', '不調'))
        is_high = active_task_count_by_emp.get(t.employee_id, 0) >= 3

        task_rows.append(
            {
                'task': t,
                'status_label': resolve_status_label(t),
                'condition_label': cond_label,
                'is_bad_condition': is_bad,
                'is_high_workload': is_high,
                'detail_text': t.detail or '',
            }
        )

    return render(
        request,
        '16-task-list.html',
        {
            'task_rows': task_rows,
        },
    )


@login_required
def task_complete_view(request, pk):
    task = get_object_or_404(Task, pk=pk)

    if request.method == 'POST':
        task.is_completed = True
        task.status = Task.Status.DONE
        task.save(update_fields=['is_completed', 'status'])

        messages.success(request, f'タスク「{task.task_name}」を完了にしました。')

    return redirect('wsapp:16-task-list')


@login_required
def task_check_view(request, pk):
    if request.method != 'POST':
        return redirect('wsapp:16-task-list')

    if not request.user.authority:
        raise PermissionDenied('完了フラグを変更できるのは管理者のみです。')

    task = get_object_or_404(Task, pk=pk)
    task.is_completed = not task.is_completed
    task.save(update_fields=['is_completed'])
    state_label = '完了確認済み' if task.is_completed else '未完了確認'
    messages.success(request, f'「{task.task_name}」を {state_label} にしました。')
    return redirect('wsapp:16-task-list')