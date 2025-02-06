import json
import random
import os

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

def generate_questions():
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
      
generate_questions()