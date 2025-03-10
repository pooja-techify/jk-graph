import json
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas  # Importing canvas for PDF generation

result_file = {
    "0": "Overlook the issue for the time, hoping they will improve.|Support them while keeping the manager informed|Redistribute workload collaboratively|Talk to them to understand their challenges and help them improve.",
    "1": "Seek guidance while taking ownership|Seek clarification before beginning to ensure you are on the right track.|Take initiative to clarify requirements proactively.|Start working immediately to meet the deadline."
}

with open('jk-graph/Test/sjt_questions.json') as f:
    sjt_questions = json.load(f)

with open('jk-graph/Test/traits.json') as f:
    traits_data = json.load(f)

trait_scores = {trait['trait']: {'score': 0, 'category': trait['category']} for trait in traits_data['traits']}
# print(trait_scores)

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
            # Update the category score based on the trait's category
            category_scores[trait_scores[trait]['category']] += score  # Add score to the corresponding category

    return total_score/20, trait_scores, category_scores

score, trait_scores, category_scores = calculate_score(result_file)

category_scores['Agreeableness'] /= 12
category_scores['Conscientiousness'] /= 20
category_scores['Extraversion'] /= 17
category_scores['Neuroticism'] /= 7
category_scores['Openness'] /= 16

def generate_pdf_report(candidate_id, first_name, last_name, email, phone_number, location, time_taken, score):
    text = "Psychometric Test"
    file_path = f"{candidate_id}_psychometric_test.pdf"
    c = canvas.Canvas(file_path, pagesize=letter)
    
    c.setFont("Helvetica-Bold", 16)
    text_width = c.stringWidth(text, "Helvetica-Bold", 16)
    c.drawString((letter[0] - text_width) / 2, 750, text)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, 730, "Candidate Information")
    
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
        c.drawString(300, y_position, "{:.2f}".format(score))
        y_position -= 15
    
    c.showPage()

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
        c.drawString(300, y_position, "{:.2f}".format(details['score']))
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

# Call the function to generate the report (example usage)
generate_pdf_report("123", "Pooja", "Shah", "abc@gmail.com", "123", "Ahmedabad", "0m0s", score)

# print(f'Total Score: {score}')
# print(f'Trait Scores: \n{trait_scores}')
# print('Category Scores: \n' + ', '.join(f'{key}: {value:.2f}' for key, value in category_scores.items()))



