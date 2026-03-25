# AI Learning Pipeline Documentation

## 🎯 Overview

This document describes the production-ready AI learning pipeline that enables continuous learning from verified claims in the database, replacing the CSV-only training approach.

## 🔄 Learning Flow

```
User submits claim
    ↓
AI predicts (ai_claim_type, confidence_score)
    ↓
Stored in DB with ai_claim_type
    ↓
Staff verifies (final_claim_type)
    ↓
Verified data stored in DB
    ↓
Training script uses DB data (ONLY final_claim_type)
    ↓
Model retrained periodically
    ↓
AI service reloads updated model
    ↓
AI becomes smarter over time
```

## 📁 Files Structure

```
insurance_claim_system/
├── train_claim_type_db.py          # Database training script
└── dataset_claim_type.csv          # CSV fallback (legacy)

ai_features/
├── services/
│   └── ai_claim_service.py         # Enhanced with model reloading
└── management/commands/
    ├── train_ai_models.py          # Original CSV training
    └── train_ai_model_db.py        # NEW: Database training command
```

## 🚀 Usage

### 1. Manual Database Training

```bash
# Train using database data
python manage.py train_ai_model_db

# Force training even with insufficient data
python manage.py train_ai_model_db --force

# Train and reload AI service
python manage.py train_ai_model_db --reload
```

### 2. Direct Script Execution

```bash
# Run training script directly
python insurance_claim_system/train_claim_type_db.py
```

### 3. Scheduled Training (Recommended)

Add to crontab for automatic training:

```bash
# Train every day at 2 AM
0 2 * * * cd /path/to/project && python manage.py train_ai_model_db --reload
```

## 📊 Database Requirements

### Claim Model Fields Used

- `description` → Input text for training
- `final_claim_type` → Training label (ONLY verified data)

### Safe Training Conditions

- **Minimum Records**: 20 verified claims required
- **Data Validation**: Skip empty descriptions or missing final_claim_type
- **Error Handling**: Graceful fallback if training fails

### Query Logic

```python
# Fetch verified claims for training
verified_claims = Claim.objects.exclude(
    final_claim_type__isnull=True
).exclude(
    final_claim_type=''
)
```

## 🔧 Technical Implementation

### 1. Database Training Script (`train_claim_type_db.py`)

**Features:**
- Fetches verified claims from database
- Uses TF-IDF + Logistic Regression
- Validates training data quality
- Comprehensive logging
- Model evaluation and saving

**Key Components:**
```python
# Safe data fetching
verified_claims = Claim.objects.exclude(final_claim_type__isnull=True)

# Data validation
if total_records < 20:
    logger.warning("Skipping training: Insufficient data")

# Model training with validation
X_train, X_test, y_train, y_test = train_test_split(...)
model.fit(X_train_vec, y_train)

# Save to proper location
model_path = Path('ai_features/models/claim_type_model.pkl')
```

### 2. Enhanced AI Service (`ai_claim_service.py`)

**Features:**
- Database model priority (fallback to CSV)
- Model reloading capability
- Singleton pattern with safe updates
- Model information tracking

**Key Methods:**
```python
def reload_model(self):
    """Reload model after database training"""
    self._model = None
    self._vectorizer = None
    self._load_model()

def get_model_info(self):
    """Get current model status"""
    return {
        'model_path': self._model_path,
        'status': 'loaded' if self._model else 'fallback'
    }
```

### 3. Management Command (`train_ai_model_db.py`)

**Features:**
- Django management command interface
- Optional model reloading
- Error handling and logging
- Integration with Django ecosystem

## 🔄 Model Loading Priority

1. **Database-trained models** (preferred)
   - `ai_features/models/claim_type_model.pkl`
   - `ai_features/models/claim_type_vectorizer.pkl`

2. **CSV-trained models** (fallback)
   - `claim_model.pkl`
   - `vectorizer.pkl`

3. **Rule-based logic** (final fallback)
   - Keyword matching when no models available

## 📈 Training Data Quality

### Data Sources Priority

1. **Verified Claims** (highest quality)
   - `final_claim_type` is not null
   - Staff has verified the claim type
   - Used for database training

2. **AI Predictions** (medium quality)
   - `ai_claim_type` from ML model
   - Used for initial predictions
   - Not used for training (avoid feedback loops)

3. **Raw Claims** (lowest quality)
   - No verification yet
   - Used only for predictions
   - Wait for staff verification

### Data Validation Rules

- Skip claims with empty descriptions
- Skip claims with missing `final_claim_type`
- Minimum 20 verified claims required
- Stratified sampling for train/test split

## 🛡️ Safety Features

### 1. Safe Training Conditions
```python
if total_records < 20:
    logger.warning("Skipping training: Insufficient data")
    return False
```

### 2. Model Reloading Safety
```python
def reload_model(self):
    try:
        self._model = None
        self._vectorizer = None
        self._load_model()
        return True
    except Exception as e:
        logger.error(f"Model reload failed: {e}")
        return False
```

### 3. Fallback Mechanism
- If database models fail → use CSV models
- If CSV models fail → use rule-based logic
- System remains functional even without ML models

## 📊 Monitoring & Logging

### Training Logs
```
2024-01-01 10:00:00 - INFO - 🚀 Starting database-driven training pipeline...
2024-01-01 10:00:01 - INFO - 📊 Fetching verified claims from database...
2024-01-01 10:00:02 - INFO - 📋 Found 150 verified claims
2024-01-01 10:00:03 - INFO - ✅ Using 150 valid records for training
2024-01-01 10:00:05 - INFO - 🤖 Training Logistic Regression model...
2024-01-01 10:00:08 - INFO - 🎯 Model accuracy: 0.92
2024-01-01 10:00:09 - INFO - ✅ Model saved to: ai_features/models/claim_type_model.pkl
2024-01-01 10:00:10 - INFO - 🎉 Training completed successfully!
```

### AI Service Logs
```
2024-01-01 10:00:15 - INFO - ✅ Database-trained ML model and vectorizer loaded successfully
2024-01-01 10:00:20 - INFO - ML prediction: accident (0.85)
2024-01-01 10:00:25 - INFO - 🔄 Reloading AI model...
2024-01-01 10:00:26 - INFO - ✅ Model reloaded successfully
```

## 🧪 Testing

### 1. Test Database Training
```bash
# Check if training works
python insurance_claim_system/train_claim_type_db.py

# Check AI service
python ai_features/test_ml_integration.py
```

### 2. Test Management Command
```bash
# Test training command
python manage.py train_ai_model_db

# Test with reload
python manage.py train_ai_model_db --reload
```

### 3. Verify Model Loading
```python
from ai_features.services.ai_claim_service import AIClaimService

service = AIClaimService()
model_info = service.get_model_info()
print(model_info)
# Output: {'model_path': '...', 'status': 'loaded', 'classes': ['accident', 'medical', 'theft', 'other']}
```

## 📋 Production Checklist

- [ ] Database has verified claims (`final_claim_type` populated)
- [ ] Model directory exists: `ai_features/models/`
- [ ] Training script has proper permissions
- [ ] Logging directory is writable
- [ ] Management command is registered
- [ ] Scheduled training is configured (optional)
- [ ] Monitoring for training success/failure
- [ ] Backup of previous models (optional)

## 🔧 Troubleshooting

### Common Issues

1. **"Insufficient data" warning**
   - Solution: Ensure staff has verified claims with `final_claim_type`
   - Check: `Claim.objects.exclude(final_claim_type__isnull=True).count()`

2. **Model loading failed**
   - Solution: Check model file paths and permissions
   - Check: `ls ai_features/models/`

3. **Training script import errors**
   - Solution: Ensure Django environment is properly set up
   - Check: `python manage.py shell` works

4. **Management command not found**
   - Solution: Ensure `ai_features` app is in `INSTALLED_APPS`
   - Check: `python manage.py help` shows the command

### Debug Commands

```bash
# Check Django apps
python manage.py shell -c "from django.apps import apps; print(apps.get_app_config('ai_features'))"

# Check model files
ls -la ai_features/models/

# Test Django setup
python manage.py shell -c "from claims.models import Claim; print(Claim.objects.count())"

# Check training script
python insurance_claim_system/train_claim_type_db.py
```

## 🎯 Future Enhancements

1. **Multi-model training** (fraud detection, amount prediction)
2. **A/B testing** between old and new models
3. **Model versioning** and rollback capability
4. **Performance monitoring** and alerting
5. **Automated data quality checks**
6. **Integration with monitoring tools** (Prometheus, Grafana)

## 📞 Support

For issues with the AI learning pipeline:
1. Check training logs: `training.log`
2. Verify database data quality
3. Test individual components
4. Check Django environment setup
5. Review error messages and stack traces