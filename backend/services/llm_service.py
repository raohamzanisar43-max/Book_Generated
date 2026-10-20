"""LLM integration: prompt construction and provider dispatch (OpenAI, Gemini, mock).

Long chapters (e.g. 20 pages ≈ 9,000 words) exceed what a model reliably writes in a single
response, so chapters are produced in two steps:

1. ``plan_chapter``  - the chapter title and an ordered list of sections with a brief for each.
2. ``write_section`` - each section written separately (~SECTION_WORDS words), given the plan,
                       earlier chapter summaries and the end of the previous section for continuity.
"""
import logging
import random
import re
import textwrap
from typing import Callable, Optional

from backend.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an accomplished professional author and developmental editor. "
    "You write rich, engaging, publication-quality prose in Markdown: concrete examples, "
    "vivid detail, smooth transitions and varied sentence rhythm. You never pad, never repeat "
    "yourself, and you follow the editor's notes precisely while keeping the book consistent."
)

CHAPTER_HEADING_RE = re.compile(r"^\s*#*\s*\**\s*chapter\s+(\d+)\s*[:.\-–—]?\s*(.*?)\**\s*$", re.IGNORECASE)
PLAN_TITLE_RE = re.compile(r"^\s*\**\s*title\s*\**\s*[:\-–—]\s*(.+)$", re.IGNORECASE)
PLAN_SECTION_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+(.+)$")

Section = tuple[str, str]  # (heading, brief)


class LLMError(RuntimeError):
    """Raised when no configured provider could produce a completion."""


class LLMService:
    def __init__(self) -> None:
        self._openai_client = None
        self._gemini_client = None

    # ------------------------------------------------------------- outline
    def generate_outline(self, title: str, notes_before: str, chapters: int = 10) -> str:
        prompt = f"""
            Create a detailed outline for a book titled "{title}".

            Editor's notes (must be followed):
            {notes_before}

            The book will have exactly {chapters} chapters, each roughly 20 pages long, so every
            chapter needs enough substance for in-depth treatment.

            Format requirements:
            - Start with a 3-4 sentence synopsis under the heading "## Synopsis".
            - Then a "## Chapters" section listing exactly {chapters} chapters.
            - Each chapter MUST be on its own line in the form "Chapter N: <Title>",
              followed by 3-5 bullet points describing what it covers.
        """
        return self._complete(prompt, mock=lambda: _mock_outline(title, notes_before, chapters))

    def regenerate_outline(self, title: str, current_outline: str, feedback: str, chapters: int = 10) -> str:
        prompt = f"""
            The current outline for the book "{title}" is:

            {current_outline}

            The editor requested these revisions:
            {feedback}

            Produce the complete revised outline. Unless the editor asks otherwise, keep {chapters}
            chapters. Keep the same format: a "## Synopsis" section, then a "## Chapters" section where
            each chapter is a line "Chapter N: <Title>" followed by bullet points.
        """
        return self._complete(prompt, mock=lambda: _mock_outline(title, feedback, chapters, revised=True))

    # ------------------------------------------------------------ chapters
    def plan_chapter(
        self,
        book_title: str,
        outline: str,
        chapter_num: int,
        previous_summaries: str,
        sections: int,
        notes: Optional[str] = None,
        previous_plan: Optional[list[str]] = None,
    ) -> tuple[str, list[Section]]:
        revision = ""
        if notes:
            revision = f"\nThis is a REVISION. The editor's notes for this chapter: {notes}\n"
            if previous_plan:
                revision += "The previous draft's sections were: " + "; ".join(previous_plan) + "\n"
        prompt = f"""
            Book title: {book_title}

            Full outline:
            {outline}

            Summaries of the previous chapters:
            {previous_summaries or "This is the first chapter."}
            {revision}
            Plan Chapter {chapter_num} as exactly {sections} sections that together form one
            well-paced, ~{sections * settings.SECTION_WORDS:,}-word chapter (opening hook ->
            development -> resolution / transition to the next chapter).

            Respond in exactly this format and nothing else:
            TITLE: <chapter title, taken from the outline>
            1. <Section heading> — <one or two sentences on what this section covers>
            2. <Section heading> — <...>
            ... up to {sections}.
        """
        text = self._complete(
            prompt, mock=lambda: _mock_plan(book_title, outline, chapter_num, sections, notes)
        )
        title, plan = parse_chapter_plan(text)
        if not title:
            title = dict(parse_outline_chapters(outline)).get(chapter_num) or f"Chapter {chapter_num}"
        # Never trust the model's count blindly: pad or trim to the requested length.
        while len(plan) < sections:
            plan.append((f"Part {len(plan) + 1}", "Continue developing the chapter's themes."))
        return title, plan[:sections]

    def write_section(
        self,
        book_title: str,
        outline: str,
        chapter_num: int,
        chapter_title: str,
        plan: list[Section],
        index: int,
        previous_summaries: str,
        recent_text: str,
        words: int,
        notes: Optional[str] = None,
    ) -> str:
        heading, brief = plan[index]
        plan_text = "\n".join(
            f"{i + 1}. {h} — {b}{'   <-- WRITE THIS ONE' if i == index else ''}" for i, (h, b) in enumerate(plan)
        )
        position = (
            "This is the OPENING section: start with a strong hook that draws the reader in."
            if index == 0
            else "This is the FINAL section: bring the chapter to a satisfying close and set up the next chapter."
            if index == len(plan) - 1
            else "This is a middle section: do not conclude the chapter."
        )
        prompt = f"""
            Book title: {book_title}

            Full outline:
            {outline}

            Summaries of the previous chapters:
            {previous_summaries or "This is the first chapter."}

            Chapter {chapter_num}: {chapter_title}
            Section plan:
            {plan_text}

            The text immediately before this section:
            \"\"\"{recent_text[-3000:] if recent_text else "(none — this is the start of the chapter)"}\"\"\"
            {f"Editor notes to apply: {notes}" if notes else ""}

            Write section {index + 1}, "{heading}", in approximately {words} words.
            {position}
            - Continue seamlessly from the text above; do not repeat it or re-introduce the chapter.
            - Do NOT write the section heading or the chapter title — start directly with prose.
            - Use ### sub-headings, lists or examples only where they genuinely help the reader.
        """
        return self._complete(
            prompt, mock=lambda: _mock_section(book_title, chapter_num, heading, brief, index, words, notes)
        )

    def summarize_chapter(self, chapter_content: str) -> str:
        prompt = f"""
            Summarize the following chapter in 4-6 sentences. Capture key events, ideas, names and
            facts that later chapters must stay consistent with. Respond with the summary only.

            {chapter_content}
        """
        return self._complete(prompt, mock=lambda: _mock_summary(chapter_content))

    # ----------------------------------------------------------- providers
    def active_provider(self) -> str:
        if settings.LLM_PROVIDER != "auto":
            return settings.LLM_PROVIDER
        if settings.OPENAI_API_KEY:
            return "openai"
        if settings.GEMINI_API_KEY:
            return "gemini"
        return "none"

    def _provider_chain(self) -> list[str]:
        if settings.LLM_PROVIDER != "auto":
            return [settings.LLM_PROVIDER]
        chain = []
        if settings.OPENAI_API_KEY:
            chain.append("openai")
        if settings.GEMINI_API_KEY:
            chain.append("gemini")
        return chain

    def _complete(self, prompt: str, mock: Callable[[], str]) -> str:
        prompt = textwrap.dedent(prompt).strip()
        chain = self._provider_chain()
        if not chain:
            raise LLMError(
                "No LLM provider configured. Set OPENAI_API_KEY or GEMINI_API_KEY, "
                "or LLM_PROVIDER=mock for offline demos."
            )

        errors = []
        for provider in chain:
            try:
                if provider == "mock":
                    text = mock()
                elif provider == "openai":
                    text = self._call_openai(prompt)
                else:
                    text = self._call_gemini(prompt)
                if not text or not text.strip():
                    raise LLMError("empty response")
                return text.strip()
            except Exception as exc:  # noqa: BLE001 - try the next provider
                logger.warning("LLM provider %s failed: %s", provider, exc)
                errors.append(f"{provider}: {_short_error(exc)}")

        raise LLMError("All LLM providers failed — " + " | ".join(errors))

    def _call_openai(self, prompt: str) -> str:
        if self._openai_client is None:
            from openai import OpenAI

            self._openai_client = OpenAI(
                api_key=settings.OPENAI_API_KEY, timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=3
            )
        response = self._openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
        )
        return response.choices[0].message.content or ""

    def _call_gemini(self, prompt: str) -> str:
        from google.genai import types

        if self._gemini_client is None:
            from google import genai

            self._gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = self._gemini_client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.8),
        )
        return response.text or ""


# ---------------------------------------------------------------- parsing
def parse_outline_chapters(outline: str) -> list[tuple[int, str]]:
    """Extract (number, title) pairs from lines like 'Chapter 3: Title'."""
    found: dict[int, str] = {}
    for line in (outline or "").splitlines():
        match = CHAPTER_HEADING_RE.match(line.replace("*", ""))
        if match:
            number = int(match.group(1))
            found.setdefault(number, match.group(2).strip(" *#"))
    return sorted(found.items())


def parse_chapter_plan(text: str) -> tuple[str, list[Section]]:
    """Parse 'TITLE: ...' and numbered 'Heading — brief' lines from a chapter plan."""
    title, sections = "", []
    for line in (text or "").splitlines():
        if not title and (m := PLAN_TITLE_RE.match(line)):
            title = m.group(1).strip(" *#\"")
            title = CHAPTER_HEADING_RE.sub(lambda mm: mm.group(2), title).strip() or title
        elif m := PLAN_SECTION_RE.match(line):
            body = m.group(1).replace("**", "").strip()
            parts = re.split(r"\s+[—–-]\s+|:\s+", body, maxsplit=1)
            heading = parts[0].strip(" #\"")
            brief = parts[1].strip() if len(parts) > 1 else ""
            if heading:
                sections.append((heading, brief))
    return title, sections


def split_chapter_title(content: str, chapter_num: int) -> tuple[str, str]:
    """Split a leading '# Chapter N: Title' line off generated content."""
    lines = (content or "").strip().splitlines()
    if lines:
        match = CHAPTER_HEADING_RE.match(lines[0].replace("*", ""))
        if match and match.group(2).strip():
            return match.group(2).strip(" *#"), "\n".join(lines[1:]).strip()
    return f"Chapter {chapter_num}", (content or "").strip()


def count_words(text: Optional[str]) -> int:
    return len(re.findall(r"\b[\w'’-]+\b", text or ""))


def _short_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ")
    return f"{type(exc).__name__}: {text[:240]}"


# ---------------------------------------------------------- mock provider
# Deterministic but varied text so demos produce realistic, full-length documents offline.
_MOCK_TOPICS = [
    "Foundations", "The Landscape Today", "Core Principles", "Tools of the Trade",
    "Building in Practice", "Designing for Scale", "Common Pitfalls", "Case Studies",
    "Teams and Culture", "Measuring What Matters", "Ethics and Responsibility", "Looking Ahead",
]
_MOCK_SECTIONS = [
    "An Unexpected Beginning", "Why This Matters Now", "The First Principles", "A Closer Look",
    "Lessons From the Field", "Where Things Go Wrong", "A Better Approach", "Putting It to Work",
    "Voices of Experience", "The Bigger Picture", "Questions Worth Asking", "Bringing It Together",
]
_OPENERS = [
    "Consider what happens when {topic} meets the pressures of the real world.",
    "It is tempting to treat {topic} as a solved problem, but the evidence suggests otherwise.",
    "Few ideas in {book} have been as misunderstood as {topic}.",
    "The story of {topic} begins, as many good stories do, with a mistake.",
    "Ask ten practitioners about {topic} and you will hear eleven opinions.",
    "There is a quiet moment in every project when {topic} stops being theory and becomes practice.",
]
_SENTENCES = [
    "The difference between a good outcome and a great one usually lies in the details nobody wanted to examine.",
    "What looks like a technical decision is, more often than not, a decision about people and priorities.",
    "Teams that succeed here tend to share one habit: they make their assumptions explicit and test them early.",
    "A useful way to think about {topic} is as a series of small bets rather than one grand plan.",
    "Each choice narrows the options that follow, which is why the early ones deserve the most care.",
    "The cost of getting this wrong is rarely visible on day one; it compounds quietly over months.",
    "Experienced practitioners learn to recognise the warning signs long before the numbers confirm them.",
    "None of this requires heroics. It requires attention, patience and a willingness to revisit old conclusions.",
    "In practice, the most valuable artefact is often a short written record of why a decision was made.",
    "This is where {topic} earns its place: it turns vague intentions into commitments that can be measured.",
    "The organisations that thrive are not the ones that avoid failure, but the ones that fail cheaply and learn fast.",
    "It helps to separate what must be true from what we merely hope is true.",
    "Simplicity is not the absence of complexity but the result of having understood it.",
    "When the stakes are high, clarity of language becomes a form of risk management.",
    "Momentum matters: a modest improvement shipped today often beats a perfect one promised for next quarter.",
    "Feedback loops are the engine of progress, and their speed determines how quickly a team can learn.",
    "The people closest to the work usually know where the real problems are, if anyone thinks to ask them.",
    "Good tools amplify good judgement; they never replace it.",
    "Seen from a distance, the pattern is obvious. From inside a busy week, it is almost invisible.",
    "That tension, between speed and certainty, runs through every chapter of {book}.",
]
_EXAMPLES = [
    "Take the case of a mid-sized team that had spent six months on a plan nobody had tested.",
    "A product lead once described the turning point as the day they stopped arguing and started measuring.",
    "One engineer kept a simple notebook of every surprise the system produced; within a year it had become the team's most valuable document.",
    "A founder recalled how a single customer interview overturned an assumption the whole company had built upon.",
]


def _mock_outline(title: str, notes: str, chapters: int, revised: bool = False) -> str:
    focus = notes.strip().split(".")[0][:160]
    lines = [
        "## Synopsis",
        f"*{title}* is a practical, story-driven book. {focus}. Across {chapters} chapters it moves from "
        "first principles to hands-on practice and the road ahead."
        + (" This revision incorporates the latest editorial feedback." if revised else ""),
        "",
        "## Chapters",
    ]
    for i in range(1, chapters + 1):
        topic = _MOCK_TOPICS[i - 1] if i <= len(_MOCK_TOPICS) else f"Advanced Topics, Part {i - len(_MOCK_TOPICS)}"
        lines += [
            f"Chapter {i}: {topic}",
            f"- Introduces the key ideas of {topic.lower()} as they relate to {title}.",
            "- Grounds the discussion in concrete, relatable examples.",
            "- Ends with practical takeaways and a bridge to the next chapter.",
            "",
        ]
    return "\n".join(lines).strip()


def _mock_plan(book: str, outline: str, chapter_num: int, sections: int, notes: Optional[str]) -> str:
    title = dict(parse_outline_chapters(outline)).get(chapter_num, f"Part {chapter_num}")
    rng = random.Random(f"{book}-{chapter_num}-{notes}")
    headings = rng.sample(_MOCK_SECTIONS, k=min(sections, len(_MOCK_SECTIONS)))
    while len(headings) < sections:
        headings.append(f"Further Perspectives {len(headings) + 1}")
    lines = [f"TITLE: {title}"]
    lines += [f"{i}. {h} — How {title.lower()} plays out through '{h.lower()}'." for i, h in enumerate(headings, 1)]
    return "\n".join(lines)


def _mock_section(
    book: str, chapter_num: int, heading: str, brief: str, index: int, words: int, notes: Optional[str]
) -> str:
    rng = random.Random(f"{book}-{chapter_num}-{heading}-{index}-{notes}")
    topic = heading.lower()
    fill = lambda s: s.format(topic=topic, book=book)  # noqa: E731
    paragraphs, total = [], 0
    if notes and index == 0:
        paragraphs.append(f"> Editor's direction applied: {notes.strip()}")
    while total < words * 0.92:
        n = rng.randint(5, 8)
        sentences = [fill(rng.choice(_OPENERS))] + [fill(s) for s in rng.sample(_SENTENCES, k=n)]
        if rng.random() < 0.3:
            sentences.insert(2, rng.choice(_EXAMPLES))
        para = " ".join(sentences)
        paragraphs.append(para)
        total += count_words(para)
        if rng.random() < 0.12:
            paragraphs.append(
                "Three questions are worth asking at this point:\n\n"
                f"- What would have to be true for {topic} to succeed here?\n"
                "- Which assumption, if wrong, would hurt the most?\n"
                "- What is the smallest step that would tell us something new?"
            )
    if index == 0:
        paragraphs.append("*(Generated by the offline mock provider — configure a real LLM for production content.)*")
    return "\n\n".join(paragraphs)


def _mock_summary(content: str) -> str:
    headings = [ln.lstrip("# ").strip() for ln in content.splitlines() if ln.startswith("## ")][:4]
    covered = ", ".join(headings) if headings else "its core themes"
    return (
        f"This chapter works through {covered}. It explains why the topic matters, illustrates it with "
        "practical examples, and highlights common pitfalls. It closes by setting up the next chapter."
    )


llm_service = LLMService()
