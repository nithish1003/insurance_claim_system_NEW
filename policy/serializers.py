from rest_framework import serializers
from .models import PolicyType

class PolicyTypeSerializer(serializers.ModelSerializer):
    # Dynamically calculate the plan count for the category
    plans_count = serializers.SerializerMethodField()

    class Meta:
        model = PolicyType
        fields = [
            'id', 'name', 'code', 'description', 
            'plans_count', 'status', 'category_type', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_plans_count(self, obj):
        # Delegate to the model's property for consistency
        return obj.plans_count

from .models import Policy

class PolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = Policy
        fields = [
            'id', 'public_id', 'policy_number', 'insurer_name', 'policy_type',
            'sum_insured', 'base_premium', 'gross_premium', 'deductible',
            'room_rent_limit_per_day', 'status', 'created_at'
        ]
        read_only_fields = ['id', 'public_id', 'policy_number', 'created_at']
