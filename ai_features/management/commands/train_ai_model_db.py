#!/usr/bin/env python
"""
Management command to train AI models using database data
Uses verified claims from database for continuous learning
"""

from django.core.management.base import BaseCommand
import subprocess
import sys
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Train AI models using verified claims from database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force training even if insufficient data',
        )
        parser.add_argument(
            '--reload',
            action='store_true',
            help='Reload AI service after training',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting database-driven AI training...')
        )
        
        # Change to the project directory
        project_dir = Path(__file__).parent.parent.parent.parent
        os.chdir(project_dir)
        
        try:
            # Run the database training script
            self.stdout.write('📊 Running database training script...')
            
            result = subprocess.run([
                sys.executable, 'insurance_claim_system/train_claim_type_db.py'
            ], capture_output=True, text=True, check=True)
            
            self.stdout.write(result.stdout)
            
            if result.stderr:
                self.stdout.write(self.style.WARNING(result.stderr))
            
            # Reload AI service if requested
            if options['reload']:
                self.stdout.write('🔄 Reloading AI service...')
                self._reload_ai_service()
            
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ Database-driven AI training completed successfully!'
                )
            )
            
        except subprocess.CalledProcessError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Training failed with error:')
            )
            self.stdout.write(e.stderr)
            raise
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Training failed with exception: {e}')
            )
            raise

    def _reload_ai_service(self):
        """Reload the AI service to use updated models"""
        try:
            from ai_features.services.ai_claim_service import AIClaimService
            
            service = AIClaimService()
            success = service.reload_model()
            
            if success:
                self.stdout.write(
                    self.style.SUCCESS('✅ AI service reloaded successfully')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('⚠️ AI service reload failed, using fallback')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ AI service reload failed: {e}')
            )