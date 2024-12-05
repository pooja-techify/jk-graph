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
from pdf2image import convert_from_path
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
        
        print("Starting textract")
        pages = convert_from_path(temp_path, dpi=300)

        files = []
        for i in range(len(pages)):
            pages[i].save("Amex_page_"+str(i+1)+".png", "PNG")
            files.append("Amex_page_"+str(i+1)+".png")

        credits_aws = pd.DataFrame()
        debits_aws = pd.DataFrame()

        for f in files:
            print("New Page")
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
                    print(table_title)
                    if 'Detail' in table_title.text:
                        df=table[0].to_pandas()
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)
                    if 'Interest Charged' in table_title.text:
                        df=table[0].to_pandas()
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)

        # df = credits_aws

        #df1 = df[df.iloc[:,0].str.match(r'^\d{2}/\d{2}', na=False)].reset_index(drop=True)

        #df1.iloc[:, 0] = df1.iloc[:, 0].str.strip()

        #for i in range(len(df1)):
         #   if pd.isna(df1.iloc[i, -1]):
         #       df1.iloc[i, -1] = df1.iloc[i, df1.iloc[i].last_valid_index()]

        #for i in range(len(df1)):
         #   if df1.iloc[i,0][-1] == '*':
         #       df1.iloc[i,0] = df1.iloc[i,0][:-1]
         #   if re.fullmatch(r'\d{2}/\d{2}/\d{2}.+', str(df1.iloc[i, 0])):
         #       df1.iloc[i, 0] = df1.iloc[i, 0][0:8]
         #       df1.iloc[i, 1] = df1.iloc[i, 1][8:]

        #new_df = df1[[0, 1, 4]].rename(columns={0: "date", 1: "description", 4: "amount"})

        #Clean up the amount column
        #new_df['amount'] = new_df['amount'].str.replace(r'[$,]', '', regex=True)
        #new_df['amount'] = pd.to_numeric(new_df['amount'])


        #credits_aws = new_df[new_df['amount']<0]
        #credits_aws['amount'] = credits_aws['amount'].astype(str).replace(r'[-,]', '', regex=True)
        #credits_aws['amount'] = pd.to_numeric(credits_aws['amount'])

        #debits_aws = new_df[new_df['amount']>0]


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

        # zip_buffer = io.BytesIO()

        # with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        #     zip_file.write(temp_excel.name, 'regex.xlsx')
        #     zip_file.write(temp_excel2.name, 'textract.xlsx')
            
        #     zip_buffer.seek(0)

        # return send_file(
        #     zip_buffer,
        #     mimetype='application/zip',
        #     as_attachment=True,
        #     download_name='converted_files.zip'
        # )

    except Exception as e:
        print("An error occured: {e}")
        
    finally:
        print("Final block")
        os.remove(temp_path)
       # os.remove(temp_excel)
       # os.remove(temp_excel2)
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
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)

        # df = credits

        # df1 = df[df.iloc[:,0].str.match(r'^\d{2}/\d{2}.*', na=False)].reset_index(drop=True)

        #df1[['date', 'description']] = df1[0].str.split(' ', n=1, expand=True)

        #new_df = df1[['date','description', 1, 2]].rename(columns={1: "debit", 2: "credit"})

        #credit_list = []
        #debit_list = []

        #for i in range(len(new_df)):
         #   if pd.isna(new_df.iloc[i, -1]):
          #      debit_list.append(new_df.iloc[i])

           # if pd.isna(new_df.iloc[i, -2]):
            #    credit_list.append(new_df.iloc[i])

        #credits_aws = pd.DataFrame(credit_list)[['date', 'description', 'credit']]
        #debits_aws = pd.DataFrame(debit_list)[['date', 'description', 'debit']]

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
        #os.remove(temp_excel)
        #os.remove(temp_excel2)
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
                print(table_title.text)
                if "Deposits" in table_title.text:
                    df=table[0].to_pandas()
                    credits_aws = pd.concat([credits_aws, df], ignore_index=True)

                if "Withdrawals" in table_title.text:
                    df=table[0].to_pandas()
                    debits_aws = pd.concat([debits_aws, df], ignore_index=True)

                if "Checks" in table_title.text:
                    df=table[0].to_pandas()
                    debits_aws = pd.concat([debits_aws, df], ignore_index=True)

        # df = debits_aws

        # df1 = df[df.iloc[:,0].str.match(r'^\d{2}/\d{2}/\d{2}', na=False)].reset_index(drop=True)

        # new_df = df1.rename(columns={0: "date", 1: "description", len(df1.columns)-1: "amount"})
        # if len(df1.columns) > 3:
        #     ori_columns = df1.columns
        #     for i in range(2, len(df1.columns)-1):
        #         new_df['description'] = new_df['description'].astype(str) + ' ' + new_df[ori_columns[i]].astype(str)

        # new_df = new_df[['date', 'description', 'amount']]
        # new_df['amount'] = new_df['amount'].str.replace(r'[-,]', '', regex=True)
        # new_df['amount'] = pd.to_numeric(new_df['amount'])

        # debits = new_df

        # df = credits_aws

        # df1 = df[df.iloc[:,0].str.match(r'^\d{2}/\d{2}/\d{2}', na=False)].reset_index(drop=True)

        # new_df = df1.rename(columns={0: "date", 1: "description", len(df1.columns)-1: "amount"})
                            
        # credits = new_df

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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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

        # df = debits_aws

        # df1 = df[df.iloc[:,0].str.match(r'^[A-z]{3} \d{1,2}', na=False)].reset_index(drop=True)

        # new_df = df1[[0, 2, 3]].rename(columns={0: "date", 2: "description", 3: "amount"})

        # new_df['amount'] = new_df['amount'].str.replace(r'[$,]', '', regex=True)
        # new_df['amount'] = pd.to_numeric(new_df['amount'])

        # debit = new_df

        # df = credits_aws

        # df1 = df[df.iloc[:,0].str.match(r'^[A-z]{3} \d{1,2}', na=False)].reset_index(drop=True)

        # df1 = df[df.iloc[:,0].str.match(r'^[A-z]{3} \d{1,2}', na=False)].reset_index(drop=True)

        # new_df = df1[[0, 2, 3]].rename(columns={0: "date", 2: "description", 3: "amount"})

        # new_df['amount'] = new_df['amount'].str.replace(r'[$,]', '', regex=True)
        # new_df['amount'] = pd.to_numeric(new_df['amount'])

        # credit = new_df


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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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

                if table_title.text.startswith('DEPOSIT'):
                    df=table[0].to_pandas()
                    if len(df.columns) > 3:
                        for i in range(2, len(df.columns)-1):
                            df[1] = df[1] + ' ' + df[i]
                        df1 = df[[0,1,len(df.columns)-1]].rename(columns={0: "date", 1: "description", len(df.columns)-1: "amount"})
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)

                if table_title.text in ['ATM & DEBIT CARD WITHDRAWALS', 'ELECTRONIC WITHDRAWALS', 'FEES']:
                    df=table[0].to_pandas()
                    # print(df)
                    if len(df.columns) > 3:
                        for i in range(2, len(df.columns)-1):
                            df[1] = df[1] + ' ' + df[i]
                        df1 = df[[0,1,len(df.columns)-1]].rename(columns={0: "date", 1: "description", len(df.columns)-1: "amount"})
                        debits_aws = pd.concat([debits_aws, df1], ignore_index=True)

        # debits['amount'] = debits['amount'].str.replace(r'[$,]', '', regex=True)
        # debits['amount'] = pd.to_numeric(debits['amount'])

        # credits['amount'] = credits['amount'].str.replace(r'[$,]', '', regex=True)
        # credits['amount'] = pd.to_numeric(credits['amount'])

        # debits_aws = debits[debits.iloc[:,0].str.match(r'^\d{2}/\d{2}.*', na=False)].reset_index(drop=True)
        # credits_aws = credits[debits.iloc[:,0].str.match(r'^\d{2}/\d{2}.*', na=False)].reset_index(drop=True)

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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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
        images = convert_from_path(temp_path)
        len_images = len(images)

        with open('log.txt', 'w', encoding='utf-8') as f:
            for i in range(len_images):
                images[i].save('hab' + str(i) + '.jpg', 'JPEG')

                loader = AmazonTextractPDFLoader("hab" + str(i) + ".jpg")
                documents = loader.load()

                for document in documents:
                    text = document.page_content
                    f.write(text + '\n') 

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'\n(\d{2}/\d{2})\n\n\n([A-Za-z*]+[A-Za-z 0-9\*\/]+)\n\n\n([0-9,]+[.]+[0-9]+)\n'
        db_pattern = r'\n(\d{2}/\d{2})\n\n\n([A-Za-z*]+[A-Za-z 0-9\/\*\~\ \\\~\|\.\&]+)\n\n\n([0-9,]+[.]+[0-9]+)[-][SC]*\n'
        # x = re.findall(db_pattern, text)
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
            pages[i].save("Hab_page_"+str(i+1)+".png", "PNG")
            files.append("Hab_page_"+str(i+1)+".png")

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
                if table_title.text in ['Deposits and Credits', 'DEPOSIT']:
                    df=table[0].to_pandas()
                    credits_aws = pd.concat([credits_aws, df], ignore_index=True)

                if table_title.text in ['Debit(s)', 'DAILY ACCOUNT ACTIVITY Electronic Payments (continued)', 'Electronic Payments (continued)', 'Other Withdrawals', 'Service Charges']:
                    df=table[0].to_pandas()
                    debits_aws = pd.concat([debits_aws, df], ignore_index=True)

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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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
        debits_aws = pd.DataFrame()

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
                table_title = table[0].title
                if table_title.text in ['DEPOSITS & CREDITS', 'AUTOMATIC TRANSFERS']:
                    df=table[0].to_pandas()
                    credits_aws = pd.concat([credits_aws, df], ignore_index=True)

                if table_title.text in ['WITHDRAWALS', 'FEES', 'CHECKS']:
                    df=table[0].to_pandas()
                    debits_aws = pd.concat([debits_aws, df], ignore_index=True)

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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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
                        credits_aws = pd.concat([credits, df], ignore_index=True)

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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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
        images = convert_from_path(temp_path)
        len_images = len(images)

        with open('log.txt', 'w', encoding='utf-8') as f:
            for i in range(len_images):
                images[i].save('seacoast' + str(i) + '.jpg', 'JPEG')

                loader = AmazonTextractPDFLoader("seacoast" + str(i) + ".jpg")
                documents = loader.load()

                for document in documents:
                    text = document.page_content
                    f.write(text + '\n') 

        with open("log.txt", "r") as f:
            text = f.read()

        cr_pattern = r'\n(\d{2}-\d{2})\n\n\n([A-Za-z\*\#]+[A-Za-z 0-9\*\/\#]+)\n\n\n([0-9,]+[.]+[0-9]+)\n\n\n[^-]'
        db_pattern = r'\n(\d{2}-\d{2})\n\n\n([A-Za-z\*\#]+[A-Za-z 0-9\*\/\#]+)\n\n\n([-][0-9,]+[.]+[0-9]+)\n'

        # x = re.findall(cr_pattern, text)
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
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)

        # transactions = transactions[transactions.iloc[:,0].str.match(r'^\d{2}-\d{1,2}.*', na=False)].reset_index(drop=True)
        # transactions = transactions.rename(columns={0:'Date', 1: 'Description', 2:'Credit', 3:'Debit'})
        # transactions['Date'] = transactions['Date'].str.replace(r'[-,]', '/', regex=True)
        
        # credits = transactions[['Date', 'Description', 'Credit']]
        # debits = transactions[['Date', 'Description', 'Debit']]

        # credits = credits[credits['Credit'] != '']

        # debits = debits[debits['Debit'] != '']

            
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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
        for f in files:
            os.remove(f)

    
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
                    print(table_title.text)
                    if table_title.text in ['Deposits/Other Credits']:
                        df=table[0].to_pandas()
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)

                    if table_title.text in ['Other Debits']:
                        df=table[0].to_pandas()
                        debits_aws = pd.concat([debits_aws, df], ignore_index=True)

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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)

                    if table_title.text in ['Electronic Payments', 'DAILY ACCOUNT ACTIVITY Electronic Payments (continued)', 'Electronic Payments (continued)', 'Other Withdrawals', 'Service Charges']:
                        df=table[0].to_pandas()
                        debits_aws = pd.concat([debits_aws, df], ignore_index=True)

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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
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

        x = re.findall(cr_pattern, text)
        print(x)

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
        print(credits)

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
                        credits_aws = pd.concat([credits_aws, df], ignore_index=True)
            
        # df = df[df.iloc[:,0].str.match(r'^\d{2}/\d{1,2}.*', na=False)].reset_index(drop=True)

        # df.drop(df.columns[5], axis=1, inplace=True)
        # df.drop(df.columns[1], axis=1, inplace=True)

        # df = df.rename(columns={df.columns[0]: "Date", df.columns[1]: "Description", df.columns[2]: "Credits", df.columns[3]: "Debits"})

        # transactions = df[['Date', 'Description', 'Credits', 'Debits']]

        # credits_list = []
        # debits_list = []

        # for i in range(len(transactions)):
        #     if transactions.iloc[i,2] == '':
        #         row = pd.DataFrame(transactions.iloc[i]).T  # Transpose to maintain row structure
        #         debits_list.append(row)
        #     else:
        #         row = pd.DataFrame(transactions.iloc[i]).T  # Transpose to maintain row structure
        #         credits_list.append(row)

        # credits = pd.concat(credits_list, ignore_index=True)
        # debits = pd.concat(debits_list, ignore_index=True)

        # debits = debits.drop('Credits', axis=1)

        # credits = credits.drop('Debits', axis=1)

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
        # os.remove(temp_excel)
        # os.remove(temp_excel2)
        for f in files:
            os.remove(f)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9595, debug=True)  # Enable debug mode for development
