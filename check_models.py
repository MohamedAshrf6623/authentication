import google.generativeai as genai
import os

# ضع مفتاحك هنا للتجربة
API_KEY = "AIzaSyD5YdckMKRTWL5cPgPomXhl0__A6LQs4jA" 
genai.configure(api_key=API_KEY)

print("List of available models:")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"Error: {e}")
