from .models import Notification

def notifications_processor(request):
    if request.user.is_authenticated:
        unread_notifications = Notification.objects.filter(user=request.user, is_read=False)
        latest_notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:10]
        return {
            'unread_notifications_count': unread_notifications.count(),
            'latest_notifications': latest_notifications,
        }
    return {
        'unread_notifications_count': 0,
        'latest_notifications': [],
    }
