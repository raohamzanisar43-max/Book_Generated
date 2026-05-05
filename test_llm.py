import asyncio
from backend.services.llm_service import llm_service
from dotenv import load_dotenv
import os

async def test_llm():
    print("Testing LLM Service...")
    title = "The Future of AI Automation"
    notes = "The book should cover FastAPI, n8n, and agentic workflows."
    
    print(f"Generating outline for: {title}")
    try:
        outline = await llm_service.generate_outline(title, notes)
        print("\n--- Generated Outline ---")
        print(outline)
        print("\n--------------------------")
    except Exception as e:
        print(f"\n[ERROR] LLM test failed: {e}")
        print("Note: This may be due to API quota issues. The database connection is working.")

if __name__ == "__main__":
    load_dotenv()
    asyncio.run(test_llm())
