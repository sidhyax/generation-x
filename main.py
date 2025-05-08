import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from autogen_agentchat.agents import AssistantAgent
# from autogen_ext.models.ollama import OllamaChatCompletionClient
import requests
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from pydantic import BaseModel
from tools import generate_video
from autogen_core.tools import FunctionTool
import asyncio

load_dotenv()





elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
stability_api_key = os.getenv("STABILITY_API_KEY")
ollama_key = os.getenv("OLLAMA_KEY")

tts_client = ElevenLabs(api_key=elevenlabs_api_key)

# Define output structure for the script
class ScriptOutput(BaseModel):
    topic: str
    takeaway: str
    captions: list[str]
    
def generate_voiceovers(messages: list[str]) -> list[str]:
    """
    Generate voiceovers for a list of messages using ElevenLabs API.
    
    Args:
        messages: List of messages to convert to speech
        
    Returns:
        List of file paths to the generated audio files
    """
    
    voice_id : str = "2EiwWnXFnvU5JabPnv8n" # Choose from ElevenLabs
    os.makedirs("voiceovers", exist_ok=True)
    
    # Check for existing files first
    audio_file_paths = []
    for i in range(1, len(messages) + 1):
        file_path = f"voiceovers/voiceover_{i}.mp3"
        if os.path.exists(file_path):
            audio_file_paths.append(file_path)
            
    # If all files exist, return them
    if len(audio_file_paths) == len(messages):
        print("All voiceover files already exist. Skipping generation.")
        return audio_file_paths
        
    # Generate missing files one by one
    audio_file_paths = []
    for i, message in enumerate(messages, 1):
        try:
            save_file_path = f"voiceovers/voiceover_{i}.mp3"
            if os.path.exists(save_file_path):
                print(f"File {save_file_path} already exists, skipping generation.")
                audio_file_paths.append(save_file_path)
                continue

            print(f"Generating voiceover {i}/{len(messages)}...")
            
            # Generate audio with ElevenLabs
            response = tts_client.text_to_speech.convert(
                text=message,
                voice_id=voice_id, # Choose from ElevenLabs
                model_id="eleven_multilingual_v2",
                output_format="mp3_22050_32",
            )
            
            # Collect audio chunks
            audio_chunks = []
            for chunk in response:
                if chunk:
                    audio_chunks.append(chunk)
            
            # Save to file
            with open(save_file_path, "wb") as f:
                for chunk in audio_chunks:
                    f.write(chunk)
                        
            print(f"Voiceover {i} generated successfully")
            audio_file_paths.append(save_file_path)
        
        except Exception as e:
            print(f"Error generating voiceover for message: {message}. Error: {e}")
            continue
            
    return audio_file_paths


def generate_images(prompts: list[str]):
    """
    Generate images based on text prompts using Stability AI API.
    
    Args:
        prompts: List of text prompts to generate images from
    """
    seed = 42
    output_dir = "images"
    os.makedirs(output_dir, exist_ok=True)

    # API config
    stability_api_url = "https://api.stability.ai/v2beta/stable-image/generate/core"
    headers = {
        "Authorization": f"Bearer {stability_api_key}",
        "Accept": "image/*"
    }

    for i, prompt in enumerate(prompts, 1):
        print(f"Generating image {i}/{len(prompts)} for prompt: {prompt}")

        # Skip if image already exists
        image_path = os.path.join(output_dir, f"image_{i}.webp")
        if not os.path.exists(image_path):
            # Prepare request payload
            payload = {
                "prompt": (None, prompt),
                "output_format": (None, "webp"),
                "height": (None, "1920"),
                "width": (None, "1080"),
                "seed": (None, str(seed))
            }

            try:
                response = requests.post(stability_api_url, headers=headers, files=payload)
                if response.status_code == 200:
                    with open(image_path, "wb") as image_file:
                        image_file.write(response.content)
                    print(f"Image saved to {image_path}")
                else:
                    print(f"Error generating image {i}: {response.json()}")
            except Exception as e:
                print(f"Error generating image {i}: {e}")



generate_voiceovers_tool = FunctionTool(
    generate_voiceovers,
    description="Generate voiceovers for a list of messages using ElevenLabs API.",
    strict=True
)

generate_images_tool = FunctionTool(
    generate_images,
    description="Generate images based on text prompts using Stability AI API.",
    strict=True
)

generate_video_tool = FunctionTool(
    generate_video,
    description="Generate a YouTube Shorts-style video by combining images, voiceovers, and background music.",
    strict=True
)



async def main() -> None:
    
    ollama_client = OpenAIChatCompletionClient(
        model="llama3.2:latest",
        api_key=ollama_key, 
        response_format=ScriptOutput,
        base_url="http://localhost:11434/v1",
        model_info={
            "function_calling": True,
            "json_output": True,
            "vision": False,
            "family": "llama3",
            "structured_output": True,
        }
    )
    
    
    
    script_writer = AssistantAgent(
        
        name="script_writer",
        model_client=ollama_client,
        system_message='''
            You are a creative assistant tasked with writing a script for a short video. 
            The script should consist of captions designed to be displayed on-screen, with the following guidelines:
                1.	Each caption must be short and impactful (no more than 8 words) to avoid overwhelming the viewer.
                2.	The script should have exactly 5 captions, each representing a key moment in the story.
                3.	The flow of captions must feel natural, like a compelling voiceover guiding the viewer through the narrative.
                4.	Always start with a question or a statement that keeps the viewer wanting to know more.
                5.  You must also include the topic and takeaway in your response.
                6.  The caption values must ONLY include the captions, no additional meta data or information.

                Output your response in the following JSON format:
                {
                    "topic": "topic",
                    "takeaway": "takeaway",
                    "captions": [
                        "caption1",
                        "caption2",
                        "caption3",
                        "caption4",
                        "caption5"
                    ]
                }
        '''
    )
    
    
    voice_actor = AssistantAgent(
        name="voice_actor",
        model_client=ollama_client,
        tools=[generate_voiceovers_tool],
        system_message='''
            You are a helpful agent tasked with generating and saving voiceovers.
            Only respond with 'TERMINATE' once files are successfully saved locally.
        '''
    )
    
    
    graphic_designer = AssistantAgent(
        name="graphic_designer",
        model_client=ollama_client,
        tools=[generate_images_tool],
        system_message='''
            You are a helpful agent tasked with generating and saving images for a short video.
            You are given a list of captions.
            You will convert each caption into an optimized prompt for the image generation tool.
            Your prompts must be concise and descriptive and maintain the same style and tone as the captions while ensuring continuity between the images.
            Your prompts must mention that the output images MUST be in: "Abstract Art Style / Ultra High Quality." (Include with each prompt)
            You will then use the prompts list to generate images for each provided caption.
            Only respond with 'TERMINATE' once the files are successfully saved locally.
        '''
    )
    
    
    director = AssistantAgent(
        name="director",
        model_client=ollama_client,
        tools=[generate_video_tool],
        system_message='''
            You are a helpful agent tasked with generating a short video.
            You are given a list of captions which you will use to create the short video.
            Remove any characters that are not alphanumeric or spaces from the captions.
            You will then use the captions list to generate a video.
            Only respond with 'TERMINATE' once the video is successfully generated and saved locally.
        '''
    )
    
    
    # Set up termination condition
    termination = TextMentionTermination("TERMINATE")

    # Create the AutoGen team
    agent_team = RoundRobinGroupChat(
        [script_writer, voice_actor, graphic_designer, director],
        termination_condition=termination,
        max_turns=4
    )

    # Interactive console loop
    while True:
        user_input = input("Enter a message (type 'exit' to leave): ")
        if user_input.strip().lower() == "exit":
            break
        
        # Run the team with the user input and display results
        stream = agent_team.run_stream(task=user_input)
        await Console(stream)
    
asyncio.run(main())