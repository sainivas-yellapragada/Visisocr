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
from datetime import timedelta
logging.basicConfig(level=logging.DEBUG)


def home(request):
    return render(request, 'ocr_app/index.html')

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

    all_text_list = re.split(r'[\n]', text)
    text_list = list()
    
    pan_pattern = r'[A-Z]{5}[0-9]{4}[A-Z]{1}'
    pan_match = re.search(pan_pattern, text)
    if pan_match:
        pan_number = pan_match.group(0).strip()

    aadhar_pattern = r'\d{4}\s\d{4}\s\d{4}'
    aadhar_match = re.search(aadhar_pattern, text)
    if aadhar_match:
        aadhaar_number = aadhar_match.group(0).strip()

    for i in all_text_list:
        if re.match(r'^(\s)+$', i) or i == '':
            continue
        else:
            text_list.append(i)

    if "MALE" in text or "male" in text or "FEMALE" in text or "female" in text: 
        name, birth_date = extract_aadhar_info(text_list)
    else:
        name, birth_date = extract_pan_info(text)
        # aadhar card has gender ,pan card doesn't based on this we differentiate between pan card or aadhar card

    return name, birth_date, pan_number, aadhaar_number

def extract_aadhar_info(text_list):
    user_dob = str()
    user_name = str()
    aadhar_dob_pat = r'(YoB|YOB:|DOB:|DOB|AOB)'
    date_ele = str()
    index = None
    for idx, i in enumerate(text_list):
        if re.search(aadhar_dob_pat, i):
            index = re.search(aadhar_dob_pat, i).span()[1]
            date_ele = i
            dob_idx = idx
        else:
            continue

    if index is not None:
        date_str = ''
        for i in date_ele[index:]:
            if re.match(r'\d', i):
                date_str = date_str + i
            elif re.match(r'/', i):
                date_str = date_str + i
            else:
                continue

        user_dob = date_str

        user_name = text_list[dob_idx - 1]
        pattern = re.search(r'([A-Z][a-zA-Z\s]+)', user_name)

        if pattern:
            name = pattern.group(0).strip()
        else:
            name = None

        return name, user_dob
    else:
        return None, None

def extract_pan_info(text):
    pancard_name = None
    name_patterns = [
        r'(Name\s*\n[A-Z]+[\s]+[A-Z]+[\s]+[A-Z]+[\s])',
        r'(Name\s*\n[A-Z]+[\s]+[A-Z]+[\s])',
        r'(Name\s*\n[A-Z\s]+)'
    ]
    for pattern in name_patterns:
        name_match_pan = re.search(pattern, text)
        if name_match_pan:
            matched_name = name_match_pan.group(1).strip().replace('\n', ' ')
            pancard_name = re.sub(r'^Name\s+', '', matched_name)
            break
    dob_match_pan = re.search(r'(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
    if dob_match_pan:
        birth_date = dob_match_pan.group(0).strip()
    else:
        birth_date = None

    return pancard_name, birth_date

def create_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='visiocr',
            user='root',
            password='root'
        )
        return connection
    except Error as e:
        logging.error("Error while connecting to MySQL: %s", e)
        return None

'''def create_table(connection):
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS extracted_data (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), birth_date DATE, pan_number VARCHAR(10), aadhaar_number VARCHAR(12), age INT, qr_code_image BLOB)")
            connection.commit()
            logging.debug("Table 'extracted_data' created successfully")
            cursor.close()
    except Error as e:
        logging.error("Error while creating table: %s", e)'''
def create_table(connection):
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extracted_data (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255),
                    birth_date DATE,
                    pan_number VARCHAR(10),
                    aadhaar_number VARCHAR(20),
                    age INT,
                    qr_code_image BLOB,
                    email VARCHAR(255),
                    phone_number VARCHAR(15)
                )
            """)
            connection.commit()
            logging.debug("Table 'extracted_data' created successfully")
            cursor.close()
    except Error as e:
        logging.error("Error while creating table: %s", e)


'''def insert_data(connection, name, birth_date, pan_number, aadhaar_number, qr_code_image_data, age):
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
'''
def insert_data(connection, name, birth_date, pan_number, aadhaar_number, qr_code_image_data, age, phone_number, email):
    try:
        if connection.is_connected():
            cursor = connection.cursor()
            sanitized_name = name.replace("'", "''")
            birth_date = datetime.strptime(birth_date, "%d/%m/%Y").strftime("%Y-%m-%d")
            
            logging.debug("Inserting data: Name=%s, Birth Date=%s, PAN Number=%s, Aadhaar Number=%s, Age=%s, Phone Number=%s, Email=%s", sanitized_name, birth_date, pan_number, aadhaar_number, age, phone_number, email)

            cursor.execute("""
                INSERT INTO extracted_data 
                (name, birth_date, pan_number, aadhaar_number, qr_code_image, age, phone_number, email) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (sanitized_name, birth_date, pan_number, aadhaar_number, qr_code_image_data, age, phone_number, email))
            connection.commit()
            logging.debug("Record inserted successfully")
            cursor.close()

    except Error as e:
        logging.error("Error while inserting data into table: %s", e)


'''def process_image(image):
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
        qr_code_image_data = create_qr_code(name, birth_date, pan_number, aadhaar_number)
        birth_date_obj = datetime.strptime(birth_date, "%d/%m/%Y")
        age = (datetime.now() - birth_date_obj).days // 365
        insert_data(connection, name, birth_date, pan_number, aadhaar_number, qr_code_image_data, age)
    except Exception as e:
        logging.error("Error processing image: %s", e)
    finally:
        if connection and connection.is_connected():
            connection.close()
            logging.debug("MySQL connection is closed")

    return name, birth_date, age, pan_number, aadhaar_number'''
def process_image(image, phone_number, email):
    try:
        name, birth_date, pan_number, aadhaar_number = extract_info(image)
        logging.debug("Extracted Info: Name=%s, Birth Date=%s, PAN Number=%s, Aadhaar Number=%s", name, birth_date, pan_number, aadhaar_number)

        if not name or not birth_date:
            logging.error("Name or Birth Date is missing")
            return None, None, None, None, None, None, None

        connection = create_connection()
        if not connection:
            logging.error("Failed to establish a database connection.")
            return None, None, None, None, None, None, None

        qr_code_image_data = create_qr_code(name, birth_date, pan_number, aadhaar_number, phone_number, email)
        birth_date_obj = datetime.strptime(birth_date, "%d/%m/%Y")
        age = (datetime.now() - birth_date_obj).days // 365

        insert_data(connection, name, birth_date, pan_number, aadhaar_number, qr_code_image_data, age, phone_number, email)

    except Exception as e:
        logging.error("Error processing image: %s", e)
        return None, None, None, None, None, None, None

    finally:
        if connection and connection.is_connected():
            connection.close()
            logging.debug("MySQL connection is closed")

    return name, birth_date, age, pan_number, aadhaar_number, phone_number, email

'''def create_qr_code(name, birth_date, pan_number, aadhaar_number):
    data = {
        "name": name,
        "birth_date": birth_date,
        "pan_number": pan_number,
        "aadhaar_number": aadhaar_number
    }
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
'''
def create_qr_code(name, birth_date, pan_number, aadhaar_number, phone_number, email):
    data = {
        "name": name,
        "birth_date": birth_date,
        "pan_number": pan_number,
        "aadhaar_number": aadhaar_number,
        "phone_number": phone_number,
        "email": email
    }
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
        phone_number = request.POST.get('phone_number', '')
        email = request.POST.get('email', '')

        try:
            image = cv2.imdecode(np.frombuffer(uploaded_file.read(), np.uint8), -1)
            name, birth_date, age, pan_number, aadhaar_number, phone_number, email = process_image(image, phone_number, email)
            
            if not name or not birth_date:
                error_message = "Image quality is too poor. Please take another picture and upload again."
                return render(request, 'ocr_app/index.html', {'error_message': error_message})

            qr_code_image_data = create_qr_code(name, birth_date, pan_number, aadhaar_number, phone_number, email)

            # Calculate the expiry date
            current_date = datetime.now().date()
            expiry_date = current_date + timedelta(days=5)

            context = {
                'name': name,
                'birth_date': birth_date,
                'age': age,
                'pan_number': pan_number,
                'aadhaar_number': aadhaar_number,
                'qr_code_image_data': qr_code_image_data,
                'expiry_date': expiry_date.strftime('%d-%m-%Y'),
                'phone_number': phone_number,
                'email': email,
            }

            return render(request, 'ocr_app/index.html', context)

        except ValueError as ve:
            logging.error("Error during image processing: %s", ve)
            error_message = "Image quality is too poor. Please take another picture and upload again."
            return render(request, 'ocr_app/index.html', {'error_message': error_message})

        except Exception as e:
            logging.error("Unexpected error during image processing: %s", e)
            error_message = "Image quality is too poor. Please take another picture and upload again."
            return render(request, 'ocr_app/index.html', {'error_message': error_message})

    return render(request, 'ocr_app/index.html')


'''@csrf_exempt  
def upload_image(request):
    if request.method == 'POST' and 'image' in request.FILES:
        uploaded_file = request.FILES['image']
        image = cv2.imdecode(np.frombuffer(uploaded_file.read(), np.uint8), -1)
        
        try:
            name, birth_date, age, pan_number, aadhaar_number = process_image(image)
            if birth_date is None and name is None:
                return render(request, 'ocr_app/home.html', {'error_message': "Image quality is too poor. Please take another picture and upload again."})
        except ValueError as ve:
            logging.error("Error during image processing: %s", ve)
            return render(request, 'ocr_app/home.html', {'error_message': "Image quality is too poor. Please take another picture and upload again."})
        
        qr_code_image_data = create_qr_code(name, birth_date, pan_number, aadhaar_number)
        
        # Calculate the expiry date
        current_date = datetime.now().date()
        expiry_date = current_date + timedelta(days=5)
        
        context = {
            'name': name,
            'birth_date': birth_date,
            'age': age,
            'pan_number': pan_number,
            'aadhaar_number': aadhaar_number,
            'qr_code_image_data': qr_code_image_data,
            'expiry_date': expiry_date.strftime('%d-%m-%Y')  # Format the expiry date
        }
        
        return render(request, 'ocr_app/home.html', context)
    
    return render(request, 'ocr_app/home.html')
'''

from django.template.loader import render_to_string

from django.shortcuts import render
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
import qrcode
import base64
from io import BytesIO

def download_pdf(request):
    template_path = 'ocr_app/pdf_template.html'
    
    # Ensure all necessary data is retrieved from the request
    name = request.POST.get('name')
    birth_date = request.POST.get('birth_date')
    age = request.POST.get('age')
    pan_number = request.POST.get('pan_number')
    aadhaar_number = request.POST.get('aadhaar_number')
    email = request.POST.get('email')
    phone_number = request.POST.get('phone_number')
    expiry_date = request.POST.get('expiry_date')
    qr_code_image_data = request.POST.get('qr_code_image_data')  # Retrieve QR code image data
    
    context = {
        'name': name,
        'birth_date': birth_date,
        'age': age,
        'pan_number': pan_number,
        'aadhaar_number': aadhaar_number,
        'email': email,
        'phone_number': phone_number,
        'expiry_date': expiry_date,
        'qr_code_image_data': qr_code_image_data,  # Pass QR code image data to context
    }

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="visiting_pass.pdf"'

    template = get_template(template_path)
    html = template.render(context)
    
    # Generate PDF
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')
    
    return response 