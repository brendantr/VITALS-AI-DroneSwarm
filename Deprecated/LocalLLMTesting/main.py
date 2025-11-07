import ollama
import inquirer
import os
import configparser
import requests

config = configparser.ConfigParser()
config.read('config.cfg')
user_name = config['USER_SETTINGS']['name']

image_dir_path = config['PATHS']['image_dir_path']

output_dir_path = config['PATHS']['output_dir_path']

image_files = os.listdir(image_dir_path)

# Determine installed models
available_models = ollama.list()
model_list = available_models['models']
model_names = []
for model in model_list:
    model_names.append(model['name'])



questions = [
  inquirer.Checkbox('model_name',
                message="Select a model (Press space to select, enter to continue)",
                choices=model_names,
                
            ),
  inquirer.Editor('prompt', message="Provide a prompt"),
  inquirer.Confirm('use_image', message="Do you want to use an image?"),
  inquirer.List('image', message="Select an image", 
                choices=image_files,
                ignore=lambda x: not x['use_image']),
]
answers = inquirer.prompt(questions)
if answers['model_name'] == []:
    print("Error: no model selected, exiting...")
    exit()


for test in answers['model_name']:

    #find the model id
    model_id = ""
    for model in model_list:
        if model['name'] == test:
            model_id = model['model']
            break

    prompt = answers['prompt']
    

    print(test + ": "+ "Generating Response...")

    # Call the chat function
    if answers['use_image']:
        image_path = image_dir_path + answers['image']
        res = ollama.chat(
        model=model_id,
        messages=[
            {
                'role': 'user',
                'content': prompt,
                'images': [image_path]
            }
        ]
    )
    else:
        res = ollama.chat(
        model=model_id,
        messages=[
            {
                'role': 'user',
                'content': prompt,
            }
        ]
    )
   
    print("Model: " + test)
    print("Response:")
    print(res['message']['content'])
    print("Total time taken: " + str(res['total_duration'] / 1000000000) + " seconds")
    questions2 = [
        inquirer.Text(
        "score",
        message="Rate the response from 1 to 10",
        validate=lambda _, x: 1 <= int(x) <= 10,
    ),
    ]
    answers2 = inquirer.prompt(questions2)
    #Deprecated Local File Output
    # num_output_files = len(os.listdir(output_dir_path))
    # output_file_name = "output_" + str(num_output_files) + ".txt"
    # output_file_path = output_dir_path + output_file_name
    # with open(output_file_path, 'a') as f:
    #     f.write("User: " + user_name + "\n")
    #     f.write("Model: " + test + "\n")
    #     f.write("Prompt: " + prompt + "\n")
    #     if answers['use_image']:
    #         f.write("Image: " + image_path + "\n")
    #     else:
    #         f.write("Image: None\n")
    #     f.write("Response: " + res['message']['content'] + "\n")
    #     f.write("Total time taken: " + str(res['total_duration'] / 1000000000) + " seconds\n")
    #     f.write("Score: " + answers2['score'] + "\n")
    #     f.write("\n")
    #     f.close()
    # print("Output saved to: " + output_file_path + "\n")
    # print("----------------------------------------------------\n")
    if(answers['use_image']):
        imageCheck = requests.get('http://localhost:8800/api/upload/'+answers['image'])
        if imageCheck.status_code == 404:
            with open(image_dir_path + answers['image'], 'rb') as image_file:
                files = {'image': image_file}
                response = requests.post('http://localhost:8800/api/upload', files=files)
            new_image_name = response.json()['filename']
            os.rename(image_dir_path + answers['image'], image_dir_path + new_image_name)
        elif imageCheck.status_code == 200:
            new_image_name = answers['image']
        else:
            print("Error: Image upload failed, exiting...")
            exit()
    body = {
        
        "apikey": config['USER_SETTINGS']['API_KEY'],
        "model": test,
        "prompt": prompt,
        "image": new_image_name,
        "response": res['message']['content'],
        "time": res['total_duration'] / 1000000000,
        "score": answers2['score']
    
    }
    res = requests.post('http://localhost:8800/api/tests/', json = body )
    




