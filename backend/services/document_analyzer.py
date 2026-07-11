from pathlib import Path


class DocumentAnalyzer:
    def extract_text(self, file_path):
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf(path)
        if suffix in {".docx", ".doc"}:
            import docx2txt

            return docx2txt.process(str(path)) or ""
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8", errors="ignore")
        return ""

    def summarize_for_context(self, uploaded_files, limit=9000):
        chunks = []
        for uploaded in uploaded_files:
            try:
                text = self.extract_text(uploaded.file.path)
            except Exception:
                text = ""
            if text.strip():
                chunks.append(f"File: {uploaded.original_name}\n{text.strip()[:3000]}")
        return "\n\n---\n\n".join(chunks)[:limit]

    def _extract_pdf(self, path):
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)
