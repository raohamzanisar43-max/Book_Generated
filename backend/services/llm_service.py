import openai
import warnings
try:
    from google import generativeai as genai
    GEMINI_AVAILABLE = True
    warnings.filterwarnings("ignore", category=FutureWarning)
except ImportError:
    GEMINI_AVAILABLE = False
from backend.database import settings

class LLMService:
    def __init__(self):
        if settings.OPENAI_API_KEY:
            openai.api_key = settings.OPENAI_API_KEY
        if settings.GEMINI_API_KEY and GEMINI_AVAILABLE:
            genai.configure(api_key=settings.GEMINI_API_KEY)

    async def generate_outline(self, title: str, notes_before: str) -> str:
        prompt = f"""
        Generate a detailed book outline for a book titled '{title}'.
        Editor's initial notes: {notes_before}
        
        Provide a list of chapters with a brief description for each.
        """
        return await self._call_llm(prompt)

    async def regenerate_outline(self, title: str, current_outline: str, feedback: str) -> str:
        prompt = f"""
        The current outline for the book '{title}' is:
        {current_outline}
        
        The editor has provided the following feedback for revision:
        {feedback}
        
        Please provide an improved version of the outline.
        """
        return await self._call_llm(prompt)

    async def generate_chapter(self, book_title: str, outline: str, chapter_num: int, previous_summaries: str, notes: str = None) -> str:
        prompt = f"""
        Book Title: {book_title}
        Full Outline: {outline}
        
        Context (Previous Chapter Summaries):
        {previous_summaries}
        
        Task: Write Chapter {chapter_num}.
        {'Editor feedback for this chapter: ' + notes if notes else ''}
        
        Ensure the chapter flows logically from the previous ones.
        """
        return await self._call_llm(prompt)

    async def regenerate_chapter(self, book_title: str, outline: str, chapter_num: int, current_content: str, previous_summaries: str, feedback: str) -> str:
        prompt = f"""
        Book Title: {book_title}
        Full Outline: {outline}
        
        Context (Previous Chapter Summaries):
        {previous_summaries}
        
        Current Chapter {chapter_num} Content:
        {current_content}
        
        The editor has provided the following feedback for revision:
        {feedback}
        
        Please provide an improved version of Chapter {chapter_num}.
        """
        return await self._call_llm(prompt)

    async def summarize_chapter(self, chapter_content: str) -> str:
        prompt = f"""
        Summarize the following chapter content in 3-5 sentences:
        {chapter_content}
        """
        return await self._call_llm(prompt)

    async def _call_llm(self, prompt: str) -> str:
        # Priority: OpenAI then Gemini
        if settings.OPENAI_API_KEY:
            try:
                response = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"OpenAI Error: {e}")
        
        if settings.GEMINI_API_KEY and GEMINI_AVAILABLE:
            try:
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                print(f"Gemini Error: {e}")
        
        return "LLM Service unavailable. Please check API keys."

llm_service = LLMService()
