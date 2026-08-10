from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    created_at_human = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'title', 'message', 'type', 
            'is_read', 'is_cleared', 'created_at', 
            'expires_at', 'related_claim_id', 'related_payment_id',
            'role_target', 'created_at_human'
        ]
        read_only_fields = ['id', 'user', 'created_at']

    def get_created_at_human(self, obj):
        from django.utils.timesince import timesince
        from django.utils import timezone
        return f"{timesince(obj.created_at, timezone.now())} ago"
