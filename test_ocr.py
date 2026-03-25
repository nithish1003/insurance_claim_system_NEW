from ai_features.services.ocr_service import perform_ocr

file_path = r"D:\insurance_claim_system_NEW\media\claims\documents\download_1.jpg"

text = perform_ocr(file_path)

print("\n--- OCR TEXT ---\n")
print(text)

print("\n--- POSSIBLE NAMES ---\n")

lines = text.split('\n')

for line in lines:
    clean_line = line.strip()

    if not clean_line:
        continue

    if any(word in clean_line.upper() for word in ["HOSPITAL", "RECEIPT", "INFORMATION"]):
        continue

    if any(char.isdigit() for char in clean_line):
        continue

    if 2 <= len(clean_line.split()) <= 3:
        print("Patient Name:", clean_line)