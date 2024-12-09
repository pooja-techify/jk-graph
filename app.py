import re
import os
import pandas as pd
import numpy as np
import pymupdf
from openpyxl.styles import numbers
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from langchain_community.document_loaders import AmazonTextractPDFLoader
from pdf2image import convert_from_path
import tempfile
from PIL import Image
from textractor import Textractor
from textractor.visualizers.entitylist import EntityList
from textractor.data.constants import TextractFeatures, Direction, DirectionalFinderType
import zipfile
import io
from datetime import datetime

app = Flask(__name__)
CORS(app)

@app.route('/amex', methods=['POST'])
def excel_amex():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)

        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text() 
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'(\d{2}/\d{2}/\d{2})[\**]\s([A-Za-z ]+)\s([A-Za-z- ]+)\s-\$([0-9,]+[.][0-9]{2})'
        cr_pattern2 = r'(\d{2}/\d{2}/\d{2})\s([A-Za-z0-9 \.\*\-\#]+)\s-\$([0-9,]+[.][0-9]{2})'
        db_pattern = r'(\d{2}/\d{2}/\d{2})\s([A-Za-z0-9() .\*\-\#\/]+)\s([A-Z0-9() .\*\-\#\/]*)\s([A-Z0-9() .\*\-\#\/]*)\s([A-Za-z0-9() .\*\-\#\/]*)\s\$([0-9,]+[.][0-9]{2})'
        db_pattern2 = r'(\d{2}/\d{2}/\d{2})\s([A-Za-z0-9 \.\*\-\#]+)\s\$([0-9,]+[.][0-9]{2})'

        credits = []
        debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1)
            user = match.group(3)
            credit = match.group(4)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        for match in re.finditer(cr_pattern2, text):
            date = match.group(1)
            user = match.group(2)
            credit = match.group(3)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        for match in re.finditer(db_pattern, text):
            date = match.group(1)
            user = match.group(2) + " " + match.group(5)
            debit = match.group(6)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })

        for match in re.finditer(db_pattern2, text):
            date = match.group(1)
            user = match.group(2)
            debit = match.group(3)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })

        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)
        credits['credit'] = credits['credit'].apply(clean_amount)

        debits = pd.DataFrame(debits)
        debits['debit'] = debits['debit'].apply(clean_amount)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
            debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

            for cell in worksheet2['C'][1:]:
                cell.number_format = '##0.00'

        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)
        
        # print("Starting textract")
        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("Amex_page_"+str(i+1)+".png", "PNG")
            files.append("Amex_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()

        for f in files:
            # print("New Page")
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                    # print(table_title)
                    if 'Detail' in table_title.text:
                        df=table[0].to_pandas()
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)
                    if 'Interest Charged' in table_title.text:
                        df=table[0].to_pandas()
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)

        df = credits_aws

        df1 = df[df.iloc[:,0].str.match(r'^\d{2}/\d{2}', na=False)].reset_index(drop=True)

        df1.iloc[:, 0] = df1.iloc[:, 0].str.strip()

        for i in range(len(df1)):
           if pd.isna(df1.iloc[i, -1]):
               df1.iloc[i, -1] = df1.iloc[i, df1.iloc[i].last_valid_index()]

        for i in range(len(df1)):
           if df1.iloc[i,0][-1] == '*':
               df1.iloc[i,0] = df1.iloc[i,0][:-1]
           if re.fullmatch(r'\d{2}/\d{2}/\d{2}.+', str(df1.iloc[i, 0])):
               df1.iloc[i, 1] = df1.iloc[i, 0][8:].strip()
               df1.iloc[i, 0] = df1.iloc[i, 0][0:8]

        new_df = df1[[0, 1, len(df1.columns)-1]].rename(columns={0: "date", 1: "description", len(df1.columns)-1: "amount"})

        new_df['amount'] = new_df['amount'].str.replace(r'[$,]', '', regex=True)
        new_df['amount'] = pd.to_numeric(new_df['amount'])


        credits_aws = new_df[new_df['amount']<0]
        credits_aws['amount'] = credits_aws['amount'].astype(str).replace(r'[-,]', '', regex=True)
        credits_aws['amount'] = pd.to_numeric(credits_aws['amount'])

        debits_aws = new_df[new_df['amount']>0]
        debits_aws['amount'] = pd.to_numeric(debits_aws['amount'])


        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )

    except Exception as e:
        print("An error occured: {e}")
        
    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)


@app.route('/bcb', methods=['POST'])
def excel_bcb():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)

        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'(\d{2}/\d{2})\s([A-Za-z0-9\&\#\*\s]+)\s([0-9,]+[.]+[0-9]+)\s*([0-9,]+[.][0-9]{2})\s'
        db_pattern = r'(\d{2}/\d{2})\s([A-Za-z0-9\&\#\*\s]+)\s([0-9,]+[.]+[0-9]+)[-]\s*([0-9,]+[.][0-9]{2})\s'

        credits = []
        debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1) 
            user = match.group(2)
            credit = match.group(3)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        for match in re.finditer(db_pattern, text):
            date = match.group(1) 
            user = match.group(2)
            debit = match.group(3)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })

        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)
        credits['credit'] = credits['credit'].apply(clean_amount)

        debits = pd.DataFrame(debits)
        debits['debit'] = debits['debit'].apply(clean_amount)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
            debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

            for cell in worksheet2['C'][1:]:
                cell.number_format = '##0.00'

        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)


        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("BCB_page_"+str(i+1)+".png", "PNG")
            files.append("BCB_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()
        transactions = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                    ],
                save_image=True
                )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                    if table_title.text in ["ACTIVITY DESCRIPTION"]:
                        df=table[0].to_pandas()
                        transactions = pd.concat([transactions, df], ignore_index=True)

        df = transactions[transactions.iloc[:,0].str.match(r'^\d{2}/\d{2}.*', na=False)].reset_index(drop=True)

        df[['date', 'description']] = df[0].str.split(' ', n=1, expand=True)

        new_df = df[['date','description', 1, 2]].rename(columns={1: "debit", 2: "credit"})

        credit_list = []
        debit_list = []

        for i in range(len(new_df)):
            if new_df.iloc[i, -1] == '':
                debit_list.append(new_df.iloc[i])

            if new_df.iloc[i, -2] == '':
                credit_list.append(new_df.iloc[i])

        credits_aws = pd.DataFrame(credit_list)
        debits_aws = pd.DataFrame(debit_list)

        credits_aws.drop(columns='debit', inplace=True)
        debits_aws.drop(columns='credit', inplace=True)

        debits_aws['debit'] = debits_aws['debit'].astype(str).replace(r'[-,]', '', regex=True)
        debits_aws['debit'] = pd.to_numeric(debits_aws['debit'])

        credits_aws['credit'] = credits_aws['credit'].astype(str).str.replace(r'[$,\s]', '', regex=True)
        credits_aws['credit'] = pd.to_numeric(credits_aws['credit'])

        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")
    
    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)


@app.route('/boa', methods=['POST'])
def excel_boa():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'(\d{2}/\d{2}/\d{2})\s([A-Za-z][A-Za-z0-9\"\'\;\:\#\*\-\&\/ ]+[.|\s][A-Za-z0-9\"\'\;\:\#\*\-\&\/ ]*)\s([0-9,]+[.][0-9]{2})'
        cr_pattern2 = r'(\d{2}/\d{2}/\d{2})\s([0-9]+)[*]?\s([0-9,]+[.][0-9]{2})'
        db_pattern = r'(\d{2}/\d{2}/\d{2})\s([A-Za-z][A-Za-z0-9\"\'\;\:\#\*\-\&\/ ]+[.|\s][A-Za-z0-9\"\'\;\:\#\*\-\&\/ ]*)\s[-]([0-9,]+[.][0-9]{2})'
        db_pattern2 = r'(\d{2}/\d{2}/\d{2})\s([0-9]+)[*]?\s[-]([0-9,]+[.][0-9]{2})'

        credits = []
        debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1)
            user = match.group(2)
            credit = match.group(3)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        for match in re.finditer(cr_pattern2, text):
            date = match.group(1)
            user = match.group(2)
            credit = match.group(3)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        for match in re.finditer(db_pattern, text):
            date = match.group(1)
            user = match.group(2)
            debit = match.group(3)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })

        for match in re.finditer(db_pattern2, text):
            date = match.group(1)
            user = match.group(2)
            debit = match.group(3)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })

        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)
        credits['credit'] = credits['credit'].apply(clean_amount)

        # print(credits)

        debits = pd.DataFrame(debits)
        debits['debit'] = debits['debit'].apply(clean_amount)

        # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
            debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

            for cell in worksheet2['C'][1:]:
                cell.number_format = '##0.00'

        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("BOA_page_"+str(i+1)+".png", "PNG")
            files.append("BOA_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                    # print(table_title.text)
                    if "Deposits" in table_title.text:
                        df=table[0].to_pandas()
                        if len(df.columns) > 3:
                            ori_columns = df.columns
                            for i in range(2, len(df.columns)-1):
                                df[1] = df[1].astype(str) + ' ' + df[ori_columns[i]].astype(str)
                        df1 = df[[0,1,len(df.columns)-1]].rename(columns={0: "date", 1: "description", len(df.columns)-1: "amount"})
                        credits_aws = pd.concat([credits_aws, df1], ignore_index=True)
                        

                    if "Withdrawals" in table_title.text:
                        df=table[0].to_pandas()
                        if len(df.columns) > 3:
                            ori_columns = df.columns
                            for i in range(2, len(df.columns)-1):
                                df[1] = df[1].astype(str) + ' ' + df[ori_columns[i]].astype(str)
                        df1 = df[[0,1,len(df.columns)-1]].rename(columns={0: "date", 1: "description", len(df.columns)-1: "amount"})
                        debits_aws = pd.concat([debits_aws, df1], ignore_index=True)

                    # if "Checks" in table_title.text:
                    #     df=table[0].to_pandas()
                    #     debits_aws = pd.concat([debits_aws, df], ignore_index=True)

        debits_aws1 = debits_aws[debits_aws.iloc[:,0].str.match(r'^\d{2}/\d{2}/\d{2}', na=False)].reset_index(drop=True)

        credits_aws1 = credits_aws[credits_aws.iloc[:,0].str.match(r'^\d{2}/\d{2}/\d{2}', na=False)].reset_index(drop=True)


        debits_aws = debits_aws1[['date', 'description', 'amount']]
        debits_aws['amount'] = debits_aws['amount'].str.replace(r'[-,]', '', regex=True)
        debits_aws['amount'] = debits_aws['amount'].str.strip()
        debits_aws['amount'] = pd.to_numeric(debits_aws['amount'])

        credits_aws = credits_aws1[['date', 'description', 'amount']]
        credits_aws['amount'] = credits_aws['amount'].str.strip()
        credits_aws['amount'] = credits_aws['amount'].str.replace(r'[-,]', '', regex=True) 
        credits_aws['amount'] = pd.to_numeric(credits_aws['amount'])

        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")
        
    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)


@app.route('/capitalone', methods=['POST'])
def excel_capitalone():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'([A-Z][a-z]{2}[ ]+\d{1,2})([\s]+[A-Z][a-z]{2}[ ]+\d{1,2}[\s]+)([A-Za-z0-9\"\'\;\:\#\@\&\*\/\-\.\ ]+)([\s]+)[-]\s[$]([0-9,]+[.][0-9]{2})\s'
        db_pattern = r'([A-Z][a-z]{2}[ ]+\d{1,2})([\s]+[A-Z][a-z]{2}[ ]+\d{1,2}[\s]+)([A-Za-z0-9\"\'\;\:\#\@\&\*\/\-\.\ ]+)([\s]+)[$]([0-9,]+[.][0-9]{2})\s'

        credits = []
        debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1)
        user = match.group(3)
        credit = match.group(5)
        credits.append({
            "date": date,
            "description": user,
            "credit": credit
        })


        for match in re.finditer(db_pattern, text):
            date = match.group(1)
            user = match.group(3)
            debit = match.group(5)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })

        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)
        credits['credit'] = credits['credit'].apply(clean_amount)

        # print(credits)

        debits = pd.DataFrame(debits)
        debits['debit'] = debits['debit'].apply(clean_amount)

        # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
            debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

            for cell in worksheet2['C'][1:]:
                cell.number_format = '##0.00'
        
        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("CapitalOne_page_"+str(i+1)+".png", "PNG")
            files.append("CapitalOne_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                    if "Credits" in table_title.text:
                        df=table[0].to_pandas()
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)

                    if "Transactions" in table_title.text:
                        df=table[0].to_pandas()
                        debits_aws = pd.concat([debits_aws, df], ignore_index=True)

                    if "Fees" in table_title.text:
                        df=table[0].to_pandas()
                        debits_aws = pd.concat([debits_aws, df], ignore_index=True)

                    if "Interests Charged" in table_title.text:
                        df=table[0].to_pandas()
                        debits_aws = pd.concat([debits_aws, df], ignore_index=True)

        df = debits_aws

        df1 = df[df.iloc[:,0].str.match(r'^[A-z]{3} \d{1,2}', na=False)].reset_index(drop=True)

        new_df = df1[[0, 2, 3]].rename(columns={0: "date", 2: "description", 3: "amount"})

        for i in range(len(new_df)):
            date = new_df.iloc[i, 0].strip()
            date_object = datetime.strptime(date, "%b %d")
            new_df.iloc[i, 0] = date_object.strftime("%m/%d")

        new_df['amount'] = new_df['amount'].str.replace(r'[$,]', '', regex=True)
        new_df['amount'] = pd.to_numeric(new_df['amount'])

        debits_aws = new_df

        df = credits_aws

        df1 = df[df.iloc[:,0].str.match(r'^[A-z]{3} \d{1,2}', na=False)].reset_index(drop=True)

        new_df = df1[[0, 2, 3]].rename(columns={0: "date", 2: "description", 3: "amount"})

        for i in range(len(new_df)):
            date = new_df.iloc[i, 0].strip()
            date_object = datetime.strptime(date, "%b %d")
            new_df.iloc[i, 0] = date_object.strftime("%m/%d")
    
        new_df['amount'] = new_df['amount'].str.replace(r'[$,]', '', regex=True)
        new_df['amount'] = pd.to_numeric(new_df['amount'])

        credits_aws = new_df

        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)

@app.route('/chase', methods=['POST'])
def excel_chase():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = (
            r'(\d{2}/\d{2})\n([A-Za-z0-9\"\'\/\\\;\:\,\&\#\*\-\s]+\.\D[A-Za-z0-9\"\'\/\\\;\:\,\&\#\*\-\s]+\.\D[A-Za-z0-9\"\'\/\\\;\:\,\&\#\*\-\s]+)\s[$]*([0-9,]+[.][0-9]{2})'
            r'|'
            r'(\d{2}/\d{2})\n([A-Za-z0-9\"\'\/\\\;\:\,\&\#\*\-\s]+\.\D[A-Za-z0-9\"\'\/\\\;\:\,\&\#\*\-\s]+)\s[$]*([0-9,]+[.][0-9]{2})'
            r'|'
            r'(\d{2}/\d{2})\n([A-Za-z0-9\"\'\/\\\;\:\,\&\#\*\-\s]+)\s[$]*([0-9,]+[.][0-9]{2})'
        )

        checks = r'(\d{4})\s[\^\*\s]*\s(A-Za-z0-9\s)*(\d{2}/\d{2})\s[$]*([0-9,]+[.][0-9]{2})'

        credits = []
        debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1) or match.group(4) or match.group(7)
            user = match.group(2) or match.group(5) or match.group(8)
            credit = match.group(3) or match.group(6) or match.group(9)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })


        # # for match in re.finditer(db_pattern, text):
        # #     date = match.group(1)
        # #     user = match.group(2)
        # #     debit = match.group(3)
        # #     debits.append({
        # #         "date": date,
        # #         "description": user,
        # #         "debit": debit
        # #     })

        for match in re.finditer(checks, text):
            date = match.group(3)
            user = match.group(1)
            debit = match.group(4)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })


        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)
        credits['credit'] = credits['credit'].apply(clean_amount)

        # print(credits)

        debits = pd.DataFrame(debits)
        debits['debit'] = debits['debit'].apply(clean_amount)

        # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
            debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

            for cell in worksheet2['C'][1:]:
                cell.number_format = '##0.00'
        
        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("Chase_page_"+str(i+1)+".png", "PNG")
            files.append("Chase_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                    if table_title.text.startswith('DEPOSIT'):
                        df=table[0].to_pandas()
                        if len(df.columns) > 3:
                            for i in range(2, len(df.columns)-1):
                                df[1] = df[1] + ' ' + df[i]
                        df1 = df[[0,1,len(df.columns)-1]].rename(columns={0: "date", 1: "description", len(df.columns)-1: "amount"})
                        credits_aws = pd.concat([credits_aws, df1], ignore_index=True)

                    if table_title.text in ['ATM & DEBIT CARD WITHDRAWALS', 'ELECTRONIC WITHDRAWALS', 'FEES']:
                        df=table[0].to_pandas()
                        # print(df)
                        if len(df.columns) > 3:
                            for i in range(2, len(df.columns)-1):
                                df[1] = df[1] + ' ' + df[i]
                        df1 = df[[0,1,len(df.columns)-1]].rename(columns={0: "date", 1: "description", len(df.columns)-1: "amount"})
                        debits_aws = pd.concat([debits_aws, df1], ignore_index=True)

        debits_aws = debits_aws[debits_aws.iloc[:,0].str.match(r'^\d{2}/\d{2}', na=False)].reset_index(drop=True)
        credits_aws = credits_aws[credits_aws.iloc[:,0].str.match(r'^\d{2}/\d{2}', na=False)].reset_index(drop=True)

        debits_aws['amount'] = debits_aws['amount'].str.replace(r'[$,]', '', regex=True)
        debits_aws['amount'] = pd.to_numeric(debits_aws['amount'])

        credits_aws['amount'] = credits_aws['amount'].str.replace(r'[$,]', '', regex=True)
        credits_aws['amount'] = pd.to_numeric(credits['amount'])
        
        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)


@app.route('/citi', methods=['POST'])
def excel_citi():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        # cr_pattern = r'(\d{2}/\d{2})\s([A-Za-z0-9\s\#]+)\s[-]([0-9,]+[.][0-9]{2})'
        db_pattern = r'(\d{2}/\d{2})\s([A-Za-z0-9\s\#]+)\s([0-9,]+[.][0-9]{2})'

        # credits = []
        debits = []

        # x = re.findall(db_pattern, text)
        # print(x)

        # for match in re.finditer(cr_pattern, text):
        #     date = match.group(1)
        #     user = match.group(2)
        #     credit = match.group(3)
        #     credits.append({
        #         "date": date,
        #         "description": user,
        #         "credit": credit
        #     })


        for match in re.finditer(db_pattern, text):
            date = match.group(1)
            user = match.group(2)
            debit = match.group(3)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })



        def clean_amount(amount):
            return float(amount.replace(',', ''))

        # credits = pd.DataFrame(credits)

        # credits['credit'] = credits['credit'].apply(clean_amount)

        # # print(credits)

        debits = pd.DataFrame(debits)

        debits['debit'] = debits['debit'].apply(clean_amount)

        # # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            # credits.to_excel(writer, sheet_name='Credit', index=False)
            debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            # worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            # for cell in worksheet1['C'][1:]:
            #     cell.number_format = '##0.00'

            for cell in worksheet2['C'][1:]:
                cell.number_format = '##0.00'

        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("Citi_page_"+str(i+1)+".png", "PNG")
            files.append("Citi_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()
        transactions = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                    if table_title.text in ['CHECKING ACTIVITY']:
                        df=table[0].to_pandas()
                        transactions = pd.concat([transactions, df], ignore_index=True)

        credits_aws = transactions[transactions.iloc[:,0].str.match(r'^\d{2}/\d{2}', na=False)].reset_index(drop=True)       

        # if len(debits_aws) > 0:
        #     debits = debits_aws[debits_aws.iloc[:,0].str.match(r'^\d{2}/\d{2}', na=False)].reset_index(drop=True)
        #     debits_aws = debits[[0,1,2]].rename(columns={0: "date", 1: "description", 2: "amount"})
        #     debits_aws['amount'] = debits_aws['amount'].str.replace(r'[$,]', '', regex=True)
        #     debits_aws['amount'] = pd.to_numeric(debits_aws['amount'])

        # if len(credits_aws) > 0:
        #     credits = credits_aws[credits_aws.iloc[:,0].str.match(r'^\d{2}/\d{2}', na=False)].reset_index(drop=True)
        #     credits_aws = credits[[0,1,3]].rename(columns={0: "date", 1: "description", 3: "amount"})
        #     credits_aws['amount'] = credits_aws['amount'].str.replace(r'[$,]', '', regex=True)
        #     credits_aws['amount'] = pd.to_numeric(credits['amount'])

        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            # debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            # worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)
        

@app.route('/citirewards', methods=['POST'])
def excel_citirewards():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'(\d{2}/\d{2})*\s(\d{2}/\d{2})\s([A-Za-z0-9\s\,\'\#\.\*\-]+)\s[-][$]([0-9,]+[.][0-9]{2})'
        db_pattern = r'(\d{2}/\d{2})*\s(\d{2}/\d{2})\s([A-Za-z0-9\s\,\'\#\.\*\-]+)\s[$]([0-9,]+[.][0-9]{2})'

        credits = []
        debits = []

        # x = re.findall(db_pattern, text)
        # print(x)

        for match in re.finditer(cr_pattern, text):
            date = match.group(2)
            user = match.group(3)
            credit = match.group(4)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
        })


        for match in re.finditer(db_pattern, text):
            date = match.group(2)
            user = match.group(3)
            debit = match.group(4)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })


        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)

        credits['credit'] = credits['credit'].apply(clean_amount)

        # print(credits)

        debits = pd.DataFrame(debits)

        debits['debit'] = debits['debit'].apply(clean_amount)

        # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
            debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

            for cell in worksheet2['C'][1:]:
                cell.number_format = '##0.00'
        
        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("CitiRewards_page_"+str(i+1)+".png", "PNG")
            files.append("CitiRewards_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                df=table[0].to_pandas()
                credits_aws = pd.concat([credits_aws, df], ignore_index=True)

        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )

    except Exception as e:
        print("An error occured: {e}")
        
    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)


@app.route('/hab', methods=['POST'])
def excel_hab():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        # images = convert_from_path(temp_path)
        # len_images = len(images)

        # with open('log.txt', 'w', encoding='utf-8') as f:
        #     for i in range(len_images):
        #         images[i].save('hab' + str(i) + '.jpg', 'JPEG')

        #         loader = AmazonTextractPDFLoader("hab" + str(i) + ".jpg")
        #         documents = loader.load()

        #         for document in documents:
        #             text = document.page_content
        #             f.write(text + '\n') 

        # with open("log.txt", "r") as f:
        #     text = f.read()

        # cr_pattern = r'\n(\d{2}/\d{2})\n\n\n([A-Za-z*]+[A-Za-z 0-9\*\/]+)\n\n\n([0-9,]+[.]+[0-9]+)\n'
        # db_pattern = r'\n(\d{2}/\d{2})\n\n\n([A-Za-z*]+[A-Za-z 0-9\/\*\~\ \\\~\|\.\&]+)\n\n\n([0-9,]+[.]+[0-9]+)[-][SC]*\n'
        # # x = re.findall(db_pattern, text)
        # # print(x)

        # credits = []
        # debits = []

        # for match in re.finditer(cr_pattern, text):
        #     date = match.group(1)
        #     user = match.group(2)
        #     credit = match.group(3)
        #     credits.append({
        #         "date": date,
        #         "description": user,
        #         "credit": credit
        #     })

        # for match in re.finditer(db_pattern, text):
        #     date = match.group(1)
        #     user = match.group(2)
        #     debit = match.group(3)
        #     debits.append({
        #         "date": date,
        #         "description": user,
        #         "debit": debit
        #     })

        # def clean_amount(amount):
        #     return float(amount.replace(',', ''))

        # credits = pd.DataFrame(credits)

        # credits['credit'] = credits['credit'].apply(clean_amount)

        # # print(credits)

        # debits = pd.DataFrame(debits)

        # debits['debit'] = debits['debit'].apply(clean_amount)

        # # print(debits)

        # with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
        #     credits.to_excel(writer, sheet_name='Credit', index=False)
        #     debits.to_excel(writer, sheet_name='Debit', index=False)

        #     workbook1 = writer.book
        #     worksheet1 = writer.sheets['Credit']
        #     worksheet2 = writer.sheets['Debit']

        #     for cell in worksheet1['C'][1:]:
        #         cell.number_format = '##0.00'

        #     for cell in worksheet2['C'][1:]:
        #         cell.number_format = '##0.00'

        # temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        # workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("Hab_page_"+str(i+1)+".png", "PNG")
            files.append("Hab_page_"+str(i+1)+".png")

        transactions = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                df=table[0].to_pandas()
                df1 = df[df.iloc[:,0].str.match(r'^\d{2}/\d{1,2}.*', na=False)].reset_index(drop=True)
                for i in range(len(df1)):
                    j = -1
                    while df1.iloc[i, -1] == '':
                        df1.iloc[i, -1] = df1.iloc[i, j-1]
                        j -= 1
                df = df1[[0, 1, len(df1.columns)-1]].rename(columns={0: "date", 1: "description", len(df1.columns)-1: "amount"})
                transactions = pd.concat([transactions, df], ignore_index=True)

    
        credit_list = []
        debit_list = []

        for i in range(len(transactions)):
            amount = transactions.iloc[i,-1]
            if '-' in amount:
                debit_list.append(transactions.iloc[i])
            else:
                credit_list.append(transactions.iloc[i])

        credits_aws = pd.DataFrame(credit_list)
        debits_aws = pd.DataFrame(debit_list)

        debits_aws['amount'] = debits_aws['amount'].astype(str).replace(r'[-,]', '', regex=True)
        debits_aws['amount'] = pd.to_numeric(debits_aws['amount'])

        credits_aws['amount'] = credits_aws['amount'].astype(str).str.replace(r'[,]', '', regex=True)
        credits_aws['amount'] = pd.to_numeric(credits_aws['amount'])
                                      
        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        # excel1_buffer = io.BytesIO()
        # workbook1.save(excel1_buffer)
        # excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )

    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        # os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)

@app.route('/pnc', methods=['POST'])
def excel_pnc():
    return 0

@app.route('/regions', methods=['POST'])
def excel_regions():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'(\d{2}/\d{2})\s([A-Za-z 0-9\#\-]+)\s([0-9,]+[.]+[0-9]{2}\s)'
        # db_pattern = r'(\d{2}/\d{2})\s([A-Za-z 0-9\#]+)\s([-][0-9,]+[.]+[0-9]{2}\s)'
        # x = re.findall(cr_pattern, text)
        # print(x)

        credits = []
        # debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1)
            user = match.group(2)
            credit = match.group(3)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        # for match in re.finditer(db_pattern, text):
        #     date = match.group(1)
        #     user = match.group(2)
        #     debit = match.group(3)
        #     debits.append({
        #         "date": date,
        #         "description": user,
        #         "debit": debit
        #     })

        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)

        credits['credit'] = credits['credit'].apply(clean_amount)

        # print(credits)

        # debits = pd.DataFrame(debits)

        # debits['debit'] = debits['debit'].apply(clean_amount)

        # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
            # debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
            # worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

            # for cell in worksheet2['C'][1:]:
                # cell.number_format = '##0.00'

        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("Regions_page_"+str(i+1)+".png", "PNG")   
            files.append("Regions_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        # debits_aws = pd.DataFrame()

        for f in files:
            image = Image.open(f)
            extractor = Textractor(region_name="us-east-1")
            response = extractor.analyze_document(
                file_source=image,
                features=[
                TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                df=table[0].to_pandas()
                transactions = pd.concat([transactions, df], ignore_index=True)

        credits_aws = transactions[transactions.iloc[:,0].str.match(r'^\d{2}/\d{1,2}.*', na=False)].reset_index(drop=True)
        credits_aws = credits_aws[~credits_aws.iloc[:,1].str.match(r'^\d', na=False)].reset_index(drop=True)
        # credits_aws = debits[[0,1,2]] 
        # filtered_transactions = debits_aws[~debits_aws.iloc[:, 1].str.match(r'^\d', na=False)]
        # debits_aws = filtered_transactions


        # if len(debits_aws) > 0:
        #     # debits_aws = debits_aws[debits_aws.iloc[:,0].str.match(r'^\d{2}/\d{1,2}.*', na=False)].reset_index(drop=True)
        #     # debits_aws = debits_aws[[0,1,2]].rename(columns={0: "date", 1: "description", 2: "debits"}, inplace=True)
        #     debits_aws['debits'] = debits_aws['debits'].astype(str).replace(r'[,]', '', regex=True)
        #     debits_aws['debits'] = pd.to_numeric(debits_aws['debits'])

        # # if len(credits_aws) > 0:
        # #     credits_aws = credits_aws[credits_aws.iloc[:,0].str.match(r'^\d{2}/\d{1,2}.*', na=False)].reset_index(drop=True)
        # #     credits_aws.rename(columns={0: "date", 1: "description", 2: "credits"}, inplace=True)
        # #     credits_aws['credits'] = credits_aws['credits'].astype(str).replace(r'[,]', '', regex=True)
        # #     credits_aws['credits'] = pd.to_numeric(credits_aws['credits'])

        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            # debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            # worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)

@app.route('/santander', methods=['POST'])
def excel_santander():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'(\d{2}-\d{2})\s([A-Za-z][A-Za-z0-9\*\/\.\-\s]+)\n[$]([0-9,]+[.]+[0-9]{2})\s[$][0-9,]+[.]+[0-9]{2}\s'

        # x = re.findall(cr_pattern, text)
        # print(x)

        credits = []
        # # debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1)
            user = match.group(2)
            credit = match.group(3)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        # # for match in re.finditer(db_pattern, text):
        # #     date = match.group(1)
        # #     user = match.group(2)
        # #     debit = match.group(3)
        # #     debits.append({
        # #         "date": date,
        # #         "description": user,
        # #         "debit": debit
        # #     })

        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)
        # print(credits)

        credits['credit'] = credits['credit'].apply(clean_amount)

        # # print(credits)

        # debits = pd.DataFrame(debits)

        # debits['debit'] = debits['debit'].apply(clean_amount)

        # # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
        #     debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
        #     worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

        #     for cell in worksheet2['C'][1:]:
    #         cell.number_format = '##0.00'

        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        # Send the file as response
        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("Santander_page_"+str(i+1)+".png", "PNG")
            files.append("Santander_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()
        transactions = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                    if table_title.text.startswith('Account Activity'):
                        df=table[0].to_pandas()
                        # df1 = df[[0,1,2,3]]
                        transactions = pd.concat([transactions, df], ignore_index=True)

        transactions[['date', 'description']] = df[0].str.split(' ', n=1, expand=True)
        transactions = transactions[['date','description',1,2]].rename(columns={1: "credit", 2: "debit"})
        transactions = transactions[transactions.iloc[:,0].str.match(r'^\d{2}-\d{1,2}.*', na=False)].reset_index(drop=True)
        transactions['date'] = transactions['date'].str.replace('-', '/')

        credit_list = []
        debit_list = []

        for i in range(len(transactions)):
            if transactions.iloc[i, 2] == '':
                debit_list.append(transactions.iloc[i])

            else:
                credit_list.append(transactions.iloc[i])

        credits_aws = pd.DataFrame(credit_list)
        debits_aws = pd.DataFrame(debit_list)

        credits_aws['credit'] = credits_aws['credit'].str.replace(r'[$,]', '', regex=True)
        credits_aws['credit'] = pd.to_numeric(credits_aws['credit'])

        debits_aws['debit'] = debits_aws['debit'].str.replace(r'[$,]', '', regex=True)
        debits_aws['debit'] = pd.to_numeric(debits_aws['debit'])

        credits_aws.drop(columns='debit', inplace=True)
        debits_aws.drop(columns='credit', inplace=True)

        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)

@app.route('/seacoast', methods=['POST'])
def excel_seacoast():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        # images = convert_from_path(temp_path)
        # len_images = len(images)
        # logfiles = []

        # with open('log.txt', 'w', encoding='utf-8') as f:
        #     for i in range(len_images):
        #         images[i].save('seacoast' + str(i) + '.jpg', 'JPEG')
        #         logfiles.append("Seacoast_page_"+str(i+1)+".png")

        #         loader = AmazonTextractPDFLoader("seacoast" + str(i) + ".jpg")
        #         documents = loader.load()

        #         for document in documents:
        #             text = document.page_content
        #             f.write(text + '\n') 

        # with open("log.txt", "r") as f:
        #     text = f.read()

        # cr_pattern = r'\n(\d{2}-\d{2})\n\n\n([A-Za-z\*\#]+[A-Za-z 0-9\*\/\#]+)\n\n\n([0-9,]+[.]+[0-9]+)\n\n\n[^-]'
        # db_pattern = r'\n(\d{2}-\d{2})\n\n\n([A-Za-z\*\#]+[A-Za-z 0-9\*\/\#]+)\n\n\n([-][0-9,]+[.]+[0-9]+)\n'

        # # x = re.findall(cr_pattern, text)
        # # print(x)

        # credits = []
        # debits = []

        # for match in re.finditer(cr_pattern, text):
        #     date = match.group(1)
        #     user = match.group(2)
        #     credit = match.group(3)
        #     credits.append({
        #         "date": date,
        #         "description": user,
        #         "credit": credit
        #     })

        # for match in re.finditer(db_pattern, text):
        #     date = match.group(1)
        #     user = match.group(2)
        #     debit = match.group(3)
        #     debits.append({
        #         "date": date,
        #         "description": user,
        #         "debit": debit
        #     })

        # def clean_amount(amount):
        #             return float(amount.replace(',', ''))

        # def sign(amount):
        #             return amount.replace('-', '')

        # def date_modify(dates):
        #             return dates.replace('-', '/')

        # credits = pd.DataFrame(credits)

        # credits['date'] = credits['date'].apply(date_modify)

        # credits['credit'] = credits['credit'].apply(clean_amount)

        #         # print(credits)

        # debits = pd.DataFrame(debits)

        # debits['date'] = debits['date'].apply(date_modify)

        # debits['debit'] = debits['debit'].apply(sign)

        # debits['debit'] = debits['debit'].apply(clean_amount)

        # # print(debits)

        # with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
        #     credits.to_excel(writer, sheet_name='Credit', index=False)
        #     debits.to_excel(writer, sheet_name='Debit', index=False)

        #     workbook1 = writer.book
        #     worksheet1 = writer.sheets['Credit']
        #     worksheet2 = writer.sheets['Debit']

        #     for cell in worksheet1['C'][1:]:
        #         cell.number_format = '##0.00'

        #     for cell in worksheet2['C'][1:]:
        #         cell.number_format = '##0.00'
        
        # temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        # workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []

        for i in range(len(pages)):
            pages[i].save("Seacoast_page_"+str(i+1)+".png", "PNG")
            files.append("Seacoast_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()
        transactions = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                    if table_title.text in ['Business Checking*', 'Business Checking']:
                        df=table[0].to_pandas()
                        transactions = pd.concat([transactions, df], ignore_index=True)

        transactions = transactions[transactions.iloc[:,0].str.match(r'^\d{2}-\d{1,2}.*', na=False)].reset_index(drop=True)
        transactions = transactions[[0,1,2,3]].rename(columns={0:'date', 1: 'description', 2:'credit', 3:'debit'})
        transactions['date'] = transactions['date'].str.replace(r'[-,]', '/', regex=True)
        transactions['credit'] = transactions['credit'].str.replace(r'[$,]', '', regex=True)
        transactions['debit'] = transactions['debit'].str.replace(r'[-$,]', '', regex=True)

        credit_list = []
        debit_list = []

        for i in range(len(transactions)):
                    if transactions.iloc[i, 2] == '':
                        debit_list.append(transactions.iloc[i])

                    if transactions.iloc[i, 3] == '':
                        credit_list.append(transactions.iloc[i])

        credits = pd.DataFrame(credit_list)
        debits = pd.DataFrame(debit_list)

        credits_aws = credits[credits['credit'] != '']
        debits_aws = debits[debits['debit'] != '']

        for index in credits_aws.index:
                    val = credits_aws.loc[index, 'credit'].split(' ')
                    credits_aws.loc[index, 'credit'] = val[0]  

        for index in debits_aws.index:
                    val = debits_aws.loc[index, 'debit'].split(' ')
                    debits_aws.loc[index, 'debit'] = val[0]

        credits_aws.drop(columns='debit', inplace=True)
        debits_aws.drop(columns='credit', inplace=True)
            
        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        # excel1_buffer = io.BytesIO()
        # workbook1.save(excel1_buffer)
        # excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )

    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        # os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)
        # for l in logfiles:
        #     os.remove(l)

    
@app.route('/synovus', methods=['POST'])
def excel_synovus():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'(\d{2}-\d{2})\sPreauthorized Credit\s([A-Za-z 0-9\#]+\s+[A-Za-z 0-9]*)\s([0-9,]+[.]+[0-9]{2})\s'

        db_pattern = r'(\d{2}-\d{2})\sPreauthorized Wd\s([A-Za-z 0-9\#\&]+\s+[A-Za-z 0-9]*)\s([0-9,]+[.]+[0-9]{2})\s'

        # x = re.findall(pattern, text)
        # print(x)

        credits = []
        debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1)
            user = match.group(2)
            credit = match.group(3)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        for match in re.finditer(db_pattern, text):
            date = match.group(1)
            user = match.group(2)
            debit = match.group(3)
            debits.append({
                "date": date,
                "description": user,
                "debit": debit
            })

        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)
        credits['credit'] = credits['credit'].apply(clean_amount)

        # print(credits)

        debits = pd.DataFrame(debits)
        debits['debit'] = debits['debit'].apply(clean_amount)

        # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
            debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

            for cell in worksheet2['C'][1:]:
                cell.number_format = '##0.00'
        
        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("Synovus_page_"+str(i+1)+".png", "PNG")
            files.append("Synovus_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()
        transactions = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                        TextractFeatures.TABLES
                    ],
                    save_image=True
                )
            
            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                df = table[0].to_pandas()
                transactions = pd.concat([transactions, df], ignore_index=True)


        transactions = transactions[transactions.iloc[:,0].str.match(r'^\d{2}-\d{1,2}.*', na=False)].reset_index(drop=True)
        transactions = transactions[transactions.iloc[:,1].str.match(r'^[A-Za-a]', na=False)].reset_index(drop=True)

        for i in range(len(transactions)):
            if pd.isna(transactions.iloc[i, -1]):
                transactions.iloc[i, -1] = transactions.iloc[i, transactions.iloc[i].last_valid_index()]

        new_df = transactions[[0,1,2,len(transactions.columns)-1]].rename(columns={0: "date", 1: "type", 2: "description", len(transactions.columns)-1: "amount"})
        new_df['date'] = new_df['date'].str.replace('-', '/')
        
        debits = ['Preauthorized Wd']
        credits = ['Preauthorized Credit']

        for i in range(len(new_df)):
            if new_df.iloc[i, 1].strip() in debits:
                row = pd.DataFrame(new_df.iloc[i])
                debits_aws = pd.concat([debits_aws, row.T], ignore_index=True)
            if new_df.iloc[i, 1].strip() in credits:
                row = pd.DataFrame(new_df.iloc[i])
                credits_aws = pd.concat([credits_aws, row.T], ignore_index=True)

        
        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)


@app.route('/tdbank', methods=['POST'])
def excel_tdbank():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'(\d{2}/\d{2})\s([A-Za-z 0-9\#\-\,\*\.\s]+)\s([0-9,]+[.]+[0-9]{2}\s)'
        # db_pattern = r'(\d{2}/\d{2})\s([A-Za-z 0-9\#]+)\s([-][0-9,]+[.]+[0-9]{2}\s)'

        credits = []
        # debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1)
            user = match.group(2)
            credit = match.group(3)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        # for match in re.finditer(db_pattern, text):
        #     date = match.group(1)
        #     user = match.group(2)
        #     debit = match.group(3)
        #     debits.append({
        #         "date": date,
        #         "description": user,
        #         "debit": debit
        #     })

        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)

        credits['credit'] = credits['credit'].apply(clean_amount)

        # # print(credits)

        # debits = pd.DataFrame(debits)

        # debits['debit'] = debits['debit'].apply(clean_amount)

        # # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
        #     debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
        #     worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

        #     for cell in worksheet2['C'][1:]:
        #         cell.number_format = '##0.00'

        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("TD_page_"+str(i+1)+".png", "PNG")
            files.append("TD_page_"+str(i+1)+".png")


        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="ap-south-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                    if table_title.text in ['DAILY ACCOUNT ACTIVITY', 'DEPOSIT']:
                        df=table[0].to_pandas()
                        df1 = df[[0,1, len(df.columns)-1]].rename(columns={0: "Date", 1: "Description",  len(df.columns)-1: "Credits"})
                        credits_aws = pd.concat([credits_aws, df1], ignore_index=True)

                    if table_title.text in ['Electronic Payments', 'DAILY ACCOUNT ACTIVITY Electronic Payments (continued)', 'Electronic Payments (continued)', 'Other Withdrawals', 'Service Charges']:
                        df=table[0].to_pandas()
                        df1 = df[[0,1, len(df.columns)-1]].rename(columns={0: "Date", 1: "Description",  len(df.columns)-1: "Debits"})
                        debits_aws = pd.concat([debits_aws, df1], ignore_index=True)

        credits_aws = credits_aws[credits_aws.iloc[:,0].str.match(r'^\d{2}/\d{2}.*', na=False)].reset_index(drop=True)
        debits_aws = debits_aws[debits_aws.iloc[:,0].str.match(r'^\d{2}/\d{2}.*', na=False)].reset_index(drop=True)

        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)
        

@app.route('/wellsfargo', methods=['POST'])
def excel_wellsfargo():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    
    temp_path = tempfile.mktemp(suffix='.pdf')
    uploaded_file.save(temp_path)

    try:
        doc = pymupdf.open(temp_path)
        with open('log.txt', 'w', encoding='utf-8') as f:
            for page in doc:
                text = page.get_text()
                f.write(text + '\n')

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'\s(\d{1,2}/\d{1,2})\s+[< ]*([A-Za-z0-9\s\*\-\\\/\#\~]+)\s+([0-9,]+[.]+[0-9]{2})\s'
        # db_pattern = r'(\d{2}/\d{2})\s([A-Za-z 0-9\#]+)\s([-][0-9,]+[.]+[0-9]{2}\s)'

        # x = re.findall(cr_pattern, text)
        # print(x)

        credits = []
        # debits = []

        for match in re.finditer(cr_pattern, text):
            date = match.group(1)
            user = match.group(2)
            credit = match.group(3)
            credits.append({
                "date": date,
                "description": user,
                "credit": credit
            })

        # for match in re.finditer(db_pattern, text):
        #     date = match.group(1)
        #     user = match.group(2)
        #     debit = match.group(3)
        #     debits.append({
        #         "date": date,
        #         "description": user,
        #         "debit": debit
        #     })

        def clean_amount(amount):
            return float(amount.replace(',', ''))

        credits = pd.DataFrame(credits)
        # print(credits)

        credits['credit'] = credits['credit'].apply(clean_amount)

        # # print(credits)

        # debits = pd.DataFrame(debits)

        # debits['debit'] = debits['debit'].apply(clean_amount)

        # # print(debits)

        with pd.ExcelWriter('excel1.xlsx', engine='openpyxl') as writer:
            credits.to_excel(writer, sheet_name='Credit', index=False)
        #     debits.to_excel(writer, sheet_name='Debit', index=False)

            workbook1 = writer.book
            worksheet1 = writer.sheets['Credit']
        #     worksheet2 = writer.sheets['Debit']

            for cell in worksheet1['C'][1:]:
                cell.number_format = '##0.00'

        #     for cell in worksheet2['C'][1:]:
        #         cell.number_format = '##0.00'
        temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        workbook1.save(temp_excel.name)

        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("WellsFargo_page_"+str(i+1)+".png", "PNG")
            files.append("WellsFargo_page_"+str(i+1)+".png")

        transactions = pd.DataFrame()
        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()

        for f in files:
            image = Image.open(f) # loads the document image with Pillow
            extractor = Textractor(region_name="us-east-1") # Initialize textractor client, modify region if required
            response = extractor.analyze_document(
                file_source=image,
                features=[
                    TextractFeatures.TABLES
                ],
                save_image=True
            )

            for i in range(len(response.tables)):
                table = EntityList(response.tables[i])
                response.tables[i].visualize()
                table_title = table[0].title
                if table_title:
                # print(table_title.text)
                    if "Transaction history" in table_title.text:
                        df=table[0].to_pandas()
                        transactions = pd.concat([transactions, df], ignore_index=True)
            
        df1 = transactions[transactions.iloc[:,0].str.match(r'^\d{2}/\d{1,2}.*', na=False)].reset_index(drop=True)

        df1.drop(df1.columns[5], axis=1, inplace=True)
        df1.drop(df1.columns[1], axis=1, inplace=True)

        new_df = df1[[0,2,3,4]].rename(columns={df.columns[0]: "Date", df.columns[2]: "Description", df.columns[3]: "Credits", df.columns[4]: "Debits"})

        credit_list = []
        debit_list = []

        for i in range(len(new_df)):
            if new_df.iloc[i, 2] == '':
                debit_list.append(new_df.iloc[i])

            else:
                credit_list.append(new_df.iloc[i])

        credits_aws = pd.DataFrame(credit_list)
        debits_aws = pd.DataFrame(debit_list)

        credits_aws.drop(columns='Debits', inplace=True)
        debits_aws.drop(columns='Credits', inplace=True)

        with pd.ExcelWriter('excel2.xlsx', engine='openpyxl') as writer:
            credits_aws.to_excel(writer, sheet_name='Credit', index=False)
            debits_aws.to_excel(writer, sheet_name='Debit', index=False)

            workbook2 = writer.book
            worksheet1 = writer.sheets['Credit']
            worksheet2 = writer.sheets['Debit']

            temp_excel2 = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
            workbook2.save(temp_excel2.name)

        excel1_buffer = io.BytesIO()
        workbook1.save(excel1_buffer)
        excel1_buffer.seek(0)
        
        excel2_buffer = io.BytesIO()
        workbook2.save(excel2_buffer)
        excel2_buffer.seek(0)
        
        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('regex.xlsx', excel1_buffer.getvalue())
            zip_file.writestr('textract.xlsx', excel2_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        # Send the zip file
        return send_file(
            zip_buffer, 
            mimetype='application/zip',
            as_attachment=True,
            download_name='excel_exports.zip'
        )
    
    except Exception as e:
        print("An error occured: {e}")

    finally:
        os.remove(temp_path)
        os.remove('excel1.xlsx')
        os.remove('excel2.xlsx')
        for f in files:
            os.remove(f)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9595, debug=True)  # Enable debug mode for development