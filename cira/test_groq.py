from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    response_format={ "type": "json_object" },
    messages=[
        {"role": "user", "content": "Reply with a JSON object containing the key 'message' and value 'GROQ WORKING'"}
    ]
)

print(response.choices[0].message.content)
