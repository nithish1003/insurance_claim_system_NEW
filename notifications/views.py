import json
import re
from rest_framework import viewsets, status, decorators
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from .models import Notification, NotificationPreference
from .serializers import NotificationSerializer
from claims.models import Claim

CLAIM_NUMBER_RE = re.compile(r'\bCLM-[A-Za-z0-9_-]+\b')


def resolve_notification_claim(notification):
    """
    Resolve a claim notification from its stored public_id first, then from
    the claim number embedded in older notification messages.
    """
    claim = None

    if notification.related_claim_id:
        claim = Claim.objects.filter(public_id=notification.related_claim_id).first()

    if not claim:
        text_to_search = f"{notification.title} {notification.message}"
        match = CLAIM_NUMBER_RE.search(text_to_search)
        if match:
            claim = Claim.objects.filter(claim_number__iexact=match.group(0)).first()

    if claim and notification.related_claim_id != claim.public_id:
        Notification.objects.filter(id=notification.id).update(related_claim_id=claim.public_id)
        notification.related_claim_id = claim.public_id

    return claim


def clear_orphaned_claim_notifications(queryset):
    """
    Hide stale claim notifications whose referenced claim no longer exists.
    This keeps dashboards from showing links that can only redirect to a warning.
    """
    orphaned_ids = []
    claim_notifications = queryset.filter(related_claim_id__isnull=False)

    for notification in claim_notifications:
        if not resolve_notification_claim(notification):
            orphaned_ids.append(notification.id)

    if orphaned_ids:
        Notification.objects.filter(id__in=orphaned_ids).update(is_cleared=True)

    return queryset.exclude(id__in=orphaned_ids)

class NotificationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing user notifications.
    Supports list, read, clear, and clear-all operations.
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication, JWTAuthentication]

    def get_queryset(self):
        # Admin sees all system alerts, Staff sees claim-related, User sees personal
        # This is naturally handled by the .filter(user=request.user) for this specific requirement
        # as notifications are created for specific users.
        queryset = Notification.objects.filter(user=self.request.user, is_cleared=False)
        queryset = clear_orphaned_claim_notifications(queryset)
        
        # 🛡️ DYNAMIC FILTERING: Support tab-based views (Read/Unread)
        is_read_param = self.request.query_params.get('is_read')
        if is_read_param is not None:
            is_read = is_read_param.lower() == 'true'
            queryset = queryset.filter(is_read=is_read)
            
        return queryset.order_by('-created_at')

    @decorators.action(detail=True, methods=['patch'])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_as_read()
        return Response({'status': 'read'})

    @decorators.action(detail=True, methods=['patch'])
    def clear(self, request, pk=None):
        notification = self.get_object()
        notification.clear()
        return Response({'status': 'cleared'})

    @decorators.action(detail=False, methods=['patch'], url_path='clear-all')
    def clear_all(self, request):
        self.get_queryset().update(is_cleared=True)
        return Response({'status': 'all_cleared'})

    @decorators.action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})

from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Avg, Q, F
from django.db import models as dj_models
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings

@login_required
def notifications_page(request):
    """Full Notification History Page (HTML)"""
    return render(request, 'notifications/full_list.html')

@staff_member_required
def admin_notification_center(request):
    """
    Executive Mission Control for system-wide communication tracking.
    Aggregates delivery rates, unread counts, and engagement trends.
    """
    time_threshold = timezone.now() - timedelta(days=30)
    
    # 📈 KPI Aggregation
    total_alerts = Notification.objects.filter(created_at__gte=time_threshold).count()
    unread_alerts = Notification.objects.filter(is_read=False).count()
    
    delivery_stats = Notification.objects.aggregate(
        emails=Count('id', filter=Q(delivered_email=True)),
        sms=Count('id', filter=Q(delivered_sms=True)),
        push=Count('id', filter=Q(delivered_push=True)),
        errors=Count('id', filter=Q(delivery_error__isnull=False))
    )

    # ⏱️ Engagement Analysis
    avg_response_time = Notification.objects.filter(
        is_read=True, 
        read_at__isnull=False
    ).annotate(
        duration=F('read_at') - F('created_at')
    ).aggregate(Avg('duration'))['duration__avg']

    # 📊 Chart Data: Daily Trend (Last 7 Days)
    daily_trend = Notification.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    ).extra(select={'day': "date(created_at)"}).values('day').annotate(count=Count('id')).order_by('day')

    # 📱 TWILIO READINESS CHECK
    twilio_sid_loaded = bool(settings.TWILIO_ACCOUNT_SID)
    twilio_token_loaded = bool(settings.TWILIO_AUTH_TOKEN)
    twilio_number_loaded = bool(settings.TWILIO_PHONE_NUMBER)

    context = {
        'total_alerts': total_alerts,
        'unread_alerts': unread_alerts,
        'emails_sent': delivery_stats['emails'],
        'sms_sent': delivery_stats['sms'],
        'push_sent': delivery_stats['push'],
        'error_count': delivery_stats['errors'],
        'avg_response': str(avg_response_time).split('.')[0] if avg_response_time else "N/A",
        'daily_trend_js': json.dumps(list(daily_trend), default=str),
        
        # 🛡️ Twilio Mission Control Data
        'twilio_creds_ok': twilio_sid_loaded and twilio_token_loaded,
        'twilio_number_active': twilio_number_loaded
    }
    
    return render(request, 'notifications/admin_center.html', context)

@login_required
def notification_settings_view(request):
    """User Preferences Page for Notification Channels."""
    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # Handle toggle updates
        prefs.email_enabled = request.POST.get('email_enabled') == 'on'
        prefs.sms_enabled = request.POST.get('sms_enabled') == 'on'
        prefs.realtime_enabled = request.POST.get('realtime_enabled') == 'on'
        prefs.claim_updates = request.POST.get('claim_updates') == 'on'
        prefs.save()
        
    return render(request, 'notifications/settings.html', {'prefs': prefs})

@login_required
def notification_list_view(request):
    """
    Standard UI view for the Notification Inbox.
    Fetches the user's uncleared notifications for display.
    """
    notifications = Notification.objects.filter(
        user=request.user, 
        is_cleared=False
    )
    notifications = clear_orphaned_claim_notifications(notifications).order_by('-created_at')
    
    return render(request, 'notifications/list.html', {
        'notifications': notifications
    })

from django.contrib import messages
from django.shortcuts import redirect

@login_required
def notification_redirect(request, pk):
    """
    SaaS-grade redirection engine. Resolves and routes user to the correct 
    target page based on their role and claim existence. Handles orphaned notifications 
    by resolving them dynamically (e.g. from deleted & re-seeded database items) and
    safely redirects with a friendly error notice instead of raising 404.
    """
    notification = get_object_or_404(Notification, id=pk, user=request.user)
    
    # Mark as read immediately when user clicks the notification
    if not notification.is_read:
        notification.mark_as_read()
    
    # 1. Determine redirect destination based on payment if applicable
    if notification.related_payment_id:
        return redirect('premiums:pay', payment_id=notification.related_payment_id)
    
    # 2. Check if a claim is associated, including legacy message-only links
    claim = resolve_notification_claim(notification)
    if notification.related_claim_id or CLAIM_NUMBER_RE.search(f"{notification.title} {notification.message}"):
        if claim:
            user_role = getattr(request.user, 'role', 'user')
            is_admin = user_role == 'admin' or request.user.is_superuser
            is_staff = user_role == 'staff' or request.user.is_staff
            
            if is_admin:
                return redirect('claim:review', id=claim.public_id)
            elif is_staff:
                return redirect('claim:staff_review', id=claim.public_id)
            else:
                return redirect('claim:detail', id=claim.public_id)
        else:
            notification.clear()
            messages.warning(request, "The claim associated with this notification could not be found.")
            
    # Default fallback: redirect to appropriate dashboard based on user role
    user_role = getattr(request.user, 'role', 'user')
    if user_role == 'admin' or request.user.is_superuser:
        return redirect('accounts:admin_dashboard')
    elif user_role == 'staff' or request.user.is_staff:
        return redirect('accounts:staff_dashboard')
    else:
        return redirect('accounts:policyholder_dashboard')
