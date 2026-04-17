import pdfplumber
path = r"C:\Users\HP\Downloads\problem_explanation_5dyamqdvxee (1).pdf"
with pdfplumber.open(path) as pdf:
    for i, page in enumerate(pdf.pages):
        print(f"\n=== PAGE {i+1} ===")
        text = page.extract_text()
        if text:
            print(text)
