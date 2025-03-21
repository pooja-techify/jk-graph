import json
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def submit_sjt_test():
    try:
        candidate_id = '123'
        first_name = 'John'
        last_name = 'Doe'
        email = 'john.doe@example.com'
        phone_number = '+1234567890'
        location = 'New York'
        time_taken = '10'
        submit_reason = 'manual'
        result_file = {
            "0": "Redistribute workload collaboratively|Overlook the issue for the time, hoping they will improve.|Talk to them to understand their challenges and help them improve.|Support them while keeping the manager informed",
            "1": "Take initiative to clarify requirements proactively.|Seek clarification before beginning to ensure you are on the right track.|Seek guidance while taking ownership|Start working immediately to meet the deadline.",
            "2": "Reflect on lessons learned and apply them|Acknowledge challenges but focus on solutions|Communicate openly and seek improvement|Take responsibility for your part and suggest improvements for next time.",
            "3": "Suggest an automation solution to improve efficiency.|Do the work as instructed without complaining.|Delegate the task to someone junior.|Find a way to make the task meaningful",
            "4": "Work extra hours to catch up without informing your team.|Discuss the challenges with your manager and suggest solutions.|Prioritize tasks effectively to improve efficiency|Try to extend the deadline.",
            "5": "Ignore their request, assuming they will forget about it.|Implement it as requested to keep them happy.|Escalate the issue without discussing alternatives.|Explain the risks and suggest an alternative.",
            "6": "Accept it without analysing the risks.|Dismiss their idea since they are inexperienced.|Ignore their suggestion to avoid delays.|Evaluate it objectively and encourage discussion.",
            "7": "Express your concerns and suggest an ethical alternative.|Follow orders as instructed.|Refuse as it is conflicting with your personal ethics.|Comply but report the issue later.",
            "8": "Find appropriate resources before responding.|Refuse as it means you can not meet the deadline.|Assess the impact and suggest a practical solution.|Agree and later assess the feasibility.",
            "9": "Answer their questions, as they need your help.|Politely ask them to schedule a discussion at a convenient time.|Divert them to your manager.|Priortize your work for now and help them based on your availability.",
            "10": "Apologize and assure them that the issue is being addressed.|Explain why your team is not at fault.|Explain the issue is of another department.|Continue working until the issue comes up again.",
            "11": "Have your seniors resolve it themselves.|Clarify with both seniors and your manager before proceeding.|Pick the one that seems easier to complete.|Follow the instructions of the one with a higher rank.",
            "12": "Let them take the credit since it is team work.|Report the issue to your manager privately.|Discuss the issue with them privately after the meeting.|Confront them publicly in the meeting.",
            "13": "Company resources can be used for personal projects as well.|Have a private conversation with your colleague to understand the situation and remind them of company policies.|Report the issue to your manager or IT security team to ensure company policies are upheld.|Assume management is already aware and take no action since it does not directly affect your work.",
            "14": "Reach out to the manager and coworker to clarify the information before any misunderstandings spread.|Send a group response immediately to correct the information so that everyone is aware.|Escalate the issue to your manager to ensure the correct information is communicated to the team.|It is not directly your responsibility, so avoid providing any inputs.",
            "15": "Complain about remote work on social media.|Inform your manager and seek help immediately.|Try to fix it yourself.|Wait until someone else notices the delay.",
            "16": "Act ignorant when someone notices the issue and fix it.|Keep quiet and hope no one finds out.|Blame it on someone else if it is discovered.|Report it immediately and fix it.",
            "17": "Support them while keeping the manager informed|Do all the work yourself.|Exclude them from future team discussions.|Talk to them and understand the reason for their lack of contribution.",
            "18": "Analyse what has been working, adjust your approach, and seek advice from top-performing colleagues.|Evaluate external factors like market conditions and hope next quarter is better.|Push harder by increasing work hours, even if it means sacrificing quality.|Continue working as usual, trusting that things will improve.",
            "19": "Ignore the client's request and complete the project as originally planned.|Politely refuse the client's request and proceed with the original plan.|Analyse the feasibility of the change, discuss with your team, and propose a realistic timeline to both the client and your manager.|Accept the change immediately without considering its impact on the deadline."
            }

        if not result_file:
            return 0
        
        else:
            print("generating report")

            with open('jk-graph/Test/stag/sjt_questions.json') as f:
                sjt_questions = json.load(f)

            with open('jk-graph/Test/stag/traits.json') as f:
                traits_data = json.load(f)

            trait_scores = {trait['trait']: {'score': 0, 'category': trait['category'], 'count': trait['count']} for trait in traits_data['traits']}

            category_scores = {trait['category']: 0 for trait in traits_data['traits']}

            def calculate_score(result_file):
                total_score = 0

                for question_id, user_response in result_file.items():
                    user_options = user_response.split('|')
                    user_options_json = {option.strip(): value for option, value in zip(user_options, [5, 3, 1, -1])}

                    question_data = sjt_questions[int(question_id)]
                    
                    score = 0

                    for option in user_options:
                        correct_score = question_data['score'].get(option.strip(), 0)
                        given_score = user_options_json.get(option.strip(), 0)
                        score += (5 - abs(correct_score - given_score))  # Score = ∑(5−| X given − X correct |)

                    total_score += score
                    
                    for trait in question_data.get('traits', []):
                        trait_scores[trait]['score'] += score  # Update the score for the trait
                        category_scores[trait_scores[trait]['category']] += score  # Add score to the corresponding category

                    print(trait_scores)
                    print(category_scores)
                    print(score)
                    print("\n\n")

                print("Calculating Trait Score")

                try:
                    for trait in trait_scores:
                        if trait_scores[trait]['count'] > 0:
                            trait_scores[trait]['score'] = "{:.2f}".format(float(trait_scores[trait]['score']) / float(trait_scores[trait]['count']))  # Divide by count and format as .2f

                except ValueError as e:
                    print(f"Error converting trait scores to float: {e}")
                    return 0
                
                try:
                    category_scores['Agreeableness'] = "{:.2f}".format(float(category_scores['Agreeableness']) / 12)
                    category_scores['Conscientiousness'] = "{:.2f}".format(float(category_scores['Conscientiousness']) / 20)
                    category_scores['Extraversion'] = "{:.2f}".format(float(category_scores['Extraversion']) / 17)
                    category_scores['Neuroticism'] = "{:.2f}".format(float(category_scores['Neuroticism']) / 7)
                    category_scores['Openness'] = "{:.2f}".format(float(category_scores['Openness']) / 16)
                
                except ValueError as e:
                    print(f"Error converting category scores to float: {e}")
                    return 0

                
                return total_score / 20, trait_scores, category_scores
            
            print("Calculating Score")
            
            score, trait_scores, category_scores = calculate_score(result_file)

            print("Calculating Category Score")
            
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
                    ("Score", score) #between 0 to 20
                ]

                # if photo_base64:
                #     try:
                #         print("adding photo")
                #         if 'data:image/' in photo_base64:
                #             photo_base64 = photo_base64.split(',')[1]
                        
                #         photo_bytes = base64.b64decode(photo_base64)
                #         photo_image = Image.open(BytesIO(photo_bytes))
 
                #         if photo_image.mode != 'RGB':
                #             photo_image = photo_image.convert('RGB')
                        
                #         # Keep target size at 100x100
                #         target_size = (150, 150)
                #         original_width, original_height = photo_image.size
                        
                #         # Calculate dimensions to maintain aspect ratio
                #         ratio = min(target_size[0]/original_width, target_size[1]/original_height)
                #         new_size = (int(original_width*ratio), int(original_height*ratio))
                        
                #         # Use high-quality resampling with antialiasing
                #         resized_image = photo_image.resize(new_size, Image.Resampling.LANCZOS)

                #         temp_photo = BytesIO()
                #         # Save with maximum quality settings
                #         resized_image.save(temp_photo, format='PNG', optimize=False, quality=100)
                #         temp_photo.seek(0)
                        
                #         # Draw image with original dimensions
                #         c.drawImage(ImageReader(temp_photo), 400, 650, width=new_size[0], height=new_size[1], preserveAspectRatio=True)
                        
                #     except Exception as e:
                #         print(f"Error processing photo: {e}")
                
                y_position = 710
                for field, value in details:
                    c.drawString(100, y_position, field)
                    c.drawString(225, y_position, str(value))
                    y_position -= 15

                print("Category Scores")

                c.setFont("Helvetica-Bold", 16)
                c.drawString(100, 500, "Category Scores")
                
                # Define column positions for categories
                category_col = 100
                score_col = 300
                
                # Add headers
                c.setFont("Helvetica-Bold", 12)
                c.drawString(category_col, 475, "Category")
                c.drawString(score_col, 475, "Score")
                
                c.line(category_col, 470, 400, 470)
                
                y_position = 455
                c.setFont("Helvetica", 12)

                # Sort categories by score in descending order
                sorted_categories = sorted(
                    category_scores.items(),
                    key=lambda x: float(x[1]),
                    reverse=True
                )

                for category, score in sorted_categories:
                    # Draw category name
                    c.drawString(category_col, y_position, category)
                    
                    # Format score with exactly 2 decimal places and right-align
                    score_str = "{:.2f}".format(float(score))
                    score_width = c.stringWidth(score_str, "Helvetica", 12)
                    score_x = score_col + 50 - score_width  # Right-align within a 50-point width
                    c.drawString(score_x, y_position, score_str)
                    y_position -= 15
                
                c.showPage()

                print("Trait Scores")

                c.setFont("Helvetica-Bold", 16)
                c.drawString(100, 750, "Trait Scores")
                y_position = 735
                y_position -= 10
                
                # Define column positions
                trait_col = 100
                score_col = 300
                category_col = 400
                
                # Add headers
                c.setFont("Helvetica-Bold", 12)
                c.drawString(trait_col, y_position, "Trait")
                c.drawString(score_col, y_position, "Score")
                c.drawString(category_col, y_position, "Category")
                y_position -= 15

                c.line(trait_col, y_position + 10, 500, y_position + 10)
                y_position -= 5

                # Calculate maximum width needed for score alignment
                c.setFont("Helvetica", 12)
                max_score_width = max(
                    c.stringWidth("{:.2f}".format(float(details['score'])), "Helvetica", 12)
                    for details in trait_scores.values()
                )

                # Sort traits by category and then by score
                sorted_traits = sorted(
                    trait_scores.items(),
                    key=lambda x: (x[1]['category'], -float(x[1]['score']))
                )

                for trait, details in sorted_traits:
                    # Draw trait name
                    c.drawString(trait_col, y_position, trait)
                    
                    # Format score with exactly 2 decimal places and right-align
                    score = "{:.2f}".format(float(details['score']))
                    score_width = c.stringWidth(score, "Helvetica", 12)
                    score_x = score_col + 50 - score_width  # Right-align within a 50-point width
                    c.drawString(score_x, y_position, score)
                    
                    # Draw category
                    c.drawString(category_col, y_position, details['category'])
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

        return 1

    except Exception as e:
        print(f"Error in submit_sjt_test: {e}")
        return 0
    
if __name__ == "__main__":
    submit_sjt_test()