from docx import Document
import os

class BookCompiler:
    @staticmethod
    def compile_to_docx(title: str, chapters: list, output_path: str):
        doc = Document()
        doc.add_heading(title, 0)

        # Sort chapters by chapter_number
        sorted_chapters = sorted(chapters, key=lambda x: x['chapter_number'])

        for chapter in sorted_chapters:
            doc.add_heading(f"Chapter {chapter['chapter_number']}: {chapter['title']}", level=1)
            doc.add_paragraph(chapter['content'])
            doc.add_page_break()

        doc.save(output_path)
        return output_path

    @staticmethod
    def compile_to_txt(title: str, chapters: list, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"{title.upper()}\n\n")
            sorted_chapters = sorted(chapters, key=lambda x: x['chapter_number'])
            for chapter in sorted_chapters:
                f.write(f"Chapter {chapter['chapter_number']}: {chapter['title']}\n")
                f.write("-" * 20 + "\n")
                f.write(chapter['content'] + "\n\n")
        return output_path

compiler = BookCompiler()
