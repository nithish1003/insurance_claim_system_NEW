import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from claims.models import AuditorReview

class Command(BaseCommand):
    help = 'Phase 7: Exports Auditor decision data for ML model fine-tuning.'

    def handle(self, *args, **options):
        reviews = AuditorReview.objects.select_related('claim', 'auditor').all()
        
        export_path = os.path.join(settings.BASE_DIR, 'ai_features/datasets/retraining_set_v2.csv')
        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        
        with open(export_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'claim_id', 'claim_type', 'claimed_amount', 'ai_risk_score', 
                'ai_predicted_amount', 'auditor_decision', 'auditor_approved_amount',
                'deviation', 'accuracy', 'auditor_id'
            ])
            
            for r in reviews:
                writer.writerow([
                    r.claim.claim_number,
                    r.claim.claim_type,
                    r.claim.claimed_amount,
                    r.claim.risk_score,
                    r.ai_original_amount,
                    r.decision,
                    r.recommended_amount,
                    r.deviation_amount,
                    r.accuracy_score,
                    r.auditor.id
                ])
        
        self.stdout.write(self.style.SUCCESS(f'Successfully exported {reviews.count()} reviews to {export_path}'))
