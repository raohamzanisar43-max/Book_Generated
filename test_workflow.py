"""
Comprehensive workflow test script for the Automated Book Generation System.
This script tests the complete workflow from book creation to compilation.
"""

import asyncio
import httpx
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

class WorkflowTester:
    def __init__(self):
        self.book_id = None
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def close(self):
        await self.client.aclose()
    
    async def print_response(self, step_name: str, response: Dict[str, Any]):
        print(f"\n{'='*60}")
        print(f"STEP: {step_name}")
        print(f"{'='*60}")
        print(json.dumps(response, indent=2, default=str))
    
    async def test_create_book(self):
        """Test Stage 1: Create book with required notes"""
        print("\n📚 Testing Book Creation...")
        
        payload = {
            "title": "The Future of AI Automation",
            "notes_on_outline_before": "Focus on FastAPI, n8n, and agentic workflows. Include practical examples and real-world use cases."
        }
        
        response = await self.client.post(f"{BASE_URL}/books/", json=payload)
        data = response.json()
        
        if response.status_code == 200:
            self.book_id = data.get('id')
            await self.print_response("Book Created Successfully", data)
            return True
        else:
            print(f"❌ Failed to create book: {data}")
            return False
    
    async def test_get_book(self):
        """Test retrieving book details"""
        print("\n📖 Testing Get Book...")
        
        response = await self.client.get(f"{BASE_URL}/books/{self.book_id}")
        data = response.json()
        
        if response.status_code == 200:
            await self.print_response("Book Retrieved", data)
            return True
        else:
            print(f"❌ Failed to get book: {data}")
            return False
    
    async def test_outline_feedback_approve(self):
        """Test approving outline"""
        print("\n✅ Testing Outline Approval...")
        
        payload = {
            "notes": "Outline looks good, proceed with chapters.",
            "status": "no_notes_needed"
        }
        
        response = await self.client.post(
            f"{BASE_URL}/books/{self.book_id}/outline-feedback",
            json=payload
        )
        data = response.json()
        
        if response.status_code == 200:
            await self.print_response("Outline Approved", data)
            return True
        else:
            print(f"❌ Failed to approve outline: {data}")
            return False
    
    async def test_generate_chapter_1(self):
        """Test generating first chapter"""
        print("\n✍️  Testing Chapter 1 Generation...")
        
        response = await self.client.post(f"{BASE_URL}/books/{self.book_id}/chapters/generate")
        data = response.json()
        
        if response.status_code == 200:
            await self.print_response("Chapter 1 Generated", data)
            return True
        else:
            print(f"❌ Failed to generate chapter: {data}")
            return False
    
    async def test_get_chapter(self, chapter_num: int):
        """Test retrieving chapter details"""
        print(f"\n📄 Testing Get Chapter {chapter_num}...")
        
        response = await self.client.get(
            f"{BASE_URL}/books/{self.book_id}/chapters/{chapter_num}"
        )
        data = response.json()
        
        if response.status_code == 200:
            await self.print_response(f"Chapter {chapter_num} Retrieved", data)
            return True
        else:
            print(f"❌ Failed to get chapter: {data}")
            return False
    
    async def test_chapter_feedback_approve(self, chapter_num: int):
        """Test approving chapter"""
        print(f"\n✅ Testing Chapter {chapter_num} Approval...")
        
        payload = {
            "notes": "Chapter looks good, proceed.",
            "status": "no_notes_needed"
        }
        
        response = await self.client.post(
            f"{BASE_URL}/books/{self.book_id}/chapters/{chapter_num}/feedback",
            json=payload
        )
        data = response.json()
        
        if response.status_code == 200:
            await self.print_response(f"Chapter {chapter_num} Approved", data)
            return True
        else:
            print(f"❌ Failed to approve chapter: {data}")
            return False
    
    async def test_generate_chapter_2(self):
        """Test generating second chapter (with context from chapter 1)"""
        print("\n✍️  Testing Chapter 2 Generation (with context)...")
        
        response = await self.client.post(f"{BASE_URL}/books/{self.book_id}/chapters/generate")
        data = response.json()
        
        if response.status_code == 200:
            await self.print_response("Chapter 2 Generated", data)
            return True
        else:
            print(f"❌ Failed to generate chapter: {data}")
            return False
    
    async def test_final_review(self):
        """Test final review approval"""
        print("\n🔍 Testing Final Review...")
        
        payload = {
            "notes": "All chapters look good, ready for compilation.",
            "status": "no_notes_needed"
        }
        
        response = await self.client.post(
            f"{BASE_URL}/books/{self.book_id}/final-review",
            json=payload
        )
        data = response.json()
        
        if response.status_code == 200:
            await self.print_response("Final Review Approved", data)
            return True
        else:
            print(f"❌ Failed final review: {data}")
            return False
    
    async def test_compile_book(self):
        """Test compiling book to .docx"""
        print("\n📦 Testing Book Compilation...")
        
        response = await self.client.post(f"{BASE_URL}/books/{self.book_id}/compile")
        data = response.json()
        
        if response.status_code == 200:
            await self.print_response("Book Compiled Successfully", data)
            return True
        else:
            print(f"❌ Failed to compile book: {data}")
            return False
    
    async def run_full_workflow(self):
        """Run the complete workflow test"""
        print("\n" + "="*60)
        print("STARTING COMPLETE WORKFLOW TEST")
        print("="*60)
        
        try:
            # Stage 1: Create Book
            if not await self.test_create_book():
                return False
            
            if not await self.test_get_book():
                return False
            
            # Stage 2: Approve Outline
            if not await self.test_outline_feedback_approve():
                return False
            
            # Stage 3: Generate Chapter 1
            if not await self.test_generate_chapter_1():
                return False
            
            if not await self.test_get_chapter(1):
                return False
            
            # Stage 4: Approve Chapter 1
            if not await self.test_chapter_feedback_approve(1):
                return False
            
            # Stage 5: Generate Chapter 2 (with context)
            if not await self.test_generate_chapter_2():
                return False
            
            if not await self.test_get_chapter(2):
                return False
            
            # Stage 6: Approve Chapter 2
            if not await self.test_chapter_feedback_approve(2):
                return False
            
            # Stage 7: Final Review
            if not await self.test_final_review():
                return False
            
            # Stage 8: Compile Book
            if not await self.test_compile_book():
                return False
            
            print("\n" + "="*60)
            print("✅ ALL TESTS PASSED!")
            print("="*60)
            return True
            
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False

async def main():
    tester = WorkflowTester()
    
    try:
        success = await tester.run_full_workflow()
        
        if success:
            print("\n🎉 Workflow test completed successfully!")
            print(f"Book ID: {tester.book_id}")
            print("Check the 'exports' folder for the compiled .docx file.")
        else:
            print("\n⚠️  Workflow test failed. Check the errors above.")
            
    finally:
        await tester.close()

if __name__ == "__main__":
    print("Make sure the FastAPI server is running on http://localhost:8000")
    print("Press Enter to start the test...")
    input()
    
    asyncio.run(main())
