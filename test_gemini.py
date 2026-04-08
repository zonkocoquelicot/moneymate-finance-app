#!/usr/bin/env python3
"""
Test script to verify your Gemini API key is working
Run this in your project folder: python test_gemini.py
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("="*60)
print("🧪 GEMINI API KEY TEST")
print("="*60)

# Step 1: Check if API key exists
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    print("❌ ERROR: GEMINI_API_KEY not found in .env file")
    print("\n📝 Create a .env file with:")
    print("GEMINI_API_KEY=your_api_key_here")
    exit(1)

print(f"✅ API Key found: {GEMINI_API_KEY[:10]}...{GEMINI_API_KEY[-5:]}")
print()

# Step 2: Try to import google.generativeai
try:
    import google.generativeai as genai
    print("✅ google.generativeai package installed")
except ImportError:
    print("❌ ERROR: google.generativeai not installed")
    print("\n📦 Install it with:")
    print("pip install google-generativeai")
    exit(1)

# Step 3: Configure the API
try:
    genai.configure(api_key=GEMINI_API_KEY)
    print("✅ API key configured")
except Exception as e:
    print(f"❌ ERROR configuring API: {e}")
    exit(1)

print()
print("="*60)
print("🚀 TESTING MODELS")
print("="*60)

# Step 4: List available models
try:
    print("\n📋 Listing available models...")
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            print(f"   ✓ {m.name}")
    
    if not available_models:
        print("⚠️ No models found (API might not be enabled)")
except Exception as e:
    print(f"❌ ERROR listing models: {e}")
    print("\n🔗 Please visit: https://aistudio.google.com/app/apikey")
    print("   And make sure to click 'Create API Key' or 'Enable API'")

print()
print("="*60)
print("💬 TESTING CONTENT GENERATION")
print("="*60)

# Step 5: Test each model
models_to_test = [
    'gemini-1.5-flash',
    'gemini-1.5-pro', 
    'gemini-pro',
    'models/gemini-1.5-flash',
    'models/gemini-pro'
]

test_prompt = "Say 'Hello' in one word."
success_model = None

for model_name in models_to_test:
    try:
        print(f"\n🔄 Testing: {model_name}")
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(test_prompt)
        print(f"   ✅ SUCCESS! Response: {response.text}")
        success_model = model_name
        break
    except Exception as e:
        print(f"   ❌ Failed: {str(e)[:80]}")

print()
print("="*60)
print("📊 SUMMARY")
print("="*60)

if success_model:
    print(f"✅ WORKING MODEL: {success_model}")
    print(f"\n💡 Update your app.py to use: '{success_model}'")
    print("\n✨ Your AI assistant should work now!")
else:
    print("❌ ALL MODELS FAILED")
    print("\n🔍 Troubleshooting steps:")
    print("   1. Check API key at: https://aistudio.google.com/app/apikey")
    print("   2. Click 'Create API Key' if you don't have one")
    print("   3. Make sure Gemini API is enabled")
    print("   4. Check if you have free quota remaining")
    print("   5. Wait a few minutes and try again")
    print("   6. Try generating a new API key")

print("="*60)