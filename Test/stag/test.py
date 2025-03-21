import json
import pandas as pd

def convert_traits_to_excel():
    try:
        # Read the JSON file
        with open('jk-graph/Test/stag/traits.json', 'r') as f:
            data = json.load(f)
        
        # Convert the traits list to a DataFrame
        df = pd.DataFrame(data['traits'])
        
        # Reorder columns to a more logical sequence
        df = df[['trait', 'category', 'count']]
        
        # Sort by category and then by count in descending order
        df = df.sort_values(['category', 'count'], ascending=[True, False])
        
        # Save to Excel
        excel_file = 'traits.xlsx'
        
        # Create Excel writer with formatting
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Traits')
            
            # Get the workbook and worksheet objects
            workbook = writer.book
            worksheet = writer.sheets['Traits']
            
            # Auto-adjust column widths
            for idx, col in enumerate(df.columns):
                max_length = max(
                    df[col].astype(str).apply(len).max(),
                    len(col)
                )
                # Add a little extra space to the column width
                worksheet.column_dimensions[chr(65 + idx)].width = max_length + 2
            
            # Add a summary sheet with category totals
            category_summary = df.groupby('category').agg({
                'trait': 'count',
                'count': 'sum'
            }).rename(columns={
                'trait': 'Number of Traits',
                'count': 'Total Occurrences'
            })
            
            category_summary.to_excel(writer, sheet_name='Category Summary')
            
            # Auto-adjust summary sheet column widths
            summary_worksheet = writer.sheets['Category Summary']
            for idx, col in enumerate(category_summary.columns):
                max_length = max(
                    category_summary[col].astype(str).apply(len).max(),
                    len(col)
                )
                # Add a little extra space to the column width
                summary_worksheet.column_dimensions[chr(66 + idx)].width = max_length + 2
            
            # Adjust category column width in summary sheet
            max_category_length = max(len(str(cat)) for cat in category_summary.index)
            summary_worksheet.column_dimensions['A'].width = max_category_length + 2

        print(f"Successfully converted to {excel_file}")
        print("Created two sheets:")
        print("1. 'Traits' - Contains all traits sorted by category and count")
        print("2. 'Category Summary' - Contains summary statistics for each category")
        
    except Exception as e:
        print(f"Error converting file: {e}")

if __name__ == "__main__":
    convert_traits_to_excel()