from django.test import SimpleTestCase
from unittest.mock import patch

from ai_features.services.ocr_service import OCRService


class AadhaarOCRServiceTests(SimpleTestCase):
    def setUp(self):
        self.service = OCRService()

    def test_extract_english_aadhaar_name_ignores_hindi_lines(self):
        text = "\n".join([
            "भारत सरकार",
            "Government of India",
            "राम कुमार",
            "RAVI KUMAR",
            "DOB : 01/01/1990",
            "1234 5678 9012",
        ])

        extracted_name = self.service._extract_english_aadhaar_name(text)

        self.assertEqual(extracted_name, "RAVI KUMAR")

    @patch.object(OCRService, "extract_text")
    def test_verify_aadhaar_requires_number_and_english_name_match(self, mock_extract_text):
        mock_extract_text.return_value = "\n".join([
            "Government of India",
            "RAVI KUMAR",
            "DOB : 01/01/1990",
            "1234 5678 9012",
        ])

        result = self.service.verify_aadhaar(
            "dummy-path.png",
            expected_name="Ravi Kumar",
            expected_number="123456789012",
        )

        self.assertTrue(result["verified"])
        self.assertTrue(result["name_match"])
        self.assertTrue(result["number_match"])
        self.assertEqual(result["extracted_name"], "RAVI KUMAR")

    @patch.object(OCRService, "extract_text")
    def test_verify_aadhaar_fails_when_english_name_does_not_match(self, mock_extract_text):
        mock_extract_text.return_value = "\n".join([
            "Government of India",
            "SURESH KUMAR",
            "DOB : 01/01/1990",
            "1234 5678 9012",
        ])

        result = self.service.verify_aadhaar(
            "dummy-path.png",
            expected_name="Ravi Kumar",
            expected_number="123456789012",
        )

        self.assertFalse(result["verified"])
        self.assertFalse(result["name_match"])
        self.assertTrue(result["number_match"])
