#!/usr/bin/env python
"""
Management command to train AI models for the insurance claim system
"""

from django.core.management.base import BaseCommand
import subprocess
import sys
import os
from pathlib import Path


class Command(BaseCommand):
    help = 'Train AI models for claim type, fraud detection, and amount prediction'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force retraining even if models already exist',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting AI model training...')
        )
        
        # Change to the ai_features directory
        ai_features_dir = Path(__file__).parent.parent.parent
        os.chdir(ai_features_dir)
        
        scripts = [
            'train_claim_type.py',
            'train_fraud_model.py', 
            'train_amount_model.py'
        ]
        
        success_count = 0
        
        for script in scripts:
            self.stdout.write(f'Running {script}...')
            
            try:
                result = subprocess.run([
                    sys.executable, script
                ], capture_output=True, text=True, check=True)
                
                self.stdout.write(
                    self.style.SUCCESS(f'✓ {script} completed successfully')
                )
                if result.stdout:
                    self.stdout.write(result.stdout)
                success_count += 1
                
            except subprocess.CalledProcessError as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ {script} failed with error:')
                )
                self.stdout.write(e.stderr)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ {script} failed with exception: {e}')
                )
        
        if success_count == len(scripts):
            self.stdout.write(
                self.style.SUCCESS(
                    f'All {success_count} AI models trained successfully!'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'Only {success_count}/{len(scripts)} models trained successfully'
                )
            )