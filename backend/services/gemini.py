import google.generativeai as genai
import asyncio

def configure_genai(api_key):
    genai.configure(api_key=api_key)

async def list_models(api_key):
    configure_genai(api_key)
    # list_models returns an iterator, convert to list in thread
    return await asyncio.to_thread(list, genai.list_models())

async def generate_content(api_key, model_name, contents, generation_config=None):
    configure_genai(api_key)
    model = genai.GenerativeModel(model_name)
    response = await model.generate_content_async(contents, generation_config=generation_config)
    return response
