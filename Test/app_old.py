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
from datetime import datetime
import boto3
import psycopg2
import pandas as pd
import base64
import logging

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
    "supports_credentials": True
}})

SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
EMAIL_SENDER = 'hrtest.techify@gmail.com'
EMAIL_PASSWORD = 'twar fdoi zxau djde'

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

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
            logger.error(f"Error receiving response while getting address from coordinates with status code {response.status_code}")
            return None
    except requests.RequestException as e:
        logger.error(f"Request error while getting address from coordinates: {e}")
        return jsonify({"error": f"Request error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error getting address from coordinates: {e}")
        return jsonify({"error": f"General error: {str(e)}"}), 500

def select_questions(input_file, level, num_questions, output_file, append=False):
    try:
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file does not exist: {input_file}")

        json_output = os.path.join(output_file)

        with open(input_file, 'r') as f:
            questions = json.load(f)

        level_questions = [q for q in questions if q['Level'] == level]
        
        if not level_questions:
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
            logger.error(f"Warning: All questions for level {level} have already been selected")
            return
            
        if num_questions > len(available_questions):
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
        logger.error(f"File not found: {e}")
        return jsonify({"error while selecting questions": str(e)}), 400
    
    except json.JSONDecodeError:
        logger.error("Invalid JSON format in input file")
        return jsonify({"error while selecting questions": "Invalid JSON format in input file"}), 400
    
    except Exception as e:
        logger.error(f"Error while selecting questions: {e}")
        return jsonify({"error while selecting questions": str(e)}), 500
    
@app.route('/generate_questions', methods=['GET'])
def generate_questions():
    try:
        select_questions(input_file="aptitude.txt", level="Basic", num_questions=2, output_file="aptitude_questions.json", append=False)
        select_questions(input_file="aptitude.txt", level="Intermediate", num_questions=6, output_file="aptitude_questions.json", append=True)
        select_questions(input_file="aptitude.txt", level="Advanced", num_questions=7, output_file="aptitude_questions.json", append=True)
        select_questions(input_file="verbalq.txt", level="Basic", num_questions=6, output_file="verbal_questions.json", append=False)
        select_questions(input_file="verbalq.txt", level="Intermediate", num_questions=4, output_file="verbal_questions.json", append=True)
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
        logger.error(f"Error while getting reasoning questions: {e}")
        return jsonify({"error while getting reasoning questions": str(e)}), 500
    

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

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, all_recipients, msg.as_string())
        server.quit()
        return True
    
    except smtplib.SMTPException as e:
        logger.error(f'SMTP error: {e}')
        return jsonify({"error": f"SMTP error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f'Error sending email: {e}')
        return jsonify({"error": f"Error sending email: {str(e)}"}), 500

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
            report_path = os.path.join('/tmp', file.filename)
            file.save(report_path)

            s3_client = boto3.client('s3')
            s3_bucket = 'onlinetest-stag-documents'
            s3_key = f'reports/{candidate_id}'
            report_s3_url = f'https://{s3_bucket}.s3.us-east-1.amazonaws.com/{s3_key}'
            
            try:
                s3_client.upload_file(
                    report_path, s3_bucket, s3_key,
                    ExtraArgs={
                        "ContentDisposition": "inline",
                        "ContentType": "application/pdf",
                        "ACL": "public-read"
                    }
                )

                s3_client.put_object_acl(Bucket=s3_bucket, Key=s3_key, ACL='public-read')
            except Exception as e:
                logger.error(f"Error uploading report to S3: {e}")
                return jsonify({"error": "Failed to upload report to S3"}), 500
            print("Report uploaded to S3 successfully")
            
            try:
                latitude, longitude = location.split(",")
                location = get_address_from_coordinates_nominatim(latitude, longitude)
            except Exception as e:
                logger.error(f"Error getting address from coordinates: {e}")
                return jsonify({"error": "Failed to get address from coordinates"}), 500
            print("Address fetched successfully")

            try:
                store_user_data(candidate_id, first_name, last_name, email, phone_number, location, score, aptitude_score, verbal_score, programming_score, logical_score, time_taken, report_s3_url, submit_reason)
            except Exception as e:
                logger.error(f"Error storing user data: {e}")
                return jsonify({"error": "Failed to store user data"}), 500
            print("User data stored successfully")

            try:
                to_emails = ['firefans121@gmail.com']
                cc_emails = ['pooja.shah@techifysolutions.com']
                # hr@techifysolutions.com
                # , 'jobs@techifysolutions.com', 'zankhan.kukadiya@techifysolutions.com'
                subject = f'Test Report {first_name} {last_name}'
                body = f"""
                Please find the attached test report.<br><br>
                Candidate ID: {candidate_id}<br>
                First Name: {first_name}<br>
                Last Name: {last_name}<br>
                Score: {score}<br><br>
                """
                send_email(subject, body, to_emails, cc_emails, attachment_path=report_path)
            except Exception as e:
                logger.error(f"Error sending report email: {e}")
                return jsonify({"error": "Failed to send report email"}), 500
            print("Report sent successfully")
        
            try:
                to_email = email
                subject = "Test Submitted Successfully"
                body = f"""
                Your test has been submitted successfully. Someone from our side will get back to you soon. Thank you for your time and effort.<br><br>
                Talent Acquisition Team<br>
                Email: hr@techifysolutions.com<br>
                Mobile: +917862063131<br><br>
                """
                send_email(subject, body, [to_email], [])
            except Exception as e:
                logger.error(f"Error sending submission confirmation mail: {e}")
                return jsonify({"error": "Failed to send submission confirmation mail"}), 500
            print("Submission confirmation mail sent successfully")

            return jsonify({"message": "Test submitted successfully"}), 200

    except Exception as e:
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
            host='localhost',
            port='5432'
        )
        
        cursor = conn.cursor()

        sql_query = '''
        UPDATE hrtest_reports
        SET feedback = %s
        WHERE candidate_id = %s;
        '''

        cursor.execute(sql_query, (feedback, candidate_id))

        conn.commit()
        print("Feedback updated successfully.")
        
        return jsonify({"message": "Feedback updated successfully"}), 200

    except Exception as e:
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
            host='localhost',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hrtest_reports (
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
                submission_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                submit_reason VARCHAR(50)
            )
            ''')

        submission_date = datetime.now().replace(microsecond=0)

        cursor.execute('''
            INSERT INTO hrtest_reports (candidate_id, first_name, last_name, email, phone_number, location, score, aptitude_score, verbal_score, programming_score, logical_score, time_taken, report_s3_url, submission_date, submit_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (candidate_id, first_name, last_name, email, phone_number, location, score, aptitude_score, verbal_score, programming_score, logical_score, time_taken, report_s3_url, submission_date, submit_reason))
        
        conn.commit()

        print("User data stored successfully")
        
    except psycopg2.DatabaseError as e:
        logger.error(f"Database error: {e}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    except Exception as e:
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
            host='localhost',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('SELECT * FROM hrtest_reports ORDER BY submission_date DESC')
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
            host='localhost',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        DELETE FROM hrtest_reports
        WHERE candidate_id = ANY(%s);
        '''

        s3_client = boto3.client('s3')
        s3_bucket = 'onlinetest-stag-documents'
        for candidate_id in candidate_ids:
            s3_key = f'reports/{candidate_id}'
            try:
                s3_client.delete_object(Bucket=s3_bucket, Key=s3_key)
                print(f"Deleted report for candidate ID: {candidate_id} from S3.")
            except Exception as e:
                logger.error(f"Error deleting report for candidate ID {candidate_id} from S3: {e}")
                return jsonify({"error": f"Error deleting report for candidate ID {candidate_id} from S3: {e}"}), 500

        cursor.execute(sql_query, (candidate_ids,))

        conn.commit()
        print(f"User data for {len(candidate_ids)} candidates deleted successfully.")
        
        return jsonify({"message": f"User data for {len(candidate_ids)} candidates deleted successfully"}), 200

    except Exception as e:
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
            host='localhost',
            port='5432'
        )

        cursor = conn.cursor()

        sql_query = '''
        SELECT * FROM hrtest_reports
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
        logger.error(f"Error exporting candidate data: {e}")
        return jsonify({"error": f"Error exporting candidate data: {str(e)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/send_verification', methods=['POST'])
def send_verification():
    try:
        data = request.json
        if data is None:
            return jsonify({"error": "No JSON data provided"}), 400
        
        emails = data.get("emails")
        
        for email in emails:
            send_test(email)

        print("Verification email/s sent successfully")

        return jsonify({"message": "Verification email/s sent successfully"}), 200
        
    except Exception as e:
        logger.error(f"Failed to send verification: {str(e)}")
        return jsonify({"error": f"Failed to send verification: {str(e)}"}), 500

def send_test(email):
    candidate_id = f"{random.randint(0, 999)}{int(datetime.now().timestamp() * 1000)}"
    candidate_url = f"https://stag-onlinetest.techifysolutions.com/?candidate_id={candidate_id}"
    passcode = str(random.randint(100000, 999999))
    
    cursor = None
    conn = None
    
    try:
        conn = psycopg2.connect(
            dbname='hrtest',
            user='hruser',
            password='T@chify$ol8m0s0!',
            host='localhost',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registration (
                candidate_id VARCHAR(50) PRIMARY KEY,
                email VARCHAR(50),
                passcode VARCHAR(10),
                test_attempted BOOLEAN DEFAULT FALSE,
                entry_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                test_attempted_date TIMESTAMP
            )
        ''')

        cursor.execute('''
            INSERT INTO registration (candidate_id, email, passcode, entry_date)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (candidate_id) DO UPDATE SET email = EXCLUDED.email, passcode = EXCLUDED.passcode;
        ''', (candidate_id, email, passcode))

        conn.commit()

        body = f"""
            Dear Candidate,<br><br>
            Greetings!!<br><br>
            Techify's DNA is about Solutions & Technologies. We believe that "Every problem has a solution".<br><br>
            To take your first step to be part of our amazing team, you are invited to appear in a test for your candidature.<br><br>
            The test link will work only for one attempt so please use high speed internet and after one attempt link will be disabled.<br><br>
            Please <b>read the instructions carefully</b> before appearing in the test.<br><br>
            <b>To appear in the test please click here: <a href="{candidate_url}">Test Link</a></b><br><br>
            You will need the following passcode to appear in the test: <b>{passcode}</b><br><br>
            All the best!<br><br>
            Talent Acquisition Team<br>
            Email: hr@techifysolutions.com<br>
            Mobile: +917862063131<br><br>
            **If you face any difficulty while giving the test please reach us at 8390849886 for technical support.
            """

        subject = "Invite to test from Techify Solutions Pvt Ltd"
        send_email(subject, body, [email], [])
        print("Verification email sent successfully")
    
    except Exception as e:
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
            host='localhost',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('''
            SELECT passcode, test_attempted FROM registration WHERE candidate_id = %s;
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
        logger.error(f"Error verifying passcode: {str(e)}")
        return jsonify({"error": f"Error verifying passcode: {str(e)}"}), 500
    
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
            host='localhost',
            port='5432'
        )
        
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE registration SET test_attempted = TRUE, test_attempted_date = CURRENT_TIMESTAMP WHERE candidate_id = %s;
        ''', (candidate_id,))
        conn.commit()

        print("Test started successfully")

        return jsonify({"message": "Test started successfully"}), 200

    except Exception as e:
        logger.error(f"Error starting test: {str(e)}")
        return jsonify({"error": f"Error starting test: {str(e)}"}), 500
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
            host='localhost',
            port='5432'
        )

        cursor = conn.cursor()

        cursor.execute('SELECT * FROM registration ORDER BY entry_date DESC')
        rows = cursor.fetchall()

        registration_data = []
        for row in rows:
            registration_data.append({
                "candidate_id": row[0],
                "email": row[1],
                "passcode": row[2],
                "test_attempted": row[3],
                "entry_date": row[4],
                "test_attempted_date": row[5]
            })

        print("Registration data fetched successfully")

        return jsonify(registration_data), 200

    except Exception as e:
        logger.error(f"Error fetching registration data: {str(e)}")
        return jsonify({"error": f"Error fetching registration data: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/health', methods=['GET'])
def health_check():
    print("Health check successful")
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
