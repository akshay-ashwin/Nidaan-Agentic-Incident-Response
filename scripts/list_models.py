"""List Gemini models available to the key (prints names only, never the key)."""
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()
key = os.environ.get("GOOGLE_API_KEY")
if not key:
    raise SystemExit("GOOGLE_API_KEY not set (put it in .env)")

client = genai.Client(api_key=key)
for m in client.models.list():
    actions = m.supported_actions or []
    if "generateContent" in actions and "flash" in m.name.lower():
        print(m.name, "|", m.display_name, "|", m.version)
