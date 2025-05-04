import os
import asyncio
import json
import subprocess
from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_core.models import UserMessage
from autogen_agentchat.ui import Console
from autogen_agentchat.tools import Tool
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from autogen_agentchat.agents import AssistantAgent
import requests
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat

# Load environment variables
load_dotenv()

elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
stability_api_key = os.getenv("STABILITY_API_KEY")

# Define the voice ID for ElevenLabs (you need to specify one)
voice_id = "EXAVITQu4vr4xnSDxMaL"  # Example voice ID, replace with your preferred voice

ollama_client = OllamaChatCompletionClient(
    model="llama3.2",
)

# async def main():
#     result = await ollama_client.create([
#         UserMessage(content="What is the capital of France?", source="user")
#     ]) 
#     print(result.content)
           
# asyncio.run(main())

elevenlabs_client = ElevenLabs(api_key=elevenlabs_api_key)


def generate_voiceovers(messages: list[str]) -> list[str]:
    """
    Generate voiceovers for a list of messages using ElevenLabs API.
    
    Args:
        messages: List of messages to convert to speech
        
    Returns:
        List of file paths to the generated audio files
    """
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
            response = elevenlabs_client.text_to_speech.convert(
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


def generate_video(captions: list[str]):
    """
    Generate a video by combining images and voiceovers.
    
    Args:
        captions: List of captions to use for the video
    """
    print("Starting video generation process...")
    
    # Clean captions (remove non-alphanumeric characters except spaces)
    clean_captions = []
    for caption in captions:
        # Keep only alphanumeric characters and spaces
        clean_caption = ''.join(c for c in caption if c.isalnum() or c.isspace())
        clean_captions.append(clean_caption)
    
    # Generate voiceovers for the cleaned captions
    audio_paths = generate_voiceovers(clean_captions)
    if not audio_paths or len(audio_paths) != len(clean_captions):
        print("Failed to generate all required voiceovers.")
        return
    
    # Check if images exist
    image_paths = []
    for i in range(1, len(clean_captions) + 1):
        image_path = os.path.join("images", f"image_{i}.webp")
        if not os.path.exists(image_path):
            print(f"Image {image_path} not found. Cannot generate video without all images.")
            return
        image_paths.append(image_path)
    
    # Create output directory
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", "final_video.mp4")
    
    # Create temporary file list for FFmpeg
    with open("temp_file_list.txt", "w") as f:
        for i, (image_path, audio_path) in enumerate(zip(image_paths, audio_paths)):
            # Get audio duration using ffprobe
            duration_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                audio_path
            ]
            
            try:
                duration = float(subprocess.check_output(duration_cmd).decode('utf-8').strip())
                
                # Create individual segment
                segment_path = f"output/segment_{i+1}.mp4"
                
                # Generate video with image, audio, and caption overlay
                segment_cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", image_path,
                    "-i", audio_path,
                    "-vf", f"drawtext=text='{clean_captions[i]}':fontcolor=white:fontsize=60:box=1:boxcolor=black@0.5:boxborderw=10:x=(w-text_w)/2:y=h-text_h-50",
                    "-c:v", "libx264",
                    "-tune", "stillimage",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-pix_fmt", "yuv420p",
                    "-shortest",
                    "-t", str(duration),
                    segment_path
                ]
                
                subprocess.run(segment_cmd, check=True)
                
                # Add to file list
                f.write(f"file '{segment_path}'\n")
                
            except Exception as e:
                print(f"Error processing segment {i+1}: {e}")
                continue
    
    # Concatenate all segments
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", "temp_file_list.txt",
        "-c", "copy",
        output_path
    ]
    
    try:
        subprocess.run(concat_cmd, check=True)
        print(f"Video successfully generated at {output_path}")
    except Exception as e:
        print(f"Error concatenating video segments: {e}")
    
    # Clean up temporary file
    os.remove("temp_file_list.txt")
    
    return {"status": "success", "video_path": output_path}


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
    tools=[generate_voiceovers],  # Add the tool to the voice actor
    system_message='''
        You are a helpful agent tasked with generating and saving voiceovers.
        You will receive a list of captions from the script writer.
        Parse the JSON received from the script writer and extract ONLY the "captions" list.
        Use this list to generate voiceovers using the generate_voiceovers tool.
        Only respond with 'TERMINATE' once files are successfully saved locally.
    '''
)

graphic_designer = AssistantAgent(
    name="graphic_designer",
    model_client=ollama_client,
    tools=[generate_images],
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
    tools=[generate_video],
    system_message='''
        You are a helpful agent tasked with generating a short video.
        You are given a list of captions which you will use to create the short video.
        Remove any characters that are not alphanumeric or spaces from the captions.
        You will then use the captions list to generate a video.
        Only respond with 'TERMINATE' once the video is successfully generated and saved locally.
    '''
)


termination = TextMentionTermination("TERMINATE")


# Create the AutoGen team
agent_team = RoundRobinGroupChat(
    [script_writer, voice_actor, graphic_designer, director],
    termination_condition=termination,
    max_turns=12  # Increased from 4 to give more room for conversation
)


# Run the interactive loop
async def main():
    # Interactive console loop
    while True:
        user_input = input("Enter a message (type 'exit' to leave): ")
        if user_input.strip().lower() == "exit":
            break
        
        # Run the team with the user input and display results
        stream = agent_team.run_stream(task=user_input)
        await Console(stream)

# Run the main function
if __name__ == "__main__":
    asyncio.run(main())