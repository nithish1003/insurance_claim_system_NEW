from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from .models import User

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['username'] = user.username
        token['role'] = user.role
        
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Add custom info to the response
        data['username'] = self.user.username
        data['role'] = self.user.role
        return data

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'phone', 'address']
        read_only_fields = ['role']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'phone', 'address']

    def create(self, validated_data):
        """
        🛡️ Hardened API Logic: Role is forced to 'user' in the backend,
        ignoring any attempt to pass a role via API parameters.
        """
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            role='user', # 🔐 Forced role
            phone=validated_data.get('phone', ''),
            address=validated_data.get('address', '')
        )
        return user
