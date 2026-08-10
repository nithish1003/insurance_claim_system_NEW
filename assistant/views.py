import json
import time
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Avg, Q
from .models import AssistantSession, AssistantMessage, EscalationTicket, AssistantAuditLog, SupportTicket
from .services.router import AssistantRouter
from .services.security import mask_sensitive_data
from claims.models import Claim
from policy.models import UserPolicy
from django.contrib.auth import get_user_model
User = get_user_model()

def get_client_ip(request):
    """Auxiliary to extract client IP address."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

@csrf_exempt
def chat_api(request):
    """Entry point for the floating assistant dialogue (Guest + Auth)."""
    if request.method == 'POST':
        start_time = time.time()
        success = True
        try:
            data = json.loads(request.body)
            user_query = data.get('message', '').strip()
            
            if not user_query:
                return JsonResponse({'error': 'Empty message'}, status=400)

            # 1. Get or Create Session
            session_id = request.session.get('assistant_session_id')
            session = None
            if session_id:
                session = AssistantSession.objects.filter(id=session_id, is_active=True).first()

            if not session:
                user = request.user if request.user.is_authenticated else None
                role = getattr(request.user, 'role', 'guest') if user else 'guest'
                session = AssistantSession.objects.create(user=user, role_context=role)
                request.session['assistant_session_id'] = str(session.id)

            # 2. Persist User Message
            AssistantMessage.objects.create(session=session, sender='user', content=user_query)

            # 3. Neural Routing (with ChatGPT-style Session Memory)
            memory = request.session.get('assistant_memory', {})
            
            # CHECK TIMEOUT (10 minutes = 600 seconds)
            last_time = memory.get('last_message_time', 0)
            if time.time() - last_time > 600:
                memory = {} # Reset context on timeout
            
            memory['session_id'] = str(session.id)

            response_text, intent, confidence, is_escalated = AssistantRouter.route(user_query, request.user, memory)

            # UPDATE MEMORY for next message
            request.session['assistant_memory'] = {
                'last_topic': intent if intent != 'fallback' else memory.get('last_topic'),
                'last_intent': intent,
                'awaiting_reply': "?" in response_text,
                'last_options_presented': ["Personal records", "Benefits", "Policy types"] if "choose" in response_text.lower() else [],
                'user_role': getattr(request.user, 'role', 'guest') if request.user.is_authenticated else 'guest',
                'last_message_time': time.time()
            }

            # 4. Handle Escalation
            if is_escalated and not session.is_escalated:
                session.is_escalated = True
                session.save()
                EscalationTicket.objects.create(
                    session=session, user=session.user, 
                    transcript_summary=mask_sensitive_data(user_query),
                    priority='high' if confidence < 0.2 else 'medium'
                )

            # 5. Persist AI Response
            ai_msg = AssistantMessage.objects.create(
                session=session, sender='ai', content=response_text,
                intent_detected=intent, confidence_score=confidence
            )

            # 6. ENTERPRISE AUDIT LOGGING
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Map source logic
            source = 'faq'
            if is_escalated: source = 'escalation'
            elif intent == 'fallback': source = 'llm'
            elif confidence > 0.9 and intent != 'faq': source = 'db'

            AssistantAuditLog.objects.create(
                user=session.user,
                role=session.role_context,
                message_text=mask_sensitive_data(user_query),
                detected_intent=intent,
                confidence_score=confidence,
                response_source=source,
                response_time_ms=duration_ms,
                ip_address=get_client_ip(request),
                success_status=success
            )

            return JsonResponse({
                'response': response_text,
                'intent': intent,
                'confidence': f"{int(confidence * 100)}%",
                'escalated': is_escalated,
                'debug_mode': settings.DEBUG,
                'session_id': str(session.id),
                'message_id': ai_msg.id
            })

        except Exception as e:
            success = False
            # Log failure for forensic review
            AssistantAuditLog.objects.create(
                user=request.user if request.user.is_authenticated else None,
                role=getattr(request.user, 'role', 'guest'),
                message_text='[ERROR] Exception occurred',
                detected_intent='system_error',
                confidence_score=0.0,
                response_source='faq',
                response_time_ms=0,
                ip_address=get_client_ip(request),
                success_status=False
            )
            return JsonResponse({'error': f'Assistant malfunction: {str(e)}'}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def submit_feedback(request):
    """Asynchronously collect user sentiment (Helpful/Not Helpful)."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message_id = data.get('message_id')
            value = data.get('value')
            msg = AssistantMessage.objects.get(id=message_id, sender='ai')
            msg.feedback_value = value
            msg.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=405)

@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_panel(request):
    """Mission Control for the Neural Assistant."""
    today = timezone.now().date()
    
    # Core Metrics
    total_chats_today = AssistantSession.objects.filter(created_at__date=today).count()
    active_users_today = AssistantSession.objects.filter(created_at__date=today).values('user').distinct().count()
    
    # Intent Distribution
    top_intents = AssistantMessage.objects.filter(sender='ai')\
        .values('intent_detected')\
        .annotate(count=Count('intent_detected'))\
        .order_by('-count')[:10]
    
    # Accuracy & Fallbacks
    unresolved_count = AssistantMessage.objects.filter(intent_detected='fallback').count()
    avg_confidence = AssistantMessage.objects.filter(sender='ai').aggregate(Avg('confidence_score'))['confidence_score__avg'] or 0
    
    # Feedback Metrics
    feedback_stats = AssistantMessage.objects.filter(sender='ai', feedback_value__isnull=False)\
        .values('intent_detected')\
        .annotate(avg_score=Avg('feedback_value'), total=Count('id')).order_by('-avg_score')

    total_positive = AssistantMessage.objects.filter(feedback_value=1).count()
    total_negative = AssistantMessage.objects.filter(feedback_value=-1).count()

    # Role Usage
    role_usage = AssistantSession.objects.values('role_context').annotate(count=Count('role_context'))
    
    # Activity Trend
    last_7_days = []
    for i in range(7):
        date = today - timedelta(days=i)
        count = AssistantSession.objects.filter(created_at__date=date).count()
        last_7_days.append({'date': date.strftime('%d %b'), 'count': count})
    last_7_days.reverse()

    # Priority Escalations
    recent_escalations = EscalationTicket.objects.all().select_related('user', 'session').order_by('-created_at')[:10]

    context = {
        'total_chats_today': total_chats_today,
        'active_users_today': active_users_today,
        'top_intents': top_intents,
        'unresolved_count': unresolved_count,
        'avg_confidence': int(avg_confidence * 100),
        'total_positive': total_positive,
        'total_negative': total_negative,
        'feedback_stats': feedback_stats,
        'role_usage': list(role_usage),
        'trend_dates': [d['date'] for d in last_7_days],
        'trend_counts': [d['count'] for d in last_7_days],
        'intent_labels': [i['intent_detected'] or 'Unknown' for i in top_intents],
        'intent_values': [i['count'] for i in top_intents],
        'recent_escalations': recent_escalations,
    }
    return render(request, 'assistant/admin_panel.html', context)

from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from policy.models import UserPolicy, Payment

@login_required
def download_policy(request, policy_id):
    """Securely serve policy PDF to the owner."""
    policy = get_object_or_404(UserPolicy, id=policy_id)
    
    # Ownership Validation
    if policy.user != request.user and not request.user.is_staff:
        return HttpResponseForbidden("You do not have permission to download this document.")
    
    if not policy.rc_upload:
        return JsonResponse({'error': 'Policy document not found.'}, status=404)
        
    return FileResponse(policy.rc_upload.open(), as_attachment=True, filename=f"Policy_{policy.certificate_number}.pdf")

@login_required
def download_receipt(request, payment_id):
    """Securely serve payment receipt to the owner."""
    payment = get_object_or_404(Payment, id=payment_id)
    
    # Ownership Validation
    if payment.user != request.user and not request.user.is_staff:
        return HttpResponseForbidden("You do not have permission to download this receipt.")
        
    # We use a simple text/json response as a placeholder if real PDF generation isn't ready
    # but in a real system this would return a generated PDF.
    response = JsonResponse({
        'transaction_id': payment.transaction_id,
        'amount': str(payment.amount),
        'date': payment.created_at.strftime('%Y-%m-%d'),
        'status': payment.payment_status,
        'method': payment.payment_method
    })
    response['Content-Disposition'] = f'attachment; filename="Receipt_{payment.transaction_id}.json"'
    return response

@login_required
def autocomplete_search(request):
    """
    Production-grade Universal Search Engine for ClaimIQ AI.
    Features: Category Grouping, Prefix Commands, NLP Parsing, Data Masking.
    """
    query = request.GET.get('q', '').strip().lower()
    role = getattr(request.user, 'role', 'staff')
    is_admin = request.user.is_superuser or role == 'admin'
    
    if len(query) < 2:
        return JsonResponse({'results': []})

    results = []
    
    # 🕵️ 1. Prefix Parsing (e.g., 'policy:CERT-')
    prefix = None
    search_query = query
    if ':' in query:
        parts = query.split(':', 1)
        prefix = parts[0]
        search_query = parts[1].strip()
    
    # 🕵️ 2. Natural Language Date Parsing (Simple)
    today_filter = False
    if 'today' in search_query:
        today_filter = True
        search_query = search_query.replace('today', '').strip()
    
    # 🕵️ 3. INTERNAL RECORD LOGGING
    print(f"[SEARCH AUDIT] {request.user.username} searched for: {query}")

    # --- CATEGORY: CUSTOMERS ---
    if not prefix or prefix == 'user':
        users = User.objects.filter(
            Q(username__icontains=search_query) | 
            Q(first_name__icontains=search_query) | 
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        ).distinct()[:5]
        for u in users:
            results.append({
                'category': 'Customers',
                'title': f"{u.first_name} {u.last_name[0]}." if u.first_name and u.last_name else u.username,
                'subtitle': f"{u.email[:2]}***@{u.email.split('@')[-1]}" if '@' in u.email else 'Private',
                'value': u.username
            })

    # --- CATEGORY: POLICIES ---
    if not prefix or prefix == 'policy':
        policies_qs = UserPolicy.objects.all()
        if 'expired' in search_query: policies_qs = policies_qs.filter(status='expired')
        
        policies = policies_qs.filter(
            Q(certificate_number__icontains=search_query.replace('expired', '').strip()) |
            Q(policy__plan__name__icontains=search_query.replace('expired', '').strip())
        )[:5]
        for p in policies:
            results.append({
                'category': 'Policies',
                'title': p.certificate_number,
                'subtitle': f"{p.policy.plan.name if p.policy and p.policy.plan else 'Standard'} | {p.status.upper()}",
                'value': p.certificate_number
            })

    # --- CATEGORY: CLAIMS ---
    if not prefix or prefix == 'claim':
        claims_qs = Claim.objects.all()
        if today_filter: claims_qs = claims_qs.filter(created_at__date=timezone.now().date())
        if 'pending' in search_query: claims_qs = claims_qs.filter(status__in=['submitted', 'under_review'])
        
        clean_q = search_query.replace('pending', '').strip()
        claims = claims_qs.filter(claim_number__icontains=clean_q)[:5]
        for c in claims:
            results.append({
                'category': 'Claims',
                'title': c.claim_number,
                'subtitle': f"Status: {c.status.upper()} | ₹{c.claimed_amount}",
                'value': c.claim_number
            })

    # --- CATEGORY: TICKETS ---
    if not prefix or prefix == 'ticket':
        tickets = SupportTicket.objects.filter(
            Q(ticket_id__icontains=search_query) | 
            Q(subject__icontains=search_query)
        )[:5]
        for t in tickets:
            results.append({
                'category': 'Tickets',
                'title': t.ticket_id,
                'subtitle': t.subject,
                'value': t.ticket_id
            })

    # --- ADMIN ONLY: PAYMENTS ---
    if is_admin and (not prefix or prefix == 'payment'):
        from policy.models import Payment
        payments = Payment.objects.filter(
            Q(transaction_id__icontains=search_query) |
            Q(payment_status__icontains=search_query)
        )[:5]
        for p in payments:
            results.append({
                'category': 'Payments',
                'title': p.transaction_id,
                'subtitle': f"₹{p.amount} | {p.payment_status.upper()}",
                'value': p.transaction_id
            })

    # --- ADMIN ONLY: STAFF ---
    if is_admin and (not prefix or prefix == 'staff'):
        staff = User.objects.filter(is_staff=True).filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query)
        )[:5]
        for s in staff:
            results.append({
                'category': 'Staff Users',
                'title': f"Staff: {s.username}",
                'subtitle': "Internal Access Root",
                'value': s.username
            })

    return JsonResponse({'results': results})
