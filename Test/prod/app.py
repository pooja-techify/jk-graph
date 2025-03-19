from flask import Flask, request, jsonify, send_file
import json
import random
import os
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from flask_cors import CORS
from datetime import datetime, timezone
import boto3
import psycopg2
import pandas as pd
import base64
import logging
from pypdf import PdfWriter
import fitz  # PyMuPDF
from PIL import Image
from io import BytesIO
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from reportlab.lib.utils import ImageReader

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
    "supports_credentials": True
}})

EMAIL_SENDER = 'hr@techifysolutions.com'

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

# Create a session for the default profile (for S3)
default_session = boto3.Session()

# Create the S3 client using the default profile
s3_client = default_session.client('s3')

# Create a session for the SES profile
ses_session = boto3.Session(profile_name='ses-profile')

# Create the SES client using the ses-profile
ses_client = ses_session.client('ses', region_name='us-east-1')

def get_address_from_coordinates_nominatim(latitude, longitude):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={latitude}&lon={longitude}&format=json"
        headers = {
            'User-Agent': 'YourAppName/1.0'
        }
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if 'address' in data:
                state_district = data['address'].get('state_district') or data['address'].get('state')
                if state_district:
                    return state_district
                return 'State/District not found'
            return 'Address not found'
        else:
            print(f"Error receiving response while getting address from coordinates with status code {response.status_code}")
            logger.error(f"Error receiving response while getting address from coordinates with status code {response.status_code}")
            return None
    except requests.RequestException as e:
        print(f"Request error while getting address from coordinates: {e}")
        logger.error(f"Request error while getting address from coordinates: {e}")
        return jsonify({"error": f"Request error: {str(e)}"}), 500
    except Exception as e:
        print(f"Error getting address from coordinates: {e}")
        logger.error(f"Error getting address from coordinates: {e}")
        return jsonify({"error": f"General error: {str(e)}"}), 500

def select_questions(input_file, level, num_questions, output_file, append=False):
    try:
        if not os.path.exists(input_file):
            print(f"File not found: {input_file}")
            raise FileNotFoundError(f"Input file does not exist: {input_file}")

        json_output = os.path.join(output_file)

        with open(input_file, 'r') as f:
            questions = json.load(f)

        level_questions = [q for q in questions if q['Level'] == level]
        
        if not level_questions:
            print(f"Warning: No questions found for level: {level}")
            raise ValueError(f"No questions found for level: {level}")
        
        existing_questions = []
        if append and os.path.exists(json_output):
            with open(json_output, 'r') as f:
                try:
                    existing_questions = json.load(f)
                except json.JSONDecodeError:
                    existing_questions = []

        available_questions = [q for q in level_questions if q not in existing_questions]
        
        if not available_questions:
            print(f"Warning: All questions for level {level} have already been selected")
            logger.error(f"Warning: All questions for level {level} have already been selected")
            return
            
        if num_questions > len(available_questions):
            print(f"Warning: Only {len(available_questions)} new questions available for level {level}")
            logger.error(f"Warning: Only {len(available_questions)} new questions available for level {level}")
            selected = available_questions
        else:
            selected = random.sample(available_questions, num_questions)
        
        final_questions = existing_questions + selected
        
        with open(json_output, 'w') as f:
            json.dump(final_questions, f, indent=2)
        
        # print(f"Successfully {'appended' if append else 'saved'} {len(selected)} questions of level {level}")
        # print(f"Total questions in output files: {len(final_questions)}")
        
    except FileNotFoundError as e:
        print(f"File not found: {e}")
        logger.error(f"File not found: {e}")
        return jsonify({"error while selecting questions": str(e)}), 400
    
    except json.JSONDecodeError:
        print("Invalid JSON format in input file")
        logger.error("Invalid JSON format in input file")
        return jsonify({"error while selecting questions": "Invalid JSON format in input file"}), 400
    
    except Exception as e:
        print(f"Error while selecting questions: {e}")
        logger.error(f"Error while selecting questions: {e}")
        return jsonify({"error while selecting questions": str(e)}), 500
    
@app.route('/generate_questions', methods=['GET'])
def generate_questions():
    try:
        select_questions(input_file="aptitude.txt", level="Basic", num_questions=2, output_file="aptitude_questions.json", append=False)
        select_questions(input_file="aptitude.txt", level="Intermediate", num_questions=6, output_file="aptitude_questions.json", append=True)
        select_questions(input_file="aptitude.txt", level="Advanced", num_questions=7, output_file="aptitude_questions.json", append=True)
        select_questions(input_file="verbal.txt", level="Basic", num_questions=6, output_file="verbal_questions.json", append=False)
        select_questions(input_file="verbal.txt", level="Intermediate", num_questions=4, output_file="verbal_questions.json", append=True)
        select_questions(input_file="programming.txt", level="Basic", num_questions=5, output_file="programming_questions.json", append=False)
        select_questions(input_file="programming.txt", level="Intermediate", num_questions=2, output_file="programming_questions.json", append=True)
        select_questions(input_file="programming.txt", level="Advanced", num_questions=1, output_file="programming_questions.json", append=True)
        select_questions(input_file="programming.txt", level="Coding", num_questions=2, output_file="programming_questions.json", append=True)
        select_questions(input_file="reasoning.txt", level="Basic", num_questions=2, output_file="reasoning_questions.json", append=False)
        select_questions(input_file="reasoning.txt", level="Intermediate", num_questions=11, output_file="reasoning_questions.json", append=True)
        select_questions(input_file="reasoning.txt", level="Advanced", num_questions=2, output_file="reasoning_questions.json", append=True)
        print("Questions generated successfully")
        return jsonify({"message": "Questions generated successfully"}), 200
    
    except Exception as e:
        print(f"Error while generating questions: {e}")
        logger.error(f"Error while generating questions: {e}")
        return jsonify({"error while generating questions": str(e)}), 500

@app.route('/get_aptitude_questions', methods=['GET'])
def get_aptitude_questions():
    try:
        with open('aptitude_questions.json', 'r') as f:
            data = json.load(f)

        json_data = json.dumps(data)

        encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
        
        return jsonify({"encoded": encoded_data})
    
    except Exception as e:
        print(f"Error while getting aptitude questions: {e}")
        logger.error(f"Error while getting aptitude questions: {e}")
        return jsonify({"error while getting aptitude questions": str(e)}), 500

@app.route('/get_verbal_questions', methods=['GET'])
def get_verbal_questions():
    try:
        with open('verbal_questions.json', 'r') as f:
            data = json.load(f)

        json_data = json.dumps(data)

        encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
        
        return jsonify({"encoded": encoded_data})
    
    except Exception as e:
        print(f"Error while getting verbal questions: {e}")
        logger.error(f"Error while getting verbal questions: {e}")
        return jsonify({"error while getting verbal questions": str(e)}), 500
    
@app.route('/get_programming_questions', methods=['GET'])
def get_programming_questions():
    try:
        with open('programming_questions.json', 'r') as f:
            data = json.load(f)

        json_data = json.dumps(data)

        encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
        
        return jsonify({"encoded": encoded_data})
    
    except Exception as e:
        print(f"Error while getting programming questions: {e}")
        logger.error(f"Error while getting programming questions: {e}")
        return jsonify({"error while getting programming questions": str(e)}), 500
    
@app.route('/get_reasoning_questions', methods=['GET'])
def get_reasoning_questions():
    try:
        with open('reasoning_questions.json', 'r') as f:
            data = json.load(f)

        json_data = json.dumps(data)

        encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
        
        return jsonify({"encoded": encoded_data})
    
    except Exception as e:
        print(f"Error while getting reasoning questions: {e}")
        logger.error(f"Error while getting reasoning questions: {e}")
        return jsonify({"error while getting reasoning questions": str(e)}), 500
    
@app.route('/get_sjt_questions', methods=['GET'])
def get_sjt_questions():
    try:
        with open('sjt_questions.json', 'r') as f:
            data = json.load(f)

        questions_and_options = [{"question": item["question"], "options": item["options"]} for item in data]

        json_data = json.dumps(questions_and_options)

        encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
        
        return jsonify({"encoded": encoded_data})
    
    except Exception as e:
        print(f"Error while getting SJT questions: {e}")
        logger.error(f"Error while getting SJT questions: {e}")
        return jsonify({"error while getting SJT questions": str(e)}), 500          
            
def send_email(subject, body, to_recipients, cc_recipients, attachment_path=None):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = ', '.join(to_recipients)
        msg['Cc'] = ', '.join(cc_recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        if attachment_path:
            with open(attachment_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {os.path.basename(attachment_path)}',
                )
                msg.attach(part)

        all_recipients = to_recipients + cc_recipients

        ses_client.send_raw_email(
            Source=EMAIL_SENDER,
            Destinations=all_recipients,
            RawMessage={'Data': msg.as_string()}
        )
        print("Email sent successfully")
    except NoCredentialsError:
        print("SES: Credentials not available.")
    except PartialCredentialsError:
        print("SES: Incomplete credentials provided.")
    except Exception as e:
        print(f"SES: An error occurred: {e}")
    
    
@app.route('/send_verification', methods=['POST'])
def send_verification():
    try:
        data = request.json
        if data is None:
            return jsonify({"error": "No JSON data provided"}), 400
        
        emails = data.get("emails")
        names = data.get("names")
        phone_numbers = data.get("phone_numbers")
        
        for email, name, phone_number in zip(emails, names, phone_numbers):
            send_test(name, email, phone_number)

        print("Verification email/s sent successfully")

        return jsonify({"message": "Verification email/s sent successfully"}), 200
        
    except Exception as e:
        print(f"Failed to send verification: {str(e)}")
        logger.error(f"Failed to send verification: {str(e)}")
        return jsonify({"error": f"Failed to send verification: {str(e)}"}), 500

def send_test(name, email, phone_number):
    candidate_id = f"{random.randint(0, 999)}{int(datetime.now().timestamp() * 1000)}"
    candidate_url = f"https://onlinetest.techifysolutions.com/#/?candidate_id={candidate_id}"
    passcode = str(random.randint(100000, 999999))
    
    cursor = None
    conn = None
    
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prod.registration (
                candidate_id VARCHAR(50) PRIMARY KEY,
                email VARCHAR(50),
                name VARCHAR(50),
                phone_number VARCHAR(15),
                passcode VARCHAR(10),
                test_attempted BOOLEAN DEFAULT FALSE,
                entry_date TIMESTAMP,
                test_attempted_date TIMESTAMP
            )
        ''')

        entry_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        cursor.execute('''
            INSERT INTO prod.registration (candidate_id, email, name, phone_number, passcode, entry_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (candidate_id) DO UPDATE SET email = EXCLUDED.email, passcode = EXCLUDED.passcode;
        ''', (candidate_id, email, name, phone_number, passcode, entry_date))

        conn.commit()

        body = f"""
            Dear {name},
            <br>Thank you for your interest in joining the Techify team. As part of our selection process, we invite you to complete a technical assessment designed to showcase your problem-solving abilities.
            <br><br>Assessment Details:
            <br>This assessment link is valid for one attempt only.
            <br>Please ensure you have a stable internet connection before beginning.
            <br>We recommend <b>carefully reviewing all instructions</b> prior to starting the test.
            <br><br>Access Information:
            <br><b>Assessment Link: <a href="{candidate_url}">Test Link</a></b>
            <br><b>Unique Access Code: {passcode}</b>
            <br><br>The assessment has been designed to evaluate key skills relevant to the position you've applied for. We encourage you to approach it methodically and demonstrate your technical capabilities.
            <br>Should you encounter any technical difficulties during the assessment, please contact our talent acquisition team at +91 7862063131.
            <br>We wish you success and look forward to reviewing your completed assessment.
            <br><br>Regards,
            <br>Talent Acquisition Team
            <br>Techify Solutions
            <br>hr@techifysolutions.com 
            <br>+91 7862063131
            """

        subject = "Invite to test from Techify Solutions Pvt Ltd"
        send_email(subject, body, [email], [])
        print("Verification email sent successfully")
    
    except Exception as e:
        print(f"Error in send_test: {str(e)}")
        logger.error(f"Error in send_test: {str(e)}")
        return jsonify({"error": f"Error in send_test: {str(e)}"}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/verify_passcode', methods=['POST'])
def verify_passcode():
    data = request.json
    candidate_id = data.get("candidate_id")
    passcode = data.get("passcode")

    if not candidate_id or not passcode:
        return jsonify({"error": "Candidate ID and passcode are required"}), 400
    cursor = None
    conn = None

    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            SELECT passcode, test_attempted FROM prod.registration WHERE candidate_id = %s;
        ''', (candidate_id,))
        result = cursor.fetchone()

        if result:
            stored_passcode, test_attempted = result
            if stored_passcode == passcode and not test_attempted:
                print("Verification successful")
                return jsonify({"message": "Verification successful, you can proceed with the test"}), 200
            else:
                return jsonify({"error": "Invalid passcode or test already attempted"}), 400
        else:
            return jsonify({"error": "Candidate ID not found"}), 404

    except Exception as e:
        print(f"Error verifying passcode: {str(e)}")
        logger.error(f"Error verifying passcode: {str(e)}")
        return jsonify({"error": f"Error verifying passcode: {str(e)}"}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/get_mail', methods=['POST'])
def get_mail():
    data = request.json
    candidate_id = data.get("candidate_id")
    is_sjt = data.get("is_sjt") #Boolean true or false

    if not candidate_id:
        return jsonify({"error": "Candidate ID is required"}), 400

    cursor = None
    conn = None
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        if is_sjt:
            cursor.execute('''
                SELECT email FROM prod.sjt_registration WHERE candidate_id = %s;
            ''', (candidate_id,))
            result = cursor.fetchone()

            if result:
                email = result[0]
                return jsonify({"email": email}), 200
            else:
                return jsonify({"error": "Candidate ID not found"}), 404

        else:
            cursor.execute('''
                SELECT email FROM prod.registration WHERE candidate_id = %s;
            ''', (candidate_id,))
            result = cursor.fetchone()

            if result:
                email = result[0]
                return jsonify({"email": email}), 200
            else:
                return jsonify({"error": "Candidate ID not found"}), 404

    except Exception as e:
        print(f"Error fetching email: {str(e)}")
        logger.error(f"Error fetching email: {str(e)}")
        return jsonify({"error": f"Error fetching email: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/start_test', methods=['POST'])
def start_test():
    data = request.json
    candidate_id = data.get("candidate_id")

    if not candidate_id:
        return jsonify({"error": "Candidate ID is required"}), 400
    cursor = None
    conn = None
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )
        
        cursor = conn.cursor()

        test_attempted_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        cursor.execute('''
            UPDATE prod.registration SET test_attempted = TRUE, test_attempted_date = %s WHERE candidate_id = %s;
        ''', (test_attempted_date, candidate_id,))
        conn.commit()

        print("Test started successfully")

        return jsonify({"message": "Test started successfully"}), 200

    except Exception as e:
        print(f"Error starting test: {str(e)}")
        logger.error(f"Error starting test: {str(e)}")
        return jsonify({"error": f"Error starting test: {str(e)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/submit_test', methods=['POST'])
def submit_test():
    try:
        if 'report' not in request.files:
            return jsonify({'error': 'No report file part'}), 400

        file = request.files['report']
        candidate_id = request.form.get('candidate_id')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        location = request.form.get('location')
        score = request.form.get('score')
        aptitude_score = request.form.get('aptitude_score')
        verbal_score = request.form.get('verbal_score')
        programming_score = request.form.get('programming_score')
        logical_score = request.form.get('logical_score')
        submit_reason = request.form.get('submit_reason')
        time_taken = request.form.get('time_taken')

        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        if file:
            # Save the uploaded file to a temporary path
            report_path = os.path.join('/tmp', file.filename)
            file.save(report_path)

            # Compress the PDF
            compressed_report_path = os.path.join('/tmp', f"{file.filename}")
            compress_pdf(report_path, compressed_report_path)

            # Upload the compressed PDF to S3
            s3_key = f'prod/reports/{candidate_id}'
            try:
                s3_client.upload_file(
                    compressed_report_path, 'onlinetest-stag-documents', s3_key,
                    ExtraArgs={
                        "ContentDisposition": "inline",
                        "ContentType": "application/pdf",
                        "ACL": "public-read"
                    }
                )
                print(f"File uploaded to S3: s3://onlinetest-stag-documents/{s3_key}")

            except NoCredentialsError:
                print("S3: Credentials not available.")
            except PartialCredentialsError:
                print("S3: Incomplete credentials provided.")
            except Exception as e:
                print(f"S3: An error occurred: {e}")
            
            
            try:
                latitude, longitude = location.split(",")
                location = get_address_from_coordinates_nominatim(latitude, longitude)
                print("Address fetched successfully")

            except Exception as e:
                print(f"Error getting address from coordinates: {e}")
                logger.error(f"Error getting address from coordinates: {e}")
                return jsonify({"error": "Failed to get address from coordinates"}), 500
            

            try:
                store_user_data(candidate_id, first_name, last_name, email, phone_number, location, score, aptitude_score, verbal_score, programming_score, logical_score, time_taken, f'https://onlinetest-stag-documents.s3.us-east-1.amazonaws.com/{s3_key}', submit_reason)
                print("User data stored successfully")
                
            except Exception as e:
                print(f"Error storing user data: {e}")
                logger.error(f"Error storing user data: {e}")
                return jsonify({"error": "Failed to store user data"}), 500
           

            try:
                to_emails = ['hr@techifysolutions.com']
                cc_emails = ['jobs@techifysolutions.com', 'zankhan.kukadiya@techifysolutions.com']
                subject = f'Test Report {first_name} {last_name}'
                body = f"""
                Please find the attached test report.<br><br>
                Candidate ID: {candidate_id}<br>
                First Name: {first_name}<br>
                Last Name: {last_name}<br>
                Score: {score}<br><br>
                """
                send_email(subject, body, to_emails, cc_emails, attachment_path=compressed_report_path)
                print("Report sent successfully")
            
            except Exception as e:
                print(f"Error sending report email: {e}")
                logger.error(f"Error sending report email: {e}")
                return jsonify({"error": "Failed to send report email"}), 500
            
        
            try:
                to_email = email
                subject = "Test Submitted Successfully"
                body = f"""
                Dear {first_name},
                <br>Thank you for completing the Techify technical assessment. We are pleased to confirm that your submission has been successfully received.
                <br>Our technical evaluation team will now review your work thoroughly. We appreciate the time and effort you've invested in this process and will be in touch with you regarding next steps.
                <br>If you have any questions in the interim, please don't hesitate to contact our Talent Acquisition Team.
                <br><br>Regards,
                <br>Talent Acquisition Team 
                <br>Techify Solutions
                <br>hr@techifysolutions.com 
                <br>+91 786-206-3131
                """
                send_email(subject, body, [to_email], [])
                print("Submission confirmation mail sent successfully")

            except Exception as e:
                print(f"Error sending submission confirmation mail: {e}")
                logger.error(f"Error sending submission confirmation mail: {e}")
                return jsonify({"error": "Failed to send submission confirmation mail"}), 500
            
            return jsonify({"message": "Test submitted successfully"}), 200

    except Exception as e:
        print(f"Error in submit_test: {e}")
        logger.error(f"Error in submit_test: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Unexpected error occurred"}), 500

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_id = data.get("candidate_id")
        feedback = data.get("feedback")

        if not candidate_id or not feedback:
            return jsonify({"error": "Candidate ID and feedback are required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )
        
        cursor = conn.cursor()

        sql_query = '''
        UPDATE prod.hrtest_reports
        SET feedback = %s
        WHERE candidate_id = %s;
        '''

        cursor.execute(sql_query, (feedback, candidate_id))

        conn.commit()
        print("Feedback updated successfully.")
        
        return jsonify({"message": "Feedback updated successfully"}), 200

    except Exception as e:
        print(f"Error updating feedback: {e}")
        logger.error(f"Error updating feedback: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def store_user_data(candidate_id, first_name, last_name, email, phone_number, location, score, aptitude_score, verbal_score, programming_score, logical_score, time_taken, report_s3_url, submit_reason):
    cursor = None
    conn = None
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prod.hrtest_reports (
                candidate_id VARCHAR(50) PRIMARY KEY,
                first_name VARCHAR(50),
                last_name VARCHAR(50),
                email VARCHAR(50),
                phone_number VARCHAR(15),
                location VARCHAR(50),
                score FLOAT,
                aptitude_score FLOAT,
                verbal_score FLOAT,
                programming_score FLOAT,
                logical_score FLOAT,
                time_taken VARCHAR(50),
                feedback TEXT DEFAULT '',
                report_s3_url TEXT,
                submission_date TIMESTAMP,
                submit_reason VARCHAR(50)
            )
            ''')

        submission_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        cursor.execute('''
            INSERT INTO prod.hrtest_reports (candidate_id, first_name, last_name, email, phone_number, location, score, aptitude_score, verbal_score, programming_score, logical_score, time_taken, report_s3_url, submission_date, submit_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (candidate_id, first_name, last_name, email, phone_number, location, score, aptitude_score, verbal_score, programming_score, logical_score, time_taken, report_s3_url, submission_date, submit_reason))
        
        conn.commit()

        print("User data stored successfully")
        
    except psycopg2.DatabaseError as e:
        print(f"Database error: {e}")
        logger.error(f"Database error: {e}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    except Exception as e:
        print(f"Error storing user data: {e}")
        logger.error(f"Error storing user data: {e}")
        return jsonify({"error": f"Error storing user data: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/fetch_user_data', methods=['GET'])
def fetch_user_data():
    cursor = None
    conn = None
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('SELECT * FROM prod.hrtest_reports ORDER BY submission_date DESC')
        rows = cursor.fetchall()

        user_data = []
        for row in rows:
            user_data.append({
                "candidate_id": row[0],
                "first_name": row[1],
                "last_name": row[2],
                "email": row[3],
                "phone_number": row[4],
                "location": row[5],
                "score": row[6],
                "aptitude_score": row[7],
                "verbal_score": row[8],
                "programming_score": row[9],
                "logical_score": row[10],
                "time_taken": row[11],
                "feedback": row[12],
                "report_s3_url": row[13],
                "submission_date": row[14],
                "submit_reason": row[15]
            })

        print("User data fetched successfully")

        return jsonify(user_data), 200

    except Exception as e:
        print(f"Error fetching user data: {str(e)}")
        logger.error(f"Error fetching user data: {str(e)}")
        return jsonify({"error": f"Error fetching user data: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/delete_user_data', methods=['DELETE'])
def delete_user_data():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_ids = data.get("candidate_ids")

        if not candidate_ids or not isinstance(candidate_ids, list):
            return jsonify({"error": "A list of Candidate IDs is required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        DELETE FROM prod.hrtest_reports
        WHERE candidate_id = ANY(%s);
        '''

        s3_key = f'prod/reports/{candidate_ids[0]}'
        try:
            s3_client.delete_object(Bucket='onlinetest-stag-documents', Key=s3_key)
            print(f"Deleted report for candidate ID: {candidate_ids[0]} from S3.")
        except NoCredentialsError:
            print("S3: Credentials not available.")
        except PartialCredentialsError:
            print("S3: Incomplete credentials provided.")
        except Exception as e:
            print(f"S3: An error occurred: {e}")

        cursor.execute(sql_query, (candidate_ids,))

        conn.commit()
        print(f"User data for {len(candidate_ids)} candidates deleted successfully.")
        
        return jsonify({"message": f"User data for {len(candidate_ids)} candidates deleted successfully"}), 200

    except Exception as e:
        print(f"Error deleting user data: {e}")
        logger.error(f"Error deleting user data: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/export_candidate_data', methods=['POST'])
def export_candidate_data():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_ids = data.get("candidate_ids")

        if not candidate_ids or not isinstance(candidate_ids, list):
            return jsonify({"error": "A list of Candidate IDs is required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        SELECT * FROM prod.hrtest_reports
        WHERE candidate_id = ANY(%s);
        '''

        cursor.execute(sql_query, (candidate_ids,))
        rows = cursor.fetchall()

        columns = [
            "candidate_id", "first_name", "last_name", "email", "phone_number",
            "location", "score", "aptitude_score", "verbal_score",
            "programming_score", "logical_score", "time_taken", "feedback", 
            "report_s3_url", "submission_date", "submit_reason"
        ]
        data_to_export = [dict(zip(columns, row)) for row in rows]

        for entry in data_to_export:
            if isinstance(entry['submission_date'], datetime):
                entry['submission_date'] = entry['submission_date'].replace(tzinfo=None)

        df = pd.DataFrame(data_to_export)
        excel_file_path = '/tmp/candidate_data.xlsx'
        df.to_excel(excel_file_path, index=False)

        print("Candidate data exported successfully")

        return send_file(excel_file_path, as_attachment=True)

    except Exception as e:
        print(f"Error exporting candidate data: {e}")
        logger.error(f"Error exporting candidate data: {str(e)}")
        return jsonify({"error": f"Error exporting candidate data: {str(e)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/fetch_registration', methods=['GET'])
def fetch_registration():
    cursor = None
    conn = None
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('SELECT * FROM prod.registration ORDER BY entry_date DESC')
        rows = cursor.fetchall()

        registration_data = []
        for row in rows:
            registration_data.append({
                "candidate_id": row[0],
                "email": row[1],
                "name": row[2],
                "phone_number": row[3],
                "passcode": row[4],
                "test_attempted": row[5],
                "entry_date": row[6],
                "test_attempted_date": row[7]
            })

        print("Registration data fetched successfully")

        return jsonify(registration_data), 200

    except Exception as e:
        print(f"Error fetching registration data: {str(e)}")
        logger.error(f"Error fetching registration data: {str(e)}")
        return jsonify({"error": f"Error fetching registration data: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/delete_registration_data', methods=['DELETE'])
def delete_registration_data():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_ids = data.get("candidate_ids")

        if not candidate_ids or not isinstance(candidate_ids, list):
            return jsonify({"error": "A list of Candidate IDs is required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        DELETE FROM prod.registration
        WHERE candidate_id = ANY(%s);
        '''

        s3_key = f'prod/reports/{candidate_ids[0]}'
        try:
            s3_client.delete_object(Bucket='onlinetest-stag-documents', Key=s3_key)
            print(f"Deleted report for candidate ID: {candidate_ids[0]} from S3.")
        except NoCredentialsError:
            print("S3: Credentials not available.")
        except PartialCredentialsError:
            print("S3: Incomplete credentials provided.")
        except Exception as e:
            print(f"S3: An error occurred: {e}")

        cursor.execute(sql_query, (candidate_ids,))

        conn.commit()
        print(f"Registration data for {len(candidate_ids)} candidates deleted successfully.")
        
        return jsonify({"message": f"Registration data for {len(candidate_ids)} candidates deleted successfully"}), 200

    except Exception as e:
        print(f"Error deleting registration data: {e}")
        logger.error(f"Error deleting registration data: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/export_registration_data', methods=['POST'])
def export_registration_data():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_ids = data.get("candidate_ids")

        if not candidate_ids or not isinstance(candidate_ids, list):
            return jsonify({"error": "A list of Candidate IDs is required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        SELECT candidate_id, email, name, phone_number, test_attempted, entry_date
        FROM prod.registration
        WHERE candidate_id = ANY(%s);
        '''

        cursor.execute(sql_query, (candidate_ids,))
        rows = cursor.fetchall()

        columns = [
            "candidate_id", "email", "name", "phone_number",
            "test_attempted", "entry_date"
        ]
        data_to_export = [dict(zip(columns, row)) for row in rows]

        for entry in data_to_export:
            if isinstance(entry['entry_date'], datetime):
                entry['entry_date'] = entry['entry_date'].replace(tzinfo=None)

        df = pd.DataFrame(data_to_export)
        excel_file_path = '/tmp/registration_data.xlsx'
        df.to_excel(excel_file_path, index=False)

        print("Registration data exported successfully")

        return send_file(excel_file_path, as_attachment=True)

    except Exception as e:
        print(f"Error exporting registration data: {e}")
        logger.error(f"Error exporting registration data: {str(e)}")
        return jsonify({"error": f"Error exporting registration data: {str(e)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/upload_excel', methods=['POST'])
def upload_excel():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join('/tmp', filename)
            file.save(file_path)

            # Read the Excel file
            df = pd.read_excel(file_path)

            # Check if required columns are present
            if not {'Name', 'Email', 'Phone_Number'}.issubset(df.columns):
                return jsonify({"error": "Excel file must contain 'Name', 'Email', and 'Phone_Number' columns"}), 400

            # Iterate over each row and call send_test
            for _, row in df.iterrows():
                name = row['Name']
                email = row['Email']
                phone_number = row['Phone_Number']
                send_test(name, email, phone_number)

            print("Verification emails sent successfully from Excel upload")

            return jsonify({"message": "Verification emails sent successfully"}), 200

    except Exception as e:
        print(f"Error processing Excel file: {str(e)}")
        logger.error(f"Error processing Excel file: {str(e)}")
        return jsonify({"error": f"Error processing Excel file: {str(e)}"}), 500

@app.route('/send_sjt_new_verification', methods=['POST'])
def send_sjt_new_verification():
    try:
        data = request.json
        if data is None:
            return jsonify({"error": "No JSON data provided"}), 400
        
        emails = data.get("emails")
        names = data.get("names")
        phone_numbers = data.get("phone_numbers")
        
        for email, name, phone_number in zip(emails, names, phone_numbers):
            send_sjt_new_test(name, email, phone_number)

        print("SJT Verification email/s sent successfully")

        return jsonify({"message": "SJT Verification email/s sent successfully"}), 200
        
    except Exception as e:
        print(f"Failed to send SJT Verification: {str(e)}")
        logger.error(f"Failed to send SJT Verification: {str(e)}")
        return jsonify({"error": f"Failed to send SJT Verification: {str(e)}"}), 500

def send_sjt_new_test(name, email, phone_number):
    candidate_id = f"{random.randint(0, 999)}{int(datetime.now().timestamp() * 1000)}"
    candidate_url = f"https://onlinetest.techifysolutions.com/#/?candidate_id={candidate_id}/sjt"
    passcode = str(random.randint(100000, 999999))
    
    cursor = None
    conn = None
    
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prod.sjt_registration (
                candidate_id VARCHAR(50) PRIMARY KEY,
                email VARCHAR(50),
                name VARCHAR(50),
                phone_number VARCHAR(15),
                passcode VARCHAR(10),
                test_attempted BOOLEAN DEFAULT FALSE,
                entry_date TIMESTAMP,
                test_attempted_date TIMESTAMP
            )
        ''')

        entry_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        cursor.execute('''
            INSERT INTO prod.sjt_registration (candidate_id, email, name, phone_number, passcode, entry_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (candidate_id) DO UPDATE SET email = EXCLUDED.email, passcode = EXCLUDED.passcode;
        ''', (candidate_id, email, name, phone_number, passcode, entry_date))

        conn.commit()

        body = f"""
            Dear {name},
            <br>Thank you for your continued interest in joining Techify. We are pleased with your progress thus far and would like to invite you to complete a psychometric assessment as the next step in our selection process.
            <br><br>Assessment Details:
            <br>This assessment link is valid for one attempt only.
            <br>Please ensure you have a stable internet connection before beginning the test.
            <br>We recommend <b>carefully reviewing all instructions</b> prior to starting the test.
            <br><br>Access Information:
            <br><b>Assessment Link: <a href="{candidate_url}">Test Link</a></b>
            <br>Unique Access Code: {passcode}
            <br><br>This assessment is designed to provide a more comprehensive understanding of your work preferences and aptitudes. The results will help us determine how your unique strengths align with our team dynamics and organizational culture.
            <br>Should you encounter any technical difficulties during the assessment, please contact our Talent Acquisition team at +91 7862063131.
            <br>We appreciate your participation in this process and look forward to reviewing your completed assessment.
            <br><br>Regards,
            <br>Talent Acquisition Team 
            <br>Techify Solutions
            <br>hr@techifysolutions.com 
            <br>+91 7862063131
            """

        subject = "Invite to test from Techify Solutions Pvt Ltd"
        send_email(subject, body, [email], [])
        print("SJT Verification email sent successfully")
    
    except Exception as e:
        print(f"Error in send_sjt_new_test: {str(e)}")
        logger.error(f"Error in send_sjt_new_test: {str(e)}")
        return jsonify({"error": f"Error in send_sjt_new_test: {str(e)}"}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/send_sjt_verification', methods=['POST'])
def send_sjt_verification():
    try:
        data = request.json
        if data is None:
            return jsonify({"error": "No JSON data provided"}), 400
        
        emails = data.get("emails")
        names = data.get("names")
        phone_numbers = data.get("phone_numbers")
        candidate_ids = data.get("candidate_ids")
        
        for email, name, phone_number, candidate_id in zip(emails, names, phone_numbers, candidate_ids):
            send_sjt_test(name, email, phone_number, candidate_id)

        print("SJT Verification email/s sent successfully")

        return jsonify({"message": "SJT Verification email/s sent successfully"}), 200
        
    except Exception as e:
        print(f"Failed to send SJT Verification: {str(e)}")
        logger.error(f"Failed to send SJT Verification: {str(e)}")
        return jsonify({"error": f"Failed to send SJT Verification: {str(e)}"}), 500

def send_sjt_test(name, email, phone_number, candidate_id):
    # candidate_id = f"{random.randint(0, 999)}{int(datetime.now().timestamp() * 1000)}"
    candidate_url = f"https://onlinetest.techifysolutions.com/#/?candidate_id={candidate_id}/sjt"
    passcode = str(random.randint(100000, 999999))
    
    cursor = None
    conn = None
    
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prod.sjt_registration (
                candidate_id VARCHAR(50) PRIMARY KEY,
                email VARCHAR(50),
                name VARCHAR(50),
                phone_number VARCHAR(15),
                passcode VARCHAR(10),
                test_attempted BOOLEAN DEFAULT FALSE,
                entry_date TIMESTAMP,
                test_attempted_date TIMESTAMP
            )
        ''')

        entry_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        cursor.execute('''
            INSERT INTO prod.sjt_registration (candidate_id, email, name, phone_number, passcode, entry_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (candidate_id) DO UPDATE SET email = EXCLUDED.email, passcode = EXCLUDED.passcode;
        ''', (candidate_id, email, name, phone_number, passcode, entry_date))

        conn.commit()

        body = f"""
            Dear {name},
            <br>Thank you for your continued interest in joining Techify. We are pleased with your progress thus far and would like to invite you to complete a psychometric assessment as the next step in our selection process.
            <br><br>Assessment Details:
            <br>This assessment link is valid for one attempt only.
            <br>Please ensure you have a stable internet connection before beginning the test.
            <br>We recommend <b>carefully reviewing all instructions</b> prior to starting the test.
            <br><br>Access Information:
            <br><b>Assessment Link: <a href="{candidate_url}">Test Link</a></b>
            <br>Unique Access Code: {passcode}
            <br><br>This assessment is designed to provide a more comprehensive understanding of your work preferences and aptitudes. The results will help us determine how your unique strengths align with our team dynamics and organizational culture.
            <br>Should you encounter any technical difficulties during the assessment, please contact our Talent Acquisition team at +91 7862063131.
            <br>We appreciate your participation in this process and look forward to reviewing your completed assessment.
            <br><br>Regards,
            <br>Talent Acquisition Team 
            <br>Techify Solutions
            <br>hr@techifysolutions.com 
            <br>+91 7862063131
            """

        subject = "Invite to test from Techify Solutions Pvt Ltd"
        send_email(subject, body, [email], [])
        print("SJT Verification email sent successfully")
    
    except Exception as e:
        print(f"Error in send_sjt_new_test: {str(e)}")
        logger.error(f"Error in send_sjt_new_test: {str(e)}")
        return jsonify({"error": f"Error in send_sjt_new_test: {str(e)}"}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/verify_sjt_passcode', methods=['POST'])
def verify_sjt_passcode():
    data = request.json
    candidate_id = data.get("candidate_id")
    passcode = data.get("passcode")

    if not candidate_id or not passcode:
        return jsonify({"error": "Candidate ID and passcode are required"}), 400
    cursor = None
    conn = None

    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            SELECT passcode, test_attempted FROM prod.sjt_registration WHERE candidate_id = %s;
        ''', (candidate_id,))
        result = cursor.fetchone()

        if result:
            stored_passcode, test_attempted = result
            if stored_passcode == passcode and not test_attempted:
                print("SJT Verification successful")
                return jsonify({"message": "SJT Verification successful, you can proceed with the test"}), 200
            else:
                return jsonify({"error": "Invalid SJT passcode or SJT test already attempted"}), 400
        else:
            return jsonify({"error": "SJT Candidate ID not found"}), 404

    except Exception as e:
        print(f"Error verifying SJT passcode: {str(e)}")
        logger.error(f"Error verifying SJT passcode: {str(e)}")
        return jsonify({"error": f"Error verifying SJT passcode: {str(e)}"}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/start_sjt_test', methods=['POST'])
def start_sjt_test():
    data = request.json
    candidate_id = data.get("candidate_id")

    if not candidate_id:
        return jsonify({"error": "SJT Candidate ID is required"}), 400
    cursor = None
    conn = None
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )
        
        cursor = conn.cursor()

        test_attempted_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        cursor.execute('''
            UPDATE prod.sjt_registration SET test_attempted = TRUE, test_attempted_date = %s WHERE candidate_id = %s;
        ''', (test_attempted_date, candidate_id,))
        conn.commit()

        print("SJT Test started successfully")

        return jsonify({"message": "SJT Test started successfully"}), 200

    except Exception as e:
        print(f"Error starting SJT Test: {str(e)}")
        logger.error(f"Error starting SJT Test: {str(e)}")
        return jsonify({"error": f"Error starting SJT Test: {str(e)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/submit_sjt_test', methods=['POST'])
def submit_sjt_test():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        candidate_id = data.get('candidate_id')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        email = data.get('email')
        phone_number = data.get('phone_number')
        location = data.get('location')
        time_taken = data.get('time_taken')
        submit_reason = data.get('submit_reason')
        result_file = data.get('result_file')

        if not result_file:
            return jsonify({"error": "No result_file data provided"}), 400
        
        else:
            print("generating report")

            with open('sjt_questions.json') as f:
                sjt_questions = json.load(f)

            with open('traits.json') as f:
                traits_data = json.load(f)

            trait_scores = {trait['trait']: {'score': 0, 'category': trait['category'], 'count': trait['count']} for trait in traits_data['traits']}

            category_scores = {trait['category']: 0 for trait in traits_data['traits']}

            def calculate_score(result_file):
                total_score = 0
                for question_id, user_response in result_file.items():

                    user_options = user_response.split('|')
                    user_options_json = {option.strip(): value for option, value in zip(user_options, [5, 3, 1, -1])}
                    # print(user_options_json)

                    question_data = sjt_questions[int(question_id)]
                    # print(question_data)
                    
                    score = 0

                    for option in user_options:
                        correct_score = question_data['score'].get(option.strip(), 0)
                        given_score = user_options_json.get(option.strip(), 0)
                        score += (5 - abs(correct_score - given_score))  # Score = ∑(5−| X given − X correct |)

                    total_score += score
                    
                    for trait in question_data.get('traits', []):
                        trait_scores[trait]['score'] += score  # Update the score for the trait
                        category_scores[trait_scores[trait]['category']] += score  # Add score to the corresponding category

                print("Calculating Trait Score")
                try:
                    for trait in trait_scores:
                        if trait_scores[trait]['count'] > 0:
                            trait_scores[trait]['score'] = "{:.2f}".format(float(trait_scores[trait]['score']) / float(trait_scores[trait]['count']))  # Divide by count and format as .2f

                except ValueError as e:
                    print(f"Error converting trait scores to float: {e}")
                    logger.error(f"Error converting trait scores to float: {e}")
                    return jsonify({"error": "Invalid trait score format"}), 500
                
                return total_score / 20, trait_scores, category_scores
            
            print("Calculating Score")
            
            score, trait_scores, category_scores = calculate_score(result_file)

            print("Calculating Category Score")
            try:
                category_scores['Agreeableness'] = "{:.2f}".format(float(category_scores['Agreeableness']))  # Ensure it's a float
                category_scores['Conscientiousness'] = "{:.2f}".format(float(category_scores['Conscientiousness']))  # Ensure it's a float
                category_scores['Extraversion'] = "{:.2f}".format(float(category_scores['Extraversion']))  # Ensure it's a float
                category_scores['Neuroticism'] = "{:.2f}".format(float(category_scores['Neuroticism']))  # Ensure it's a float
                category_scores['Openness'] = "{:.2f}".format(float(category_scores['Openness']))  # Ensure it's a float
            
            except ValueError as e:
                print(f"Error converting category scores to float: {e}")
                logger.error(f"Error converting category scores to float: {e}")
                return jsonify({"error": "Invalid category score format"}), 500

            file_path = f"psychometric_test.pdf"

            print("Starting report generation")
            
            def generate_pdf_report(candidate_id, first_name, last_name, email, phone_number, location, time_taken, score):
                text = "Psychometric Test"
                
                c = canvas.Canvas(file_path, pagesize=letter)
                
                c.setFont("Helvetica-Bold", 16)
                text_width = c.stringWidth(text, "Helvetica-Bold", 16)
                c.drawString((letter[0] - text_width) / 2, 750, text)

                c.setFont("Helvetica-Bold", 12)
                c.drawString(100, 730, "Candidate Information")
                
                print("Candidate Details")

                c.setFont("Helvetica", 12)
                details = [
                    ("Candidate ID", candidate_id),
                    ("Name", first_name + " " + last_name),
                    ("Email", email),
                    ("Phone Number", phone_number),
                    ("Location", location),
                    ("Time Taken", time_taken),
                    ("Score", score)
                ]
                
                y_position = 710
                for field, value in details:
                    c.drawString(100, y_position, field)
                    c.drawString(300, y_position, str(value))
                    y_position -= 15

                print("Category Scores")

                c.setFont("Helvetica-Bold", 16)
                c.drawString(100, 500, "Category Scores")
                y_position -= 10
                
                c.setFont("Helvetica-Bold", 12)
                c.drawString(100, 475, "Category")
                y_position -= 10
                c.drawString(300, 475, "Score")
                
                c.line(100, 470, 400, 470)
                
                y_position = 455
                c.setFont("Helvetica", 12)
                for category, score in category_scores.items():
                    c.drawString(100, y_position, category)
                    c.drawString(300, y_position, "{:.2f}".format(float(score)))
                    y_position -= 15
                
                c.showPage()

                print("Trait Scores")

                c.setFont("Helvetica-Bold", 16)
                c.drawString(100, 750, "Trait Scores")
                y_position = 735
                y_position -= 10
                
                c.setFont("Helvetica-Bold", 12)
                c.drawString(100, y_position, "Trait")
                c.drawString(300, y_position, "Score")
                c.drawString(400, y_position, "Category")
                y_position -= 15

                c.line(100, y_position + 10, 500, y_position + 10)
                y_position -= 5

                c.setFont("Helvetica", 12)
                for trait, details in trait_scores.items():
                    c.drawString(100, y_position, trait)
                    c.drawString(300, y_position, "{:.2f}".format(float(details['score'])))
                    c.drawString(400, y_position, details['category'])
                    y_position -= 15
                
                c.showPage()

                def draw_wrapped_text(c, text, x, y, max_width):
                    words = text.split(' ')
                    current_line = ''
                    for word in words:
                        test_line = current_line + ' ' + word if current_line else word
                        if c.stringWidth(test_line, "Helvetica", 12) < max_width:
                            current_line = test_line
                        else:
                            c.drawString(x, y, current_line)
                            y -= 15
                            current_line = word

                    if current_line:
                        c.drawString(x, y, current_line)
                        y -= 15

                    return y
                
                print("Questions")
                
                y_position = 750

                for question_data in sjt_questions:
                    question_id = sjt_questions.index(question_data)
                    user_response = result_file.get(str(question_id), "")
                    user_options = user_response.split('|') if user_response else []
                    user_options_json = {option.strip(): value for option, value in zip(user_options, [5, 3, 1, -1])}

                    # Check if y_position is less than 150 to start a new page
                    if y_position < 300:
                        c.showPage()
                        y_position = 750

                    c.setFont("Helvetica-Bold", 12)
                    question_text = "Question: {}".format(question_data['question'])

                    # Check if the question will fit on the page
                    if y_position - 15 < 300:  # 15 is the height of the next line
                        c.showPage()
                        y_position = 750

                    # Draw the question text
                    y_position = draw_wrapped_text(c, question_text, 100, y_position, 400)

                    # Add spacing before "Selected Options"
                    y_position -= 10  # Adjust this value for more or less spacing

                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(100, y_position, "Selected Options:")
                    y_position -= 15
                    
                    c.setFont("Helvetica", 12)
                    for option, score in user_options_json.items():
                        y_position = draw_wrapped_text(c, "{}: {}".format(score, option), 100, y_position, 400)

                    y_position -= 15  # Add spacing after options

                    # Add header for scores
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(100, y_position, "Options with Scores:")
                    y_position -= 15  # Move down for the options

                    c.setFont("Helvetica", 12)
                    options_with_scores = [
                        "{}: {}".format(question_data['score'][option], option) for option in question_data['score']
                    ]
                    for option_score in options_with_scores:
                        y_position = draw_wrapped_text(c, option_score, 100, y_position, 400)

                    y_position -= 15

                    # Add traits text
                    c.setFont("Helvetica-Bold", 12)
                    traits_text = "Traits: {}".format(", ".join(question_data.get('traits', [])))
                    y_position = draw_wrapped_text(c, traits_text, 100, y_position, 400)

                    # Add spacing before the next question
                    y_position -= 50  # Adjust this value for more or less spacing before the next question

                    # Check if y_position is less than 150 to start a new page
                    if y_position < 300:
                        c.showPage()
                        y_position = 750

                c.save()
            
            generate_pdf_report(candidate_id, first_name, last_name, email, phone_number, location, time_taken, score)

            print("Uploading to s3")

            s3_key = f'prod/sjt_reports/{candidate_id}'
            try:
                s3_client.upload_file(
                    file_path, 'onlinetest-stag-documents', s3_key,
                    ExtraArgs={
                        "ContentDisposition": "inline",
                        "ContentType": "application/pdf",
                        "ACL": "public-read"
                    }
                )
                print(f"File uploaded to S3: s3://onlinetest-stag-documents/{s3_key}")

            except NoCredentialsError:
                print("S3: Credentials not available.")
            except PartialCredentialsError:
                print("S3: Incomplete credentials provided.")
            except Exception as e:
                print(f"S3: An error occurred: {e}")
            
            print("s3 upload finished. fetching location")

            try:
                latitude, longitude = location.split(",")
                location = get_address_from_coordinates_nominatim(latitude, longitude)
                print("Lat/Long fetched successfully")

            except Exception as e:
                print(f"Error getting address from coordinates: {e}")
                logger.error(f"Error getting address from coordinates: {e}")
                return jsonify({"error": "Failed to get address from coordinates"}), 500
            
            print("location fetched. storing data now.")

            try:
                store_sjt_data(candidate_id, first_name, last_name, email, phone_number, location, score, category_scores['Agreeableness'], category_scores['Conscientiousness'], category_scores['Extraversion'], category_scores['Neuroticism'], category_scores['Openness'], time_taken, f'https://onlinetest-stag-documents.s3.us-east-1.amazonaws.com/{s3_key}', submit_reason)
                print("SJT data stored successfully")

            except Exception as e:
                print(f"Error storing SJT user data: {e}")
                logger.error(f"Error storing SJT user data: {e}")
                return jsonify({"error": "Failed to store SJT user data"}), 500
            
            try:
                to_emails = ['firefans121@gmail.com']
                cc_emails = ['pooja.shah@techifysolutions.com']
                # hr@techifysolutions.com
                # , 'jobs@techifysolutions.com', 'zankhan.kukadiya@techifysolutions.com'
                subject = f'Test Report {first_name} {last_name}'
                body = f"""
                Please find the attached psychometric test report.<br><br>
                Candidate ID: {candidate_id}<br>
                First Name: {first_name}<br>
                Last Name: {last_name}<br>
                """
                send_email(subject, body, to_emails, cc_emails, attachment_path=file_path)
                print("SJT Report sent")
                 
            except Exception as e:
                print(f"Error sending SJT report email: {e}")
                logger.error(f"Error sending SJT report email: {e}")
                return jsonify({"error": "Failed to send SJT report email"}), 500
        
        
            try:
                to_email = email
                subject = "Test Submitted Successfully"
                body = f"""
                Dear {first_name},
                <br>Thank you for completing the Techify psychometric assessment. We are pleased to confirm that your submission has been successfully received.
                <br>Our technical evaluation team will now review your work thoroughly. We appreciate the time and effort you've invested in this process and will be in touch with you regarding next steps.
                <br>If you have any questions in the interim, please don't hesitate to contact our Talent Acquisition Team.
                <br><br>Regards,
                <br>Talent Acquisition Team 
                <br>Techify Solutions
                <br>hr@techifysolutions.com 
                <br>+91 786-206-3131
                """
                send_email(subject, body, [to_email], [])
                print("SJT Submission confirmation mail sent")
                

            except Exception as e:
                print(f"Error sending SJT submission confirmation mail: {e}")
                logger.error(f"Error sending SJT submission confirmation mail: {e}")
                return jsonify({"error": "Failed to send SJT submission confirmation mail"}), 500
        
        return jsonify({"message": "SJT Test submitted successfully"}), 200

    except Exception as e:
        print(f"Error in submit_sjt_test: {e}")
        logger.error(f"Error in submit_sjt_test: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/submit_sjt_feedback', methods=['POST'])
def submit_sjt_feedback():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_id = data.get("candidate_id")
        feedback = data.get("feedback")

        if not candidate_id or not feedback:
            return jsonify({"error": "SJT Candidate ID and feedback are required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )
        
        cursor = conn.cursor()

        sql_query = '''
        UPDATE prod.sjt_test_reports
        SET feedback = %s
        WHERE candidate_id = %s;
        '''

        cursor.execute(sql_query, (feedback, candidate_id))

        conn.commit()
        print("SJT Feedback updated successfully.")
        
        return jsonify({"message": "SJT Feedback updated successfully"}), 200

    except Exception as e:
        print(f"Error updating SJT Feedback: {e}")
        logger.error(f"Error updating SJT Feedback: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def store_sjt_data(candidate_id, first_name, last_name, email, phone_number, location, score, agreeableness, conscientiousness, extraversion, neuroticism, openness, time_taken, report_s3_url, submit_reason):
    cursor = None
    conn = None
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prod.sjt_test_reports (
                candidate_id VARCHAR(50) PRIMARY KEY,
                first_name VARCHAR(50),
                last_name VARCHAR(50),
                email VARCHAR(50),
                phone_number VARCHAR(15),
                location VARCHAR(50),
                score varchar(10),
                agreeableness varchar(10),
                conscientiousness varchar(10),
                extraversion varchar(10),
                neuroticism varchar(10),
                openness varchar(10),
                time_taken VARCHAR(50),
                feedback TEXT DEFAULT '',
                report_s3_url TEXT,
                submission_date TIMESTAMP,
                submit_reason VARCHAR(20)
            )
            ''')

        submission_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        cursor.execute('''
            INSERT INTO prod.sjt_test_reports (candidate_id, first_name, last_name, email, phone_number, location, score, agreeableness, conscientiousness, extraversion, neuroticism, openness, time_taken, report_s3_url, submission_date, submit_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (candidate_id, first_name, last_name, email, phone_number, location, score, agreeableness, conscientiousness, extraversion, neuroticism, openness, time_taken, report_s3_url, submission_date, submit_reason))
        
        conn.commit()

        print("SJT User data stored successfully")
        
    except psycopg2.DatabaseError as e:
        print(f"SJT Database error: {e}")
        logger.error(f"SJT Database error: {e}")
        return jsonify({"error": f"SJT Database error: {str(e)}"}), 500

    except Exception as e:
        print(f"SJT Error storing user data: {e}")
        logger.error(f"SJT Error storing user data: {e}")
        return jsonify({"error": f"SJT Error storing user data: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/fetch_sjt_data', methods=['GET'])
def fetch_sjt_data():
    cursor = None
    conn = None
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('SELECT * FROM prod.sjt_test_reports ORDER BY submission_date DESC')
        rows = cursor.fetchall()

        user_data = []
        for row in rows:
            user_data.append({
                "candidate_id": row[0],
                "first_name": row[1],
                "last_name": row[2],
                "email": row[3],
                "phone_number": row[4],
                "location": row[5],
                "agreeableness": row[6], 
                "conscientiousness": row[7], 
                "extraversion": row[8],
                "neuroticism": row[9],
                "openness": row[10],
                "score": row[11],
                "time_taken": row[12],
                "feedback": row[13],
                "report_s3_url": row[14],
                "submission_date": row[15],
                "submit_reason": row[16]
            })

        print("SJT User data fetched successfully")

        return jsonify(user_data), 200

    except Exception as e:
        print(f"Error fetching SJT data: {str(e)}")
        logger.error(f"Error fetching SJT data: {str(e)}")
        return jsonify({"error": f"Error fetching SJT data: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/delete_sjt_data', methods=['DELETE'])
def delete_sjt_data():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_ids = data.get("candidate_ids")

        if not candidate_ids or not isinstance(candidate_ids, list):
            return jsonify({"error": "A list of Candidate IDs is required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        DELETE FROM prod.sjt_test_reports
        WHERE candidate_id = ANY(%s);
        '''

        s3_key = f'prod/sjt_reports/{candidate_ids[0]}'
        try:
            s3_client.delete_object(Bucket='onlinetest-stag-documents', Key=s3_key)
            print(f"Deleted SJT report for candidate ID: {candidate_ids[0]} from S3.")
        except NoCredentialsError:
            print("S3: Credentials not available.")
        except PartialCredentialsError:
            print("S3: Incomplete credentials provided.")
        except Exception as e:
            print(f"S3: An error occurred: {e}")

        cursor.execute(sql_query, (candidate_ids,))

        conn.commit()
        print(f"SJT data for {len(candidate_ids)} candidates deleted successfully.")
        
        return jsonify({"message": f"SJT data for {len(candidate_ids)} candidates deleted successfully"}), 200

    except Exception as e:
        print(f"Error deleting SJT data: {e}")
        logger.error(f"Error deleting SJT data: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/export_sjt_data', methods=['POST'])
def export_sjt_data():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_ids = data.get("candidate_ids")

        if not candidate_ids or not isinstance(candidate_ids, list):
            return jsonify({"error": "A list of Candidate IDs is required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        SELECT * FROM prod.sjt_test_reports
        WHERE candidate_id = ANY(%s);
        '''

        cursor.execute(sql_query, (candidate_ids,))
        rows = cursor.fetchall()

        columns = [
            "candidate_id", "first_name", "last_name", "email", "phone_number", "location", "score", "agreeableness", "conscientiousness", "extraversion", "neuroticism", "openness", "time_taken", "feedback", "report_s3_url", "submission_date", "submit_reason"
        ]
        data_to_export = [dict(zip(columns, row)) for row in rows]

        for entry in data_to_export:
            if isinstance(entry['submission_date'], datetime):
                entry['submission_date'] = entry['submission_date'].replace(tzinfo=None)

        df = pd.DataFrame(data_to_export)
        excel_file_path = '/tmp/sjt_data.xlsx'
        df.to_excel(excel_file_path, index=False)

        print("SJT data exported successfully")

        return send_file(excel_file_path, as_attachment=True)

    except Exception as e:
        print(f"Error exporting SJT data: {e}")
        logger.error(f"Error exporting SJT data: {str(e)}")
        return jsonify({"error": f"Error exporting SJT data: {str(e)}"}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/upload_sjt_excel', methods=['POST'])
def upload_sjt_excel():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join('/tmp', filename)
            file.save(file_path)

            # Read the Excel file
            df = pd.read_excel(file_path)

            # Check if required columns are present
            if not {'Name', 'Email', 'Phone_Number'}.issubset(df.columns):
                return jsonify({"error": "Excel file must contain 'Name', 'Email', and 'Phone_Number' columns"}), 400

            # Iterate over each row and call send_test
            for _, row in df.iterrows():
                name = row['Name']
                email = row['Email']
                phone_number = row['Phone_Number']
                send_sjt_new_test(name, email, phone_number)

            print("Verification emails sent successfully from Excel upload")

            return jsonify({"message": "Verification emails sent successfully"}), 200

    except Exception as e:
        print(f"Error processing Excel file: {str(e)}")
        logger.error(f"Error processing Excel file: {str(e)}")
        return jsonify({"error": f"Error processing Excel file: {str(e)}"}), 500
    
def compress_pdf(input_path, output_path):
    try:
        # Open the PDF
        document = fitz.open(input_path)
        # Create a new PDF writer
        writer = fitz.open()

        # Iterate through each page
        for page_number in range(document.page_count):
            page = document.load_page(page_number)
            # Add the page to the writer
            writer.insert_pdf(document, from_page=page_number, to_page=page_number)

        # Save the compressed PDF
        writer.save(output_path, garbage=4, deflate=True, clean=True)
        writer.close()
        document.close()

    except Exception as e:
        print(f"Error compressing PDF: {e}")
        logger.error(f"Error compressing PDF: {e}")
        raise

@app.route('/fetch_sjt_registration', methods=['GET'])
def fetch_sjt_registration():
    cursor = None
    conn = None
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('SELECT * FROM prod.sjt_registration ORDER BY entry_date DESC')
        rows = cursor.fetchall()

        sjt_registration_data = []
        for row in rows:
            sjt_registration_data.append({
                "candidate_id": row[0],
                "email": row[1],
                "name": row[2],
                "phone_number": row[3],
                "passcode": row[4],
                "test_attempted": row[5],
                "entry_date": row[6],
                "test_attempted_date": row[7]
            })

        print("SJT Registration data fetched successfully")

        return jsonify(sjt_registration_data), 200

    except Exception as e:
        print(f"Error fetching SJT registration data: {str(e)}")
        logger.error(f"Error fetching SJT registration data: {str(e)}")
        return jsonify({"error": f"Error fetching SJT registration data: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/delete_sjt_registration_data', methods=['DELETE'])
def delete_sjt_registration_data():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_ids = data.get("candidate_ids")

        if not candidate_ids or not isinstance(candidate_ids, list):
            return jsonify({"error": "A list of Candidate IDs is required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        DELETE FROM prod.sjt_registration
        WHERE candidate_id = ANY(%s);
        '''

        s3_key = f'prod/sjt_reports/{candidate_ids[0]}'
        try:
            s3_client.delete_object(Bucket='onlinetest-stag-documents', Key=s3_key)
            print(f"Deleted SJT report for candidate ID: {candidate_ids[0]} from S3.")
        except NoCredentialsError:
            print("S3: Credentials not available.")
        except PartialCredentialsError:
            print("S3: Incomplete credentials provided.")
        except Exception as e:
            print(f"S3: An error occurred: {e}")

        cursor.execute(sql_query, (candidate_ids,))

        conn.commit()
        print(f"SJT registration data for {len(candidate_ids)} candidates deleted successfully.")
        
        return jsonify({"message": f"SJT registration data for {len(candidate_ids)} candidates deleted successfully"}), 200

    except Exception as e:
        print(f"Error deleting SJT registration data: {e}")
        logger.error(f"Error deleting SJT registration data: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/export_sjt_registration_data', methods=['POST'])
def export_sjt_registration_data():
    cursor = None
    conn = None
    try:
        data = request.json
        candidate_ids = data.get("candidate_ids")

        if not candidate_ids or not isinstance(candidate_ids, list):
            return jsonify({"error": "A list of Candidate IDs is required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        SELECT candidate_id, email, name, phone_number, test_attempted, entry_date
        FROM prod.sjt_registration
        WHERE candidate_id = ANY(%s);
        '''

        cursor.execute(sql_query, (candidate_ids,))
        rows = cursor.fetchall()

        columns = [
            "candidate_id", "email", "name", "phone_number",
            "test_attempted", "entry_date"
        ]
        data_to_export = [dict(zip(columns, row)) for row in rows]

        for entry in data_to_export:
            if isinstance(entry['entry_date'], datetime):
                entry['entry_date'] = entry['entry_date'].replace(tzinfo=None)

        df = pd.DataFrame(data_to_export)
        excel_file_path = '/tmp/sjt_registration_data.xlsx'
        df.to_excel(excel_file_path, index=False)

        print("SJT registration data exported successfully")

        return send_file(excel_file_path, as_attachment=True)

    except Exception as e:
        print(f"Error exporting SJT registration data: {e}")
        logger.error(f"Error exporting SJT registration data: {str(e)}")
        return jsonify({"error": f"Error exporting SJT registration data: {str(e)}"}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/health', methods=['GET'])
def health_check():
    print("Health check successful")
    return jsonify({"status": "healthy"}), 200

@app.route('/verify_login', methods=['POST'])
def verify_login():
    cursor = None
    conn = None
    try:
        data = request.json
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='10.1.0.18',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            SELECT permission_access FROM prod.login WHERE username = %s AND password = %s;
        ''', (username, password))
        result = cursor.fetchone()

        if result:
            permission_access = result[0]
            return jsonify({"success": True, "permission_access": permission_access}), 200
        else:
            return jsonify({"success": False, "permission_access": "no"}), 200

    except Exception as e:
        print(f"Error verifying login: {str(e)}")
        logger.error(f"Error verifying login: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)