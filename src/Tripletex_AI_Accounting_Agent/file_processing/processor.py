import base64
import io
import logging

from google.genai import types

logger = logging.getLogger("file_processing")


def process_files(files: list[dict]) -> tuple[list[str], list[types.Part]]:
    """Process uploaded files. Returns (pdf_texts, image_parts)."""
    pdf_texts: list[str] = []
    image_parts: list[types.Part] = []

    for f in files:
        filename = f.get("filename", "")
        mime_type = f.get("mime_type", "")
        raw = base64.b64decode(f["content_base64"])

        logger.info(f"Processing file: {filename} ({mime_type}, {len(raw)} bytes)")

        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            text = extract_pdf_text(raw)
            if text.strip():
                pdf_texts.append(f"[File: {filename}]\n{text}")
                logger.info(f"Extracted {len(text)} chars from PDF")
            else:
                # PDF might be image-based, send as image to Gemini
                image_parts.append(types.Part.from_bytes(data=raw, mime_type="application/pdf"))

        elif mime_type.startswith("image/"):
            image_parts.append(types.Part.from_bytes(data=raw, mime_type=mime_type))
            logger.info(f"Added image part: {mime_type}")

        else:
            # Try as text
            try:
                text = raw.decode("utf-8")
                pdf_texts.append(f"[File: {filename}]\n{text}")
            except UnicodeDecodeError:
                logger.warning(f"Could not process file: {filename}")

    return pdf_texts, image_parts


def extract_pdf_text(data: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)

                # Also try extracting tables
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            pages.append(" | ".join(str(cell or "") for cell in row))

            return "\n\n".join(pages)
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return ""
