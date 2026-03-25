# AI Features for Insurance Claim System

This module provides Machine Learning-powered features for the Online Insurance Claim Processing System, replacing rule-based logic with real ML models.

## Features

### 1. AI Claim Type Identification
- **Input**: Claim description text
- **Output**: 
  - `ai_claim_type` (Accident / Medical / Theft / Other)
  - `confidence_score` (0.0 to 1.0)
- **Model**: TF-IDF + Logistic Regression
- **Fallback**: Rule-based keyword matching

### 2. AI Fraud Detection
- **Input**: 
  - Claim amount
  - Document verification status
  - User claim history
- **Output**:
  - `risk_score` (0-100)
  - `fraud_flag` (True/False)
- **Model**: RandomForestClassifier
- **Fallback**: Rule-based risk calculation

### 3. Recommended Claim Amount
- **Input**:
  - Claimed amount
  - Policy coverage percentage
  - Claim type
  - Risk score
  - Document verification status
- **Output**:
  - `recommended_amount`
- **Model**: Linear Regression
- **Fallback**: Rule-based calculation

## Architecture

### ML Models
- **Claim Type Model**: `models/claim_type_model.pkl`
- **Fraud Detection Model**: `models/fraud_model.pkl` + `models/fraud_scaler.pkl`
- **Amount Prediction Model**: `models/amount_model.pkl` + `models/amount_scaler.pkl` + `models/amount_label_encoder.pkl`

### Services
- `ai_claim_service.py`: Singleton service for claim type prediction
- `fraud_service.py`: Singleton service for fraud detection
- `amount_service.py`: Singleton service for amount prediction

### Data Flow
```
User Submit Claim
    ↓
AI Processing (Type + Fraud + Amount)
    ↓
Save Results to Database
    ↓
Staff Verification
    ↓
Admin Decision
```

## Installation

1. Install ML dependencies:
```bash
pip install scikit-learn pandas numpy joblib
```

2. Add `ai_features` to `INSTALLED_APPS` in settings.py (already done)

3. Run database migrations:
```bash
python manage.py makemigrations ai_features
python manage.py migrate
```

## Training Models

### Automatic Training
```bash
python manage.py train_ai_models
```

### Manual Training
```bash
# Train claim type model
python ai_features/train_claim_type.py

# Train fraud detection model
python ai_features/train_fraud_model.py

# Train amount prediction model
python ai_features/train_amount_model.py
```

## Usage

### In Views
```python
from ai_features.services.ai_claim_service import predict_claim_type
from ai_features.services.fraud_service import predict_fraud_risk
from ai_features.services.amount_service import predict_recommended_amount

# Predict claim type
claim_type, confidence = predict_claim_type("I was in a car accident")

# Predict fraud risk
risk_score, fraud_flag = predict_fraud_risk(claim_instance)

# Predict recommended amount
recommended_amount = predict_recommended_amount(claim_instance)
```

### Automatic Processing
AI predictions are automatically triggered when claims are created or updated via Django signals.

## Database Fields

### Claim Model Extensions
- `ai_claim_type`: AI-predicted claim type
- `confidence_score`: Confidence score for AI prediction
- `final_claim_type`: Final claim type after staff verification
- `risk_score`: Fraud risk score (0-100)
- `fraud_flag`: Whether claim is flagged as fraudulent
- `recommended_amount`: AI-recommended settlement amount

### Policy Model Extensions
- `coverage_percentage`: Coverage percentage for ML models (default: 80%)

## API Integration

The existing APIs work seamlessly with ML integration:

- `POST /submit-claim/` → Runs ML models internally
- `GET /claim-status/<id>/` → Returns AI predictions
- `POST /staff-verify/` → Allows staff to override AI predictions

## Fallback Mechanism

If ML models fail or are not available, the system automatically falls back to rule-based logic:

1. **Claim Type**: Keyword-based matching
2. **Fraud Detection**: Risk factor calculation
3. **Amount Prediction**: Coverage-based calculation

## Testing

```bash
python ai_features/test_ml_integration.py
```

## Monitoring

AI predictions are logged for monitoring:
```
AI predictions for claim CL-001: type=accident, confidence=0.850, risk=25.5, fraud=False, recommended=42500.00
```

## Performance

- **Models load once** (singleton pattern)
- **Fast inference** (sub-second predictions)
- **Handles missing data** safely
- **Graceful degradation** if models unavailable

## Security

- Models are loaded from trusted paths
- Input validation prevents injection attacks
- Fallback ensures system stability
- Logging for audit trails

## Development

### Adding New Features
1. Create training script in `ai_features/train_*.py`
2. Create service in `ai_features/services/*.py`
3. Update models if needed
4. Add to signals if automatic processing needed

### Model Updates
1. Update training data in `datasets/`
2. Retrain models using management command
3. Models are automatically loaded on next request

## Troubleshooting

### Models Not Loading
- Check `ai_features/models/` directory exists
- Verify model files are present
- Check Django logs for loading errors

### Poor Predictions
- Review training data quality
- Check feature engineering
- Consider model retraining

### Performance Issues
- Models load only once (singleton)
- Use caching for frequent predictions
- Monitor memory usage

## License

This module is part of the Insurance Claim System project.