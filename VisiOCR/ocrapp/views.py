import cv2
import numpy as np
import pytesseract
from datetime import datetime
from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import re
from django.template.loader import get_template
from xhtml2pdf import pisa

def home(request):
    return render(request, 'ocr_app/home.html')

def preprocess_image(image):
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Apply thresholding or other techniques to enhance text visibility
    processed_image = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    return processed_image
def extract_info(image):
    processed_image = preprocess_image(image)
    text = pytesseract.image_to_string(processed_image)
    print("Extracted Text:")
    print(text)
    name, birth_date = parse_text(text) 
    return name, birth_date
def parse_text(text):
    name = None
    birth_date = None
    
     # Extract Name from pan card format
    name_match_pan = re.search(r'(Name\s*\n[A-Z]+[\s]+[A-Z]+[\s]+[A-Z]+[\s])' or r'(Name\s*\n[A-Z]+[\s]+[A-Z]+[\s])' , text)  

    # Extract Name from Aadhaar card format
    name_match_aadhaar = re.search(r'([A-Z][a-zA-Z\s]+[A-Z][a-zA-Z\s]+[A-Z][a-zA-Z]+)'or r'([A-Z][a-zA-Z\s]+[A-Z][a-zA-Z]+)', text)
    
    if name_match_pan:
        name = name_match_pan.group(1).strip()
        print("pan name:", name)
    elif name_match_aadhaar:
        name = name_match_aadhaar.group(0).strip()
        print("adhar name:", name)

    #Extract Date of Birth from pan card format
    dob_match_pan = re.search(r'(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
    #dob_match_pan = re.search(r'(\d{2}/\d{2}/\d{4})\s*[a-zA-Z]\s*', text, re.IGNORECASE)
    print("pan dob:",dob_match_pan)
    if dob_match_pan:
        birth_date = dob_match_pan.group(0).strip()

    # Extract Date of Birth from Aadhaar card format
    dob_match_aadhaar = re.search(r'(\d{2}/\d{2}/\d{4})', text)  # Custom logic for Aadhaar card
    print("adhar dob:", dob_match_aadhaar)
    if dob_match_aadhaar:
        birth_date = dob_match_aadhaar.group(1).strip()
    return name, birth_date
    
def process_image(image):
    name, birth_date = extract_info(image)

    if birth_date is None:
        return name, None, None 

    try:
      
        birth_date_formats = ['%d-%m-%Y', '%d/%m/%Y', '%m-%d-%Y', '%m/%d/%Y']
        for fmt in birth_date_formats:
            try:
                birth_date = datetime.strptime(birth_date, "%d/%m/%Y")
                print(birth_date)
                break  
            except ValueError:
                continue 

        age = (datetime.now() - birth_date).days // 365
    except (ValueError, TypeError):
      
        birth_date = None
        age = None

    return name, birth_date.strftime('%d/%m/%Y'), age

@csrf_exempt  
def upload_image(request):
    if request.method == 'POST' and 'image' in request.FILES:
        uploaded_file = request.FILES['image']
        image = cv2.imdecode(np.frombuffer(uploaded_file.read(), np.uint8), -1)
        name, birth_date, age = process_image(image)
        print("final dob:", birth_date)
        if birth_date is None and name is None:
            return render(request, 'ocr_app/home.html', {'error_message': "Image quality is too poor. Please try again."})
        
        return render(request, 'ocr_app/home.html', {'name': name, 'birth_date': birth_date, 'age': age})
    
    return render(request, 'ocr_app/home.html')
def download_pdf(request):
    template_path = 'ocr_app/pdf_template.html'
    context = {
        'name': request.POST.get('name'),
        'birth_date': request.POST.get('birth_date'),
        'age': request.POST.get('age'),
    }
    # Create a Django response object with the appropriate PDF headers
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="visiting_pass.pdf"'

    # Render the HTML template as a PDF
    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response)
    # If error then show some funy view
    if pisa_status.err:
       return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response
