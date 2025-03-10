import json

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

print(f'Total Score: {score}')
print(f'Trait Scores: \n{trait_scores}')
print('Category Scores: \n' + ', '.join(f'{key}: {value:.2f}' for key, value in category_scores.items()))



