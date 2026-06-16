from dotenv import load_dotenv

load_dotenv()

from utils.azure_openai_client import call_azure_openai, get_config_status


config_status = get_config_status()
print(f"AZURE_OPENAI_API_KEY loaded: {config_status['loaded']}")
print(f"AZURE_OPENAI_API_KEY length: {config_status['length']}")
print(f"AZURE_OPENAI_API_KEY preview: {config_status['preview']}")
print(f"AZURE_OPENAI_API_KEY source: {config_status['source']}")
print(f"AZURE_OPENAI_ENDPOINT: {config_status['endpoint']}")
print(f"AZURE_OPENAI_DEPLOYMENT: {config_status['deployment']}")
print(f"AZURE_OPENAI_API_VERSION: {config_status['api_version']}")


reply = call_azure_openai(
    messages=[
        {"role": "user", "content": "Reply with exactly: AZURE OPENAI WORKING"}
    ],
    temperature=0,
)

print(reply)
