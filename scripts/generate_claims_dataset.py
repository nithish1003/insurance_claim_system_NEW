import pandas as pd
import numpy as np
import random
import os

def generate_synthetic_claims(n_records=2500):
    """
    Generates a realistic synthetic medical claim dataset for XGBoost risk scoring.
    """
    print(f"🚀 Generating {n_records} synthetic medical claim records...")
    
    hospitals = ['Apollo Hospitals', 'MIOT International', 'Fortis Healthcare', 'Max Super Speciality', 'Narayana Health', 'Lilavati Hospital']
    diseases = ['Viral Fever', 'General Surgery', 'Accident/Trauma', 'Cardiac Arrest', 'Kidney Stone', 'Maternity', 'Appendicitis']
    
    data = []
    
    for _ in range(n_records):
        # 🏥 Core Stay Details
        stay_days = random.randint(1, 12)
        room_rent_per_day = random.randint(2000, 11000)
        room_rent = room_rent_per_day * stay_days
        allowed_room_rent_per_day = random.randint(3000, 7500)
        allowed_room_rent = allowed_room_rent_per_day * stay_days
        
        # 💊 Medical Components
        surgery_cost = random.choice([0, random.randint(15000, 85000)])
        diagnostics = random.randint(1000, 18000)
        allowed_diagnostics = random.randint(1500, 12000)
        medicines = random.randint(1200, 12000)
        
        # 💰 Financials
        # Claim amount is roughly sum of components + some variability
        base_amount = room_rent + surgery_cost + diagnostics + medicines
        claim_amount = random.randint(int(base_amount * 0.95), int(base_amount * 1.15))
        
        non_medical = random.uniform(0, 0.12) * claim_amount
        deductible = random.randint(1000, 10000)
        
        # 🛡️ Governance & Risk Factors
        hospital_risk = random.uniform(0, 0.55)
        claim_frequency = random.randint(1, 5)
        user_risk = 0.05 * claim_frequency + random.uniform(0, 0.1)
        
        # 🧠 RISK SCORE CALCULATION (Deterministic Ground Truth for Training)
        # 1. Non-medical ratio (Penalty for high incidental billing)
        nm_ratio = non_medical / claim_amount if claim_amount > 0 else 0
        
        # 2. Room Excess Ratio (Penalty for luxury ward billing)
        re_ratio = max(0, (room_rent - allowed_room_rent) / allowed_room_rent) if allowed_room_rent > 0 else 0
        
        # 3. Diagnostic Over-billing Ratio
        dg_ratio = max(0, (diagnostics - allowed_diagnostics) / allowed_diagnostics) if allowed_diagnostics > 0 else 0
        
        # Weighted AI Formula
        risk_score = (
            (0.32 * nm_ratio) + 
            (0.24 * re_ratio) + 
            (0.22 * dg_ratio) + 
            (0.14 * hospital_risk) + 
            (0.08 * user_risk)
        )
        
        # Ensure range [0, 1]
        risk_score = min(max(risk_score, 0.0), 1.0)
        
        # 🚩 Bonus: Fraud Flag
        fraud_flag = 1 if risk_score > 0.45 else 0
        
        data.append({
            'hospital_name': random.choice(hospitals),
            'disease_type': random.choice(diseases),
            'stay_days': stay_days,
            'claim_amount': round(claim_amount, 2),
            'deductible': round(deductible, 2),
            'room_rent': round(room_rent, 2),
            'allowed_room_rent': round(allowed_room_rent, 2),
            'surgery_cost': round(surgery_cost, 2),
            'diagnostics': round(diagnostics, 2),
            'allowed_diagnostics': round(allowed_diagnostics, 2),
            'medicines': round(medicines, 2),
            'non_medical': round(non_medical, 2),
            'hospital_risk': round(hospital_risk, 3),
            'user_risk': round(user_risk, 3),
            'claim_frequency': claim_frequency,
            'risk_score': round(risk_score, 4),
            'fraud_flag': fraud_flag
        })
        
    df = pd.DataFrame(data)
    
    # 💾 Save results
    output_filename = "claims_dataset.csv"
    df.to_csv(output_filename, index=False)
    print(f"✅ Success! Generated {len(df)} records.")
    print(f"📂 Dataset saved to: {os.path.abspath(output_filename)}")
    
    return df

if __name__ == "__main__":
    generate_synthetic_claims(2500)
