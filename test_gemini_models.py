"""
Test Gemini API key and list available models
"""
from google import generativeai as genai
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

API_KEY = "AIzaSyAnp7N_nRdF4ahqwnvUEMgfgVwIRkLBhPs"

print("Testing Gemini API Key...")
print(f"API Key: {API_KEY[:20]}...")

try:
    genai.configure(api_key=API_KEY)
    print("\n[OK] API configured successfully")
    
    # List available models
    print("\nListing available models...")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"  - {m.name}")
    
except Exception as e:
    print(f"\n[ERROR] {e}")
