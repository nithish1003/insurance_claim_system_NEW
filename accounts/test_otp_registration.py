from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

from accounts.models import User, OTPVerification
from accounts.otp_service import OTPService


class OTPRegistrationTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.send_url = reverse('accounts:register_send_otp')
        self.verify_url = reverse('accounts:register_verify_otp')
        
        self.valid_data = {
            'full_name': 'Test User',
            'username': 'testuser',
            'email': 'test@example.com',
            'phone': '+919876543210',
            'password': 'Password123!',
        }

    @patch('notifications.services.NotificationService.send_html_email')
    @patch('notifications.sms_service.TextBeeSMSService.send_sms')
    def test_send_otp_success(self, mock_sms, mock_email):
        mock_email.return_value = True
        mock_sms.return_value = True

        # Need to establish a session first
        self.client.session.create()

        response = self.client.post(self.send_url, self.valid_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        
        # Verify DB records
        self.assertEqual(OTPVerification.objects.count(), 2)
        email_otp = OTPVerification.objects.get(purpose='email_verify')
        sms_otp = OTPVerification.objects.get(purpose='phone_verify')
        
        self.assertEqual(email_otp.email, 'test@example.com')
        self.assertEqual(sms_otp.phone, '+919876543210')

        # Session data
        self.assertIn('reg_data', self.client.session)
        self.assertEqual(self.client.session['reg_data']['username'], 'testuser')

    @patch('notifications.services.NotificationService.send_html_email')
    @patch('notifications.sms_service.TextBeeSMSService.send_sms')
    def test_verify_otp_success(self, mock_sms, mock_email):
        mock_email.return_value = True
        mock_sms.return_value = True

        self.client.session.create()
        self.client.post(self.send_url, self.valid_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        email_otp = OTPVerification.objects.get(purpose='email_verify').otp_code
        sms_otp = OTPVerification.objects.get(purpose='phone_verify').otp_code

        verify_data = {
            'email_otp': email_otp,
            'sms_otp': sms_otp,
        }
        
        response = self.client.post(self.verify_url, verify_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertTrue(self.client.session['otp_verified'])

    @patch('notifications.services.NotificationService.send_html_email')
    @patch('notifications.sms_service.TextBeeSMSService.send_sms')
    def test_verify_otp_invalid_code(self, mock_sms, mock_email):
        mock_email.return_value = True
        mock_sms.return_value = True

        self.client.session.create()
        self.client.post(self.send_url, self.valid_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        verify_data = {
            'email_otp': '000000',
            'sms_otp': '000000',
        }
        
        response = self.client.post(self.verify_url, verify_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('email_otp', data['errors'])
        self.assertIn('sms_otp', data['errors'])
        
        # Verify attempt counter increased
        email_otp_obj = OTPVerification.objects.get(purpose='email_verify')
        self.assertEqual(email_otp_obj.attempts, 1)

    @patch('notifications.services.NotificationService.send_html_email')
    @patch('notifications.sms_service.TextBeeSMSService.send_sms')
    def test_duplicate_email(self, mock_sms, mock_email):
        User.objects.create(username='existing', email='test@example.com')
        
        response = self.client.post(self.send_url, self.valid_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = response.json()
        
        self.assertFalse(data['success'])
        self.assertIn('email', data['errors'])
        self.assertEqual(data['errors']['email'], 'Email already exists.')

