import os
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from langchain_community.callbacks import get_openai_callback
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser
from langchain_core.output_parsers import JsonOutputParser
import pandas as pd
import psycopg2
import time
from dotenv import load_dotenv
import logging
import json
import uuid

load_dotenv()

log = logging.getLogger(__name__)

llm = ChatOpenAI(model='gpt-4o')

app = Flask(__name__)
CORS(app, origins = ['*']) 

domain = 'https://staging-backend.jkadvantage.co.in/lms/download-excel?file='

UPLOAD_DIRECTORY = 'uploads'
if not os.path.exists(UPLOAD_DIRECTORY):
    os.makedirs(UPLOAD_DIRECTORY)

@tool
def SQLQuery(text):
    """Forms the SQL Query and returns the result of the query."""
    conn = psycopg2.connect(
        host = "localhost", 
        database = "test2", 
        user = "postgres", 
        password = "123"
    )
    conn.autocommit = True

    log.debug("Connection Established!")

    query_prompt = ChatPromptTemplate.from_template(
    """
    Answer the question based on the context below.

    Context:
    You are an expert PostgreSQL assistant who helps user form SQL queries in proper format.
    Form a proper PostgreSQL query which could be run on the database.
    You will get a natural language input as {text}.

    The database has two tables:
        1. 'data' table which consists of rows denoting transactions also known as orders.
        2. 'active_dealer' table having a list of customers who are currently considered to have status active 
    
    Use the table from database respectively as mentioned by the user.

    The 'data' table has the following columns:
        "financialyear" -> Shows the financial year. Financial years are stored in XX-YY format such as 19-20, 20-21 and so on.
        "quarter" -> Shows the quarter of the year as Q1, Q2, Q3 and Q4.
            Q1 represents APR, MAY and JUN months
            Q2 represents JUL, AUG and SEP months
            Q3 represents OCT, NOV and DEC months
            Q4 represents JAN, FEB and MAR months
        "year" -> Shows the year namely 2019,2020 and so on.
        "month" -> Shows the month of the year in 3 characters format namely JAN, FEB and so on.
        "zone" -> Shows the zone of purchase namely East, West, North, South and so on.
        "region" -> Shows the region of purchase. All region names are in all caps.
        "customercode" -> Shows the unique code of the customer. Also known as SAP code.
        "customer" -> Shows the name of the customer.
        "accountgroupkey" -> Shows the key to denote the account group type.
        "accountgroup" -> Shows the name of the account group type.
        "customerclassification" -> Shows the classification of the customer. Contains abbreviations. The abbreviation of the classification are as follows:
            1. "CDS DEALER" -> "PD"
            2. "Steel wheels" -> "SW"
            3. "Common" -> "CO"
            4. "Indian Oil-Comb" -> "IC"
            5. "HPCL-Comb" -> "HC"
            6. "Non truck" -> "NT"
            7. "Non SAS Account" -> "NA"
            8. "Truck" -> "TR"
            9. "Xpress Wheels" -> "XW"
            10. "DISTRIBUTOR" -> "DB"
            11. "Waves account" -> "WV"
            12. "OTR" -> "OT"
            13. "FLEET MANAGEMENT" -> "FM"
            14. "CDS-PTP" -> "PP"
            15. "Pref.Trade Partner" -> "TP"
            16. "Rural Distribution" -> "RD"
            17. "Not assigned" -> "#"
            18. "HPCL-PTP" -> "HP"
            19. "Truck wheels" -> "TW"
            20. "Maruti Suzuki" -> "MS"
            21. "Farm Xpress Wheel" -> "FW"
            22. "A-customer" -> "01"
            23. "B-customer" -> "02"
            24. "ESSAR Oil-Comb" -> "EC"
            25. "RENAULT" -> "RN"
            26. "HYUNDAI" -> "HY"
            27. "HONDA" -> "HD"
            28. "CDS-PTP DEALER" -> "CP"
            29. "Mobility" -> "MB"
            30. "INDIAN OIL-PTP" -> "IP"
            31. "ESSAR Oil-NT" -> "EN"
            32. "Export Tornel-MX" -> "MX"
            33. "NISSAN" -> "NS"
        "inches" -> Shows the code representing size of the tyre.
        "material" -> Code representing the material of tyre.
        "tyrecategory" -> Shows the category of the tyre.
        "pattern" -> Shows the pattern of the tyre.
        "billingtype" -> Shows the type of billing.
        "quantity" -> Shows the quantity of the tyre transactions. Positive values mean orders and negative values mean returns. For orders, consider the positive values; for returns, consider the negative values; for transactions, consider all the values.
    
    The 'active_dealer' table has the following columns:
        "customercode" -> Shows the unique code of the customer. Also known as SAP code.
        "customer" -> Shows the name of the customer.
        "quantity" -> Shows the total amount of transactions for that customer.

    For queries involving financial year, fetch results using "financialyear" column and for queries involving year, fetch results using "year" column.

    The data we have follows Indian definition of Financial Year i.e. a financial year would start from April of current year and end in March of next year.
    For example: FY 2022-23 is APR 2022 to MAR 2023 which can also be written as Q1 2022 to Q4 2023.
    
    The yearly data will have quarters in the order of Q4, Q1, Q2, Q3 of the same year.

    A single financial year or calender year should have exactly 4 quarters.
    
    When asked for advantage data, select customers for that financial year who have billing type in 'ZOR', 'YOR', 'YPLT', 'YRDR', 'ZPLT', 'ZRDR' and Account Group Key is 'Z001' combined with customers who have billing type in 'ZOR', 'YOR', 'YPLT', 'YRDR', 'ZPLT', 'ZRDR' and Account Group Key is 'Z004' and customer classification in 'DB' and 'RD'.
    
    Unless asked exclusively, don't include active status in query.

    When asked for a quarter on quarter offtake or month on month offtake, calculate the difference in quantity for a month or quarter across the years and return only the difference per month or quarter and month or quarter respectively.

    When user mentions a quarter of a year, only fetch details for that particular quarter of that year.

    Make sure the query is being run for only the quarters and/or years mentioned by the user in {text} and you are not adding any quarters and/or years by yourself.
    
    Do not include any explanation for the SQL query you formed.
    Do not add any limit to the amount of results to be returned and return all the information, unless a limit is mentioned by the user.
    
    Make sure you avoid cases leading to divide by zero error. Use NULLIF for denominators.
    Make sure you avoid AmbiguousColumn errors when using JOIN, by never accessing a column directly using its column name and always mentioning table name or alias to be used to access columns using table_name_alias.column_name format.
    
    The columns used in the aggregate function should never be added to GROUP BY.
    NEVER group results by 'customercode' or 'customer' if you are fetching a count of customers.
    Remember to add a GROUP BY clause to the query whenever you need to group results for the non-aggregate columns.
    When asking a total count, make sure to not add a group by 'customer' or 'customercode' or 'quantity' or such fields which do not need to be grouped on for a total count.
    The query should not have any opening or closing brackets like '(' or ')' around the table name.
    All the column names should be in lowercase letters only.

    All the column names and table names used in the query should be in double quotes.

    Do not use subqueries.
    ORDER BY only a column which you have selected under SELECT part of query.
    When using ORDER BY, make sure that the column being used is a result column or an alias of a result column.
    Make sure to include only and only the columns requested by user in input.
    Make sure your query does not have more than one row returned by a subquery used as an expression.

    For SELECT DISTINCT, ORDER BY expressions must be present in query.
    For queries using months, the order of months should always be chronologically (JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG, SEP, OCT, NOV, DEC) and not alphabetically.
    For queries using Financial Yearly data, the order of months should always be chronologically, starting from APR and going to MAR in order (APR, MAY, JUN, JUL, AUG, SEP, OCT, NOV, DEC, JAN, FEB, MAR) and not alphabetically.
    Never use ORDER BY FIELD for ordering data in some particular manner.
    
    For financial year queries, NEVER group by year.
    It you are using ORDER BY for a column, it should ALWAYS be fetched under the SELECT part of the query.
    Only order on a column fetched in the query by SELECT.

    Make sure you are returning the query without any prefix or suffix such as '```sql' or '```' or 'Here is the SQL query:' or 'Here is the PostgreSQL query:' or anything such
    The query SHOULD NOT IN ANY CASE have any prefix or suffix such as '```sql' or '```' or 'Here is the SQL query:' or 'Here is the PostgreSQL query:' or anything such.
    Return only the SQL query in the format of a string and no explanations.

    Here are some example for how the output should be: {sql_format_example}

    """
    )
    
    format_chain = query_prompt | llm | StrOutputParser()

    query = format_chain.invoke({"text": text, "sql_format_example": sql_format_example})
    print("\nQuery: ", query)

    log.debug("Query Formed!")

    cursor = conn.cursor() 

    cursor.execute(query) 

    log.debug("Query Executed!")

    res = cursor.fetchall()
    result = '\n'.join(str(e) for e in res)
    # print("\nResult: ", result)
 
    conn.commit() 
    conn.close() 

    # result = db.run(query)
    print(result)
    
    return query, result

@tool
def visualize(text):
    """Forms the SQL Query for a visualization request and returns the result of the query as a json."""

    query, result = SQLQuery.invoke(text)

    parser = JsonOutputParser()

    json_prompt = ChatPromptTemplate.from_template(
    """
    Answer the question based on the context below.

    Context:
    You will get input {result} in form of the result of SQL query as well as the original user request {text}.
    
    You have to return the result in json format. The graphing library we are using is Recharts. 
    You will also get details about the type of chart to be plotted from the user request {text}.
    Do not in any case populate the data for the chart by yourself. The data should be taken from the input itself and not formed by you.
    If the result of the SQL query obtained is empty, print "No data found" and return.
    For the given user question {text}, please give an approprite graph type and accurate graph parameters datakey or namekey wherever relevant.
    The json result should consist of the following JSON keys:
        1. "input" -> The user input {text}
        2. "graph_type" -> This will have the type of chart to be plotted. It will consist of only the type of chart such as "linechart", "barchart", "piechart", "scatterchart" and no other information.
        3. "graph_parameters" -> This will have parameters needed to plot the graph.
        4. "data" -> This will consist of data points. 
        5. "sql_query" -> The SQL query input {query}
        6. "label" -> A label for the graph, in human readable format and not field names.
    Only output the json and nothing else.
    The datakey and namekey should always be exactly as in the SQL result, never use a datakey that is not in the results.
    Always indicate where the datakey or namekey is coming from by suffixing the component with "_" followed by component name. Example: datakey_Pie_1, namekey_Pie_1, datakey_YAxis etc.
    DO NOT ADD numbered suffixed like "_1" or "_2" to graph parameters containing XAxis or YAxis in their name.
    The 'graph_parameters' should contain keys be as below depending on 'graph_type'. The necessary keys should always be there and the optional keys are added as per need:
        - 'barchart' :
            necessary : 'datakey_XAxis' => categorical value 
                        'datakey_Bar_1' => numerical value
            optional :  'datakey_Bar_2' => numerical value, add one each for plotting multiple bar graphs
        - 'piechart' :
            necessary : 'datakey_Pie_1' => numerical value
                        'namekey_Pie_1' => categorical value   
        - 'linechart' :
            necessary : 'datakey_XAxis' => categorical value 
                        'datakey_Line_1' => numerical value
            optional :  'datakey_Line_2' => numerical value, add one each for plotting multiple line graphs
        - 'scatterchart' :
            necessary : 'namekey_Scatter' => categorical value 
                        'datakey_XAxis' => numerical value
            optional :  'datakey_Scatter_1' => numerical value, add one each for plotting multiple scatter graphs
                        
    Always make sure that the 'graph parameters' are in the same order as above and the 'data' also has data entries in the same order as 'graph parameters'.
    Especially for when 'graph_type' is 'piechart' each data entry must have the numerical data i.e. datakey first, followed by categorical data i.e. namekey for each data entry.
    For example:
        "graph_type": "piechart",
        "graph_parameters": {"datakey_Pie_1": "average_offtake", "namekey_Pie_1": "quarter"},
        "data": [{"average_offtake": 8.0393105368476108, "quarter": "Q1"}, {"average_offtake": 8.2378032538059075, "quarter": "Q2"}],
    This is only an example on the order to be followed and the actual data would vary.
    The json should contain the data in chronological month order (JAN, FEB, MAR, etc.) per year and not alphabetically.
    For queries involving quarters of years the data should ALWAYS be ordered as Q4, Q1, Q2, Q3 - ordered in ascending order of years.
    For queries involving quarters of financial years the data should ALWAYS be ordered as Q1, Q2, Q3, Q4 - ordered in ascending order of years.
    For example: Q1 2020, Q2 2020, Q3 2020, Q4 2021, Q1 2021, Q2 2021 and so on.
    For example: Q1 21-22, Q2 21-22, Q3 21-22, Q4 21-22, Q1 22-23, Q2 22-23 and so on.
    The 'data' should have keys exactly same as values of 'graph_parameters', with each value from 'graph_parameter' present in 'data' as key.
    Always make sure that the order of keys in each 'data' entry follows the same order as in 'graph_parameter' values.
    Here are some examples of the format of output required : {data_format}
    """
    )

    json_chain = json_prompt | llm | parser

    print("Raw output before JSON parsing:", result)  # Debugging line

    query = json_chain.invoke({"result": result, "text": text, "query": query, "data_format": json_format_example})

    log.debug("Json Formed!")
    
    print("\nJson: ", query)

    # return query
    return {
            'chart_result': {
                'data': query.get('data', None),
                'graph_parameters': query.get('graph_parameters', None),
                'graph_type': query.get('graph_type', None),
                'query': query.get('sql_query', None),
                'chart_description': query.get('label', None),
                },
            'input_question':query.get('input', None),
            }, 200

@tool
def excel(text):
    """Return results as excel file"""
    query, result = SQLQuery.invoke(text)
    df = pd.DataFrame(result)
    current_time_millis = int(time.time() * 1000)
    filename = os.path.join(UPLOAD_DIRECTORY, '{current_time_millis}.xlsx'.format(current_time_millis=current_time_millis))
    df.to_excel(filename, index=False)
    log.debug("Excel Formed!")
    return '{domain}{current_time_millis}.xlsx'.format(domain=domain, current_time_millis=current_time_millis)
    
tool = [SQLQuery, visualize, excel]

json_format_example = """
Example 1 =>
```json
{
    "input": "Share a bar chart for average quarterly offtake for year 2022",
    "graph_type": "barchart",
    "graph_parameters": {"datakey_XAxis": "quarter", "datakey_Bar_1": "average_offtake"},
    "data": [{"quarter": "Q1", "average_offtake": 8.0393105368476108}, {"quarter": "Q2", "average_offtake": 8.2378032538059075}, {"quarter": "Q3", "average_offtake": 7.8879574670104418}, {"quarter": "Q4", "average_offtake": 7.8775089728485712}],
    "sql_query": "SELECT "quarter", AVG("quantity") AS "average_offtake" FROM "data" WHERE "year" = 2022 GROUP BY "quarter"",
    "label": "Bar Chart for Average Quarterly Offtake"
}

Example 2 =>
```json
{
    "input": "Share a pie chart for average quarterly offtake for year 2022",
    "graph_type": "piechart",
    "graph_parameters": {"datakey_Pie_1": "average_offtake", "namekey_Pie_1": "quarter"},
    "data": [{"average_offtake": 8.0393105368476108, "quarter": "Q1"}, {"average_offtake": 8.2378032538059075, "quarter": "Q2"}, {"average_offtake": 7.8879574670104418, "quarter": "Q3"}, {"average_offtake": 7.8775089728485712, "quarter": "Q4"}],
    "sql_query": "SELECT "quarter", AVG("quantity") AS "average_offtake" FROM "data" WHERE "year" = 2022 GROUP BY "quarter"",
    "label": "Pie Chart for Average Quarterly Offtake"
}
```

Example 3 =>
```json
{
    "input": "Show a bar chart for the count of distinct dealers for each zone with 'HY' classification for FY 2020-21",
    "graph_type": "barchart",
    "graph_parameters": {"datakey_XAxis": "zone", "datakey_Bar_1": "count"},
    "data": [{"zone": "East", "count": 13}, {"zone": "North", "count": 2}, {"zone": "West", "count": 3}],
    "sql_query": "SELECT "data"."zone", COUNT(DISTINCT "data"."customercode") FROM "data" WHERE "data"."customerclassification" = 'HY' AND "data"."financialyear" = '20-21' GROUP BY "data"."zone"",
    "label": "Bar Chart for Count of Dealers"
}
```

Example 4 =>
```json
{
    "input": "Share a scatter graph for total count of customers by year and quarter in North Zone with Customer Classification 'TP' for Q1 of FY 2019-20 to Q4 of FY 2020-21", 
    "graph_type": "scatterchart", 
    "graph_parameters": {"datakey_XAxis": "count", "namekey_Scatter_1": "quarter"}, 
    "data": [{"quarter": "Q1 2019-20", "count": 14475}, {"quarter": "Q2 2019-20", "count": 10021}, {"quarter": "Q3 2019-20", "count": 7925}, {"quarter": "Q4 2019-20", "count": 7070}, {"quarter": "Q1 2020-21", "count": 3700}, {"quarter": "Q2 2020-21", "count": 7819}, {"quarter": "Q3 2020-21", "count": 7704}, {"quarter": "Q4 2020-21", "count": 6444}],
    "sql_query": "SELECT "year", "quarter", COUNT("customercode") FROM "data" WHERE "zone" = \'North\' AND "customerclassification" = \'TP\' AND "financialyear" IN (\'19-20\', \'20-21\') GROUP BY "financialyear", "quarter" ORDER BY "financialyear"",
    "label": "Scatter Graph for Total Count of Customers"
}

example 5 =>
```json
{
    "input": "Share a change in quarter on quarter offtake for year FY 2021-22 vs FY 2022-23 as a line chart", 
    "graph_type": "linechart", 
    "graph_parameters": {"datakey_XAxis": "quarter", "datakey_Line_1": "offtake"}, 
    "data": [{"quarter": "Q1", "offtake": 14475}, {"quarter": "Q2", "offtake": 10021}, {"quarter": "Q3", "offtake": 7925}, {"quarter": "Q4", "offtake": 7070}],
    "sql_query": "SELECT "quarter", SUM(CASE WHEN "financialyear" = '22-23' THEN "quantity" ELSE 0 END) - SUM(CASE WHEN "financialyear" = '21-22' THEN "quantity" ELSE 0 END) AS "change_in_offtake" FROM "data" WHERE ("data"."financialyear" IN ('21-22', '22-23')) GROUP BY "data"."quarter" ORDER BY "data"."quarter""
    "label": "Line Graph for Change in Quarter on Quarter Offtake"
}

example 6 =>
```json
{
    "input": "Show a bar chart to compare offtake between FY 2022-23 and FY 2023-24 for each zone",
    "graph_type": "barchart",
    "graph_parameters": {"datakey_XAxis": "zone", "datakey_Bar_1": "offtake_22_23", "datakey_Bar_2": "offtake_23_24"},
    "data": [{"zone": "East", "offtake_22_23": 2559720.0, "offtake_23_24": 1944190.0}, {"zone": "Nepal", "offtake_22_23": 0, "offtake_23_24": 19298.0}, {"zone": "North", "offtake_22_23": 3564074.0, "offtake_23_24": 3717753.0}, {"zone": "Not assigned", "offtake_22_23": 0, "offtake_23_24": 803.0}, {"zone": "Plant", "offtake_22_23": 0, "offtake_23_24": 5002.0}, {"zone": "South", "offtake_22_23": 2151174.0, "offtake_23_24": 0}, {"zone": "South - I", "offtake_22_23": 459828.0, "offtake_23_24": 1249148.0}, {"zone": "South - II", "offtake_22_23": 567537.0, "offtake_23_24": 1582382.0}, {"zone": "West", "offtake_22_23": 2947819.0, "offtake_23_24": 2624835.0}],
    "sql_query": "SELECT "zone", SUM(CASE WHEN "financialyear" = \'22-23\' THEN "quantity" ELSE 0 END) AS "offtake_22_23", SUM(CASE WHEN "financialyear" = \'23-24\' THEN "quantity" ELSE 0 END) AS "offtake_23_24" FROM "data" WHERE "financialyear" IN (\'22-23\', \'23-24\') GROUP BY "zone"",
    "label": "Bar Chart for Offtake Comparison between FY 2022-23 and FY 2023-24"
}

example 7 =>
```json
{
    "input": "Share a change in quarter on quarter offtake for year FY 2021-22 and FY 2022-23 as a line chart", 
    "graph_type": "linechart", 
    "graph_parameters": {"datakey_XAxis": "quarter", "datakey_Line_1": "change_in_offtake"}, 
    "data": [{"quarter": "Q1 21-22", "change_in_offtake": 557018.0}, {"quarter": "Q2 21-22", "change_in_offtake": 2413659.0}, {"quarter": "Q3 21-22", "change_in_offtake": 2171918.0}, {"quarter": "Q4 21-22", "change_in_offtake": 751088.0}], 
    "sql_query": "SELECT "quarter", SUM(CASE WHEN "financialyear" = \'22-23\' THEN "quantity" ELSE 0 END) - SUM(CASE WHEN "financialyear" = \'21-22\' THEN "quantity" ELSE 0 END) AS "change_in_offtake" FROM "data" WHERE "financialyear" IN (\'21-22\', \'22-23\') GROUP BY "quarter" ORDER BY "quarter"", 
    "label": "Line Chart for Quarter on Quarter Offtake Change"
}

example 8 =>
```json
{
    "input": "Share a comparision of quarter on quarter offtake for year FY 2021-22 and FY 2022-23 as a line chart", 
    "graph_type": "linechart", 
    "graph_parameters": {"datakey_XAxis": "quarter", "datakey_Line_1": "FY_2021_22", "datakey_Line_2": "FY_2022_23"}, 
    "data": [{"quarter": "Q1 21-22", "FY_2021_22": 3089499.0, "FY_2022_23": 2532481.0}, {"quarter": "Q2 21-22", "FY_2021_22": 3278102.0, "FY_2022_23": 864443.0}, {"quarter": "Q3 21-22", "FY_2021_22": 3007339.0, "FY_2022_23": 835421.0}, {"quarter": "Q4 21-22", "FY_2021_22": 2875212.0, "FY_2022_23": 2124124.0}], 
    "sql_query": "SELECT "quarter", SUM(CASE WHEN "financialyear" = \'22-23\' THEN "quantity" ELSE 0 END) AS "FY_2022_23", SUM(CASE WHEN "financialyear" = \'21-22\' THEN "quantity" ELSE 0 END) AS "FY_2021_22" FROM "data" WHERE "financialyear" IN (\'21-22\', \'22-23\') GROUP BY "quarter" ORDER BY "quarter"", 
    "label": "Line Chart for Quarter on Quarter Offtake Comparison FY 2021-22 vs FY 2022-23"
}

example 9 =>
```json
{
    "input": "pie chart for total offtake per month for FY 2020-21", 
    "graph_type": "piechart", 
    "graph_parameters": {"datakey_Pie_1": "total_offtake", "namekey_Pie_1": "month"}, 
    "data": [{"total_offtake": "82899.0", "month": "APR"}, {"total_offtake": "672333.0", "month": "MAY"}, {"total_offtake": "955921.0", "month": "JUN"}, {"total_offtake": "1022520.0", "month": "JUL"}, {"total_offtake": "1007422.0", "month": "AUG"}, {"total_offtake": "1115069.0", "month": "SEP"}, {"total_offtake": "1164656.0", "month": "OCT"}, {"total_offtake": "1045839.0", "month": "NOV"}, {"total_offtake": "1147228.0", "month": "DEC"}, {"total_offtake": "1080000.0", "month": "JAN"}, {"total_offtake": "1033255.0", "month": "FEB"}, {"total_offtake": "1060214.0", "month": "MAR"}], 
    "sql_query": "SELECT \"month\", SUM(\"quantity\") AS \"total_offtake\" FROM \"data\" WHERE \"financialyear\" = '20-21' GROUP BY \"month\" ORDER BY CASE \"month\" WHEN 'APR' THEN 1 WHEN 'MAY' THEN 2 WHEN 'JUN' THEN 3 WHEN 'JUL' THEN 4 WHEN 'AUG' THEN 5 WHEN 'SEP' THEN 6 WHEN 'OCT' THEN 7 WHEN 'NOV' THEN 8 WHEN 'DEC' THEN 9 WHEN 'JAN' THEN 10 WHEN 'FEB' THEN 11 WHEN 'MAR' THEN 12 END",
    "label": "Pie Chart for Total Offtake per Month for FY 2020-21"
}

In the above examples, the fields for "data" are truncated for some cases, but for actual output print all the entries available.
"""

sql_format_example = """
Example 1 =>
    Input: Show a bar chart for the count of distinct dealers for each zone with 'HY' classification for FY 2021-22.
    Output: SELECT "data"."zone", COUNT(DISTINCT "data"."customercode") FROM "data" WHERE "data"."customerclassification" = 'HY' AND "data"."financialyear" = '21-22' GROUP BY "data"."zone"

Example 2 =>
    Input: Share the details of distinct dealers having returns in Quarter 1, Quarter 2 and Quarter 3 of year 2023. Limit to 10.
    Output: SELECT DISTINCT "customercode", "customer" FROM "data" WHERE "quantity" < 0 AND "year" = 2023 AND ("quarter" = 'Q1' OR "quarter" = 'Q2' OR "quarter" = 'Q3') ORDER BY "customercode", "customer" LIMIT 10

Example 3 =>
    Input: Share total count of customers by year and quarter in North Zone with Customer Classification 'TP' for Q1 of FY 2019-20 to Q4 of FY 2020-21
    Output: SELECT "quarter", "financialyear", COUNT("customercode") FROM "data" WHERE "customerclassification" = 'TP' AND "zone" = 'North' AND "financialyear" IN ('19-20', '20-21') GROUP BY "quarter", "financialyear"

Example 4 =>
    Input: Share the amount of distinct dealers with Steel Wheels classification, where quarterly offtake reduced by 30%, from Q1 FY 2022-23 to Q1 FY 2023-24
    Output: SELECT COUNT(DISTINCT "data"."customercode") FROM "data" WHERE "data"."customerclassification" = 'SW' AND ("data"."financialyear" = '22-23' AND "data"."quarter" = 'Q1' OR "data"."financialyear" = '23-24' AND "data"."quarter" = 'Q1') HAVING SUM(CASE WHEN "data"."financialyear" = '22-23' THEN "data"."quantity" ELSE 0 END) > 0 AND SUM(CASE WHEN "data"."financialyear" = '23-24' THEN "data"."quantity" ELSE 0 END) < SUM(CASE WHEN "data"."financialyear" = '22-23' THEN "data"."quantity" ELSE 0 END) * 0.7

Example 5 =>
    Input: Share a change in quarter on quarter offtake for year FY 2021-22 vs FY 2022-23 as a line chart
    Output: SELECT "quarter", SUM(CASE WHEN "financialyear" = '22-23' THEN "quantity" ELSE 0 END) - SUM(CASE WHEN "financialyear" = '21-22' THEN "quantity" ELSE 0 END) AS "change_in_offtake" FROM "data" WHERE ("data"."financialyear" IN ('21-22', '22-23')) GROUP BY "data"."quarter" ORDER BY "data"."quarter" 

Example 6 =>
    Input: Share a change in month on month offtake for FY 2022-23 vs FY 2023-24
    Output: SELECT "month", SUM(CASE WHEN "financialyear" = '23-24' THEN "quantity" ELSE 0 END) - SUM(CASE WHEN "financialyear" = '22-23' THEN "quantity" ELSE 0 END) AS "change_in_offtake" FROM "data" WHERE "financialyear" IN ('22-23', '23-24') GROUP BY "month" ORDER BY CASE "month" WHEN 'APR' THEN 1 WHEN 'MAY' THEN 2 WHEN 'JUN' THEN 3 WHEN 'JUL' THEN 4 WHEN 'AUG' THEN 5 WHEN 'SEP' THEN 6 WHEN 'OCT' THEN 7 WHEN 'NOV' THEN 8 WHEN 'DEC' THEN 9 WHEN 'JAN' THEN 10 WHEN 'FEB' THEN 11 WHEN 'MAR' THEN 12 END
    
"""


function_calling_prompt = ChatPromptTemplate.from_messages([
    """You are an AI assistant that helps users interact with a database and visualize data. 
    You have access to three functions:
    1. SQLQuery: Forms and executes SQL queries on the database and displays its result.
    2. visualize: Creates charts and graphs based on database queries. Use this only and only when you have been asked to plot a graph.
    3. excel: Export the result to an excel table.

    ONLY and ONLY if user request contains the keyword 'chart' then use 'visualize' function. For all other cases, function should be 'SQLQuery'.

    Your task is to determine which function to call based on the user's input {query}.
    If the user mentions to get excel file of result, use 'excel' function.
    If the user asks for data visualization by asking for any kind of chart or graph by mentioning keywords such as chart or graph or its type, only then use the 'visualize' function.
    For all other database-related queries, use the 'SQLQuery' function like user asking to share or show or display.

    Respond by returning only the function name that needs to be called. Do not print any other information.
    For example:
    - "SQLQuery"
    - "visualize"
    - "excel"
    """
])

format_chain = function_calling_prompt | llm | StrOutputParser()

@app.route("/", methods=['GET'])
def hello_world():
  return "<p>I'm building something cool today!</p>"

def query_result(query):
    try:
        conn = psycopg2.connect(
        host = "localhost", 
        database = "test2", 
        user = "postgres", 
        password = "123"
    )
        cur=conn.cursor()
    
        cur.execute(query)
        rows=cur.fetchall()
        column_names=[desc[0] for desc in cur.description]
        print(rows)
        print("Successfully generated Query Output.")
        result=[dict(zip(column_names,row)) for row in rows]
        return result
    except (Exception,psycopg2.Error) as e:
        print(f"Error creating table: {str(e)}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    
def update_order_number(user_id):
    update_count=""" UPDATE chart_data SET display_order = display_order + 1 WHERE user_id=%s;"""
    try:
        conn = psycopg2.connect(
        host = "localhost", 
        database = "test2", 
        user = "postgres", 
        password = "123"
    )
        cur=conn.cursor()
        cur.execute(update_count,(str(user_id),))
        conn.commit()
        return jsonify({"message":f"Successfuly updated the order count"}), 200
    except (Exception, psycopg2.Error) as e:
        return jsonify({"message": f"Error updating  display order column: {str(e)}"}), 500
    finally:
        
        if cur:
            cur.close()
        if conn:
            conn.close()


def insert_data(user_id,prompt,query,graph_type,graph_parameters,name):
    update_order_number(user_id)
    order=0
    insert_rows="""
INSERT INTO chart_data(user_id,prompt,query,graph_type,graph_parameters,name,id,display_order) VALUES(%s,%s,%s,%s,%s,%s,%s,%s);

"""
    try:
        conn = psycopg2.connect(
        host = "localhost", 
        database = "test2", 
        user = "postgres", 
        password = "123"
    )
        cur=conn.cursor()
        cur.execute(insert_rows,(user_id,prompt,query,graph_type,graph_parameters,name,str(uuid.uuid4()),order))
        conn.commit()
        return {"message":"Successfully saved the chart data in chart_data table."}
    except (Exception,psycopg2.Error) as e:
        return {"message":f"Error saving chart data {str(e)}"}
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    

@ app.route('/lms/save',methods=['POST'])
def save_query_url():
    result={}
    data=request.json
    print("\n Save Data \n", data)
    user_id=data.get("user_id")
    prompt=data.get("prompt")
    
    if not user_id or not prompt:
        return jsonify({"error": 'Missing user_id or prompt in the request'}),400
    
    try:
        # llm_response=chat_with_openai(prompt)
        # try:
        #     json_data=json.loads(llm_response)
        # except json.JSONDecodeError as e:
        #     return jsonify({"error": f"Error parsing LLM response: {str(e)}"}), 500

        # if 'query' not in json_data:
        #     return jsonify({"error": "Query not found in LLM response"}), 500
        
        json_data = request.json
        query=json_data["query"]
        # chart_data=query_result(query)
        graph_type=json_data["graph_type"]
        graph_parameters=json_data["graph_parameters"]
        name=json_data["name"]
        result["prompt"]=prompt
        result["name"]=name
        result["query"]=query
        result["graph_type"]=graph_type
        result["graph_parameters"]=graph_parameters

        postgres_response=insert_data(user_id,prompt,query,graph_type,json.dumps(graph_parameters),name)
        result["database_message"]=postgres_response["message"]
        return jsonify(result),200
    except Exception as e:
        return jsonify({"error":f"An error occured: {str(e)}"}),500

@app.route('/lms/charts', methods=['GET'])
def fetch_charts():
    user_id = request.args.get('user_id')
    
   
    if not user_id:
        return jsonify({"message": "user_id is required"}), 400

    query = "SELECT * FROM Chart_data WHERE user_id = %s"
    conn = None
    cur = None
    
    try:
        
        conn = psycopg2.connect(
        host = "localhost", 
        database = "test2", 
        user = "postgres", 
        password = "123"
    )
        cur = conn.cursor()
        
        
        cur.execute(query, (str(user_id),))
        result = cur.fetchall()

      
        if not result:
            return jsonify({"message": "No charts found for this user."}), 404

        
        column_names = [desc[0] for desc in cur.description]
        charts = [dict(zip(column_names, row)) for row in result]
        print(charts)
        results=[]
        for i in charts:
            result={}
            result['id']=i['id']
            result['user_id']=i['user_id']
            result['name']=i['name']
            result['prompt']=i['prompt']
            query=i['query']
            chart_data=query_result(query)
            result['chartData']=chart_data
            graph_type=i['graph_type']
            graph_parameters=i['graph_parameters']
            result['order']=i['display_order']
            result['chartConfig']={
                "query":query,
                "graph_type":graph_type,
                "graph_parameters":graph_parameters
            }
            results.append(result)

        return jsonify(results), 200
    
    except (Exception, psycopg2.Error) as e:
        return jsonify({"message": f"Error getting chart data: {str(e)}"}), 500

    finally:
        
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/lms/charts/order", methods=["POST"])
def update_order():
    data = request.json
    charts = data.get('charts')
    update_query = """UPDATE chart_data SET display_order = %s WHERE id = %s;"""

    
    conn = None
    cur = None

    try:
        
        conn = psycopg2.connect(
        host = "localhost", 
        database = "test2", 
        user = "postgres", 
        password = "123"
    )
        cur = conn.cursor()

        
        for chart in charts:
            chart_id = chart.get('id')
            order = chart.get('order')
            cur.execute(update_query, (order, chart_id))

        
        conn.commit()

        return jsonify({"message": "Successfully saved the updated order in chart_data table."}), 200

    except (Exception, psycopg2.Error) as e:
   
        if conn:
            conn.rollback()
        return jsonify({"message": f"Error updating order chart data: {str(e)}"}), 500

    finally:
       
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/lms", methods=['POST'])
def queryJson():
    req = request.get_json()
    print(req)
    text = req['question']

    if 'excel' in text.lower() or 'list' in text.lower():
        # chain = create_sql_query_chain(ChatOpenAI(temperature=0, model_name=MODEL_NAME), db, k=10000000)
        # response = chain.invoke({"question":text})
        response, result = SQLQuery.invoke(text)
        print(response)
        connection = psycopg2.connect(
            host = "localhost", 
            database = "test2", 
            user = "postgres", 
            password = "123")
        cursor = connection.cursor()
        #split_start = response.find('```sql')
        #split_end = response.find('```', split_start + 1)
        #response = response[split_start + len('```sql'):split_end]
        cursor.execute(response)
        columns = [desc[0] for desc in cursor.description]
        data = cursor.fetchall()
        result = []
        for row in data:
            result.append(dict(zip(columns, row)))
        cursor.close()
        connection.close()
        df = pd.DataFrame(result)
        current_time_millis = int(time.time() * 1000)
        filename = os.path.join(UPLOAD_DIRECTORY, '{current_time_millis}.xlsx'.format(current_time_millis=current_time_millis))
        df.to_excel(filename, index=False)
        return '{domain}{current_time_millis}.xlsx'.format(domain=domain, current_time_millis=current_time_millis)

    log.debug("Request Received!")

    with get_openai_callback() as cb:
        function_call = format_chain.invoke({"query": text})
        print("FC:", function_call)

        if function_call == "visualize":
            result = visualize.invoke(text)
        elif function_call == "excel":
            result = excel.invoke(text)
        else:
            query, result = SQLQuery.invoke(text)

    log.debug("Request Completed!")

    print(f"Total Tokens: {cb.total_tokens}")
    print(f"Prompt Tokens: {cb.prompt_tokens}")
    print(f"Completion Tokens: {cb.completion_tokens}")
    print(f"Total Cost (USD): ${cb.total_cost}")

    return result

@app.route('/lms/download-excel', methods=['GET'])
def download_excel():
    try:
        # Check if the Excel file exists
        filename = os.path.join(UPLOAD_DIRECTORY, request.args.get('file'))
        if not os.path.exists(filename):
            return jsonify({'error': 'Excel file not found'}), 404

        log.debug("Excel Return Processing!")
        # Send the Excel file as a downloadable attachment
        return send_file(
            filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Run the Flask development server on a different port (e.g., 8000)
    app.run(host="0.0.0.0", port=8001, debug=False, threaded=True)
