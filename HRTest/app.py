from flask import Flask, request, jsonify
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
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configure your email settings
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
EMAIL_SENDER = 'hrtest.techify@gmail.com'
EMAIL_PASSWORD = 'twar fdoi zxau djde'

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "hr-test.json"
SPREADSHEET_NAME = "Feedback"

credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
client = gspread.authorize(credentials)
sheet = client.open(SPREADSHEET_NAME).sheet1

def select_questions(input_file, level, num_questions, output_file, append=False):
    try:
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
            print(f"Warning: All questions for level {level} have already been selected")
            return
            
        if num_questions > len(available_questions):
            print(f"Warning: Only {len(available_questions)} new questions available for level {level}")
            selected = available_questions
        else:
            selected = random.sample(available_questions, num_questions)
        
        final_questions = existing_questions + selected
        
        with open(json_output, 'w') as f:
            json.dump(final_questions, f, indent=2)
        
        print(f"Successfully {'appended' if append else 'saved'} {len(selected)} questions of level {level}")
        print(f"Total questions in output files: {len(final_questions)}")
        
    except FileNotFoundError:
        print(f"Error: Could not find input file: {input_file}")
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in input file")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

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

        return jsonify({"message": "Questions generated successfully"}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/get_aptitude_questions', methods=['GET'])
def get_aptitude_questions():
    try:
        with open('aptitude_questions.json', 'r') as f:
            data = f.read()
        return data, 200, {'Content-Type': 'text/plain'}
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

@app.route('/get_verbal_questions', methods=['GET'])
def get_verbal_questions():
    try:
        with open('verbal_questions.json', 'r') as f:
            data = f.read()
        return data, 200, {'Content-Type': 'text/plain'}
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

@app.route('/get_programming_questions', methods=['GET'])
def get_programming_questions():
    try:
        with open('programming_questions.json', 'r') as f:
            data = f.read()
        return data, 200, {'Content-Type': 'text/plain'}
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

@app.route('/get_reasoning_questions', methods=['GET'])
def get_reasoning_questions():
    try:
        with open('reasoning_questions.json', 'r') as f:
            data = f.read()
        return data, 200, {'Content-Type': 'text/plain'}
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

def send_email(subject, body, to_recipients, cc_recipients, attachment_path=None):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = ', '.join(to_recipients)
        msg['Cc'] = ', '.join(cc_recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Attach the file if provided
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
    
    except Exception as e:
        print(f'Error sending email: {e}')
        return False

@app.route('/submit_test', methods=['POST'])
def submit_test():
    # Define the email addresses on the backend
    to_emails = ['firefans121@gmail.com']
    cc_emails = ['pooja.shah@techifysolutions.com']
    # hr@techifysolutions.com
    # , 'jobs@techifysolutions.com', 'zankhan.kukadiya@techifysolutions.com'
    subject = 'Test Report'
    body = 'Please find the attached test report.\n'

    # Check if the post request has the file part
    if 'report' not in request.files:
        return jsonify({'error': 'No report file part'}), 400

    file = request.files['report']

    # If the user does not select a file, the browser submits an empty file without a filename
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:
        # Save the file temporarily
        report_path = os.path.join('/tmp', file.filename)
        file.save(report_path)

        # Send the email with the attached report
        if send_email(subject, body, to_emails, cc_emails, attachment_path=report_path):
            return jsonify({'message': 'Report sent successfully'}), 200
        else:
            return jsonify({'error': 'Failed to send email'}), 500
        
@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.json
        date = datetime.today().strftime('%d/%m/%y')
        email = data.get("email")
        feedback = data.get("feedback")

        sheet.append_row([date, email, feedback])

        return jsonify({"message": "Feedback submitted successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
