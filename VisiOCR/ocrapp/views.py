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
import qrcode
import base64
from io import BytesIO
import mysql.connector
from mysql.connector import Error
import logging

logging.basicConfig(level=logging.DEBUG)

def home(request):
    return render(request, 'ocr_app/home.html')

def preprocess_image(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    processed_image = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    return processed_image

def extract_info(image):
    processed_image = preprocess_image(image)
    text = pytesseract.image_to_string(processed_image)
    name, birth_date, pan_number, aadhaar_number = parse_text(text) 
    return name, birth_date, pan_number, aadhaar_number

def parse_text(text):
    name = None
    birth_date = None
    pan_number = None
    aadhaar_number = None

    pan_match = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', text)
    name_match_pan = re.search(r'(\s*\n[A-Z]+[\s]+[A-Z]+[\s]+[A-Z]+[\s])' or r'(\s*\n[A-Z]+[\s]+[A-Z]+[\s])', text)  
    if pan_match:
        pan_number = pan_match.group(0).strip()
    if name_match_pan:
        name = name_match_pan.group(1).strip()

    aadhaar_match = re.search(r'\b\d{4}\s\d{4}\s\d{4}\b', text)
    name_match_aadhaar = re.search(r'([A-Z][a-zA-Z\s]+[A-Z][a-zA-Z\s]+[A-Z][a-zA-Z]+)' or r'([A-Z][a-zA-Z\s]+[A-Z][a-zA-Z]+)', text)
    if aadhaar_match:
        aadhaar_number = aadhaar_match.group(0).strip()
    if name_match_aadhaar:
        name = name_match_aadhaar.group(0).strip()

    dob_match_pan = re.search(r'(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
    if dob_match_pan:
        birth_date = dob_match_pan.group(0).strip()

    dob_match_aadhaar = re.search(r'(\d{2}/\d{2}/\d{4})', text)
    if dob_match_aadhaar:
        birth_date = dob_match_aadhaar.group(1).strip()

    return name, birth_date, pan_number, aadhaar_number

def create_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='OCR',
            user='root',
            password='root'
        )
        return connection
    except Error as e:
        logging.error("Error while connecting to MySQL: %s", e)
        return None

def create_table(connection):
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS extracted_data (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), birth_date DATE, pan_number VARCHAR(10), aadhaar_number VARCHAR(12), age INT, qr_code_image BLOB)")
            connection.commit()
            logging.debug("Table 'extracted_data' created successfully")
            cursor.close()
    except Error as e:
        logging.error("Error while creating table: %s", e)

def insert_data(connection, name, birth_date, pan_number, aadhaar_number, qr_code_image_data, age):
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            sanitized_name = name.replace("'", "''")
            birth_date = datetime.strptime(birth_date, "%d/%m/%Y").strftime("%Y-%m-%d")
            cursor.execute("INSERT INTO extracted_data (name, birth_date, pan_number, aadhaar_number, qr_code_image, age) VALUES (%s, %s, %s, %s, %s, %s)", (sanitized_name, birth_date, pan_number, aadhaar_number, qr_code_image_data, age))
            connection.commit()
            logging.debug("Record inserted successfully")
            logging.debug("Name: %s, Birth Date: %s, PAN Number: %s, Aadhaar Number: %s", sanitized_name, birth_date, pan_number, aadhaar_number)
            cursor.close()
    except Error as e:
        logging.error("Error while inserting data into table: %s", e)
        logging.error("Failed to insert data: Name: %s, Birth Date: %s, PAN Number: %s, Aadhaar Number: %s", sanitized_name, birth_date, pan_number, aadhaar_number)

def process_image(image):
    name, birth_date, pan_number, aadhaar_number = extract_info(image)
    logging.debug("Extracted Info: Name=%s, Birth Date=%s, PAN Number=%s, Aadhaar Number=%s", name, birth_date, pan_number, aadhaar_number)
    if birth_date is None or name is None:
        logging.error("Failed to extract valid name or birth date from the image.")
        return name, None, None, None 

    connection = create_connection()
    if not connection:
        logging.error("Failed to establish a database connection.")
        return name, None, None, None

    try:
        create_table(connection)
        qr_code_image_data = create_qr_code(name)
        birth_date_obj = datetime.strptime(birth_date, "%d/%m/%Y")
        age = (datetime.now() - birth_date_obj).days // 365
        insert_data(connection, name, birth_date, pan_number, aadhaar_number, qr_code_image_data, age)
    except Exception as e:
        logging.error("Error processing image: %s", e)
    finally:
        if connection and connection.is_connected():
            connection.close()
            logging.debug("MySQL connection is closed")

    return name, birth_date, age, pan_number, aadhaar_number


def create_qr_code(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white")

    qr_img_bytes = BytesIO()
    qr_img.save(qr_img_bytes, format='PNG')
    qr_img_bytes.seek(0)

    qr_code_image_data = base64.b64encode(qr_img_bytes.getvalue()).decode()
    
    return qr_code_image_data

@csrf_exempt  
def upload_image(request):
    if request.method == 'POST' and 'image' in request.FILES:
        uploaded_file = request.FILES['image']
        image = cv2.imdecode(np.frombuffer(uploaded_file.read(), np.uint8), -1)
        name, birth_date, age, pan_number, aadhaar_number = process_image(image)
        qr_code_image_data = create_qr_code(name)
        if birth_date is None and name is None:
            return render(request, 'ocr_app/home.html', {'error_message': "Image quality is too poor. Please try again."})
        
        return render(request, 'ocr_app/home.html', {'name': name, 'birth_date': birth_date, 'age': age, 'pan_number': pan_number, 'aadhaar_number': aadhaar_number, 'qr_code_image_data': qr_code_image_data})
    
    return render(request, 'ocr_app/home.html')

def download_pdf(request):
    template_path = 'ocr_app/pdf_template.html'
    context = {
        'name': request.POST.get('name'),
        'birth_date': request.POST.get('birth_date'),
        'age': request.POST.get('age'),
        'pan_number': request.POST.get('pan_number'),
        'aadhaar_number': request.POST.get('aadhaar_number'),
    }
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="visiting_pass.pdf"'

    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response
