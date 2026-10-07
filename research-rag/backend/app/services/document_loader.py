import fitz  # PyMuPDF
from typing import List, Dict
import os
import subprocess

try:
    import docx
except ImportError:
    pass

class DocumentLoader:
    def __init__(self):
        pass
        
    def extract_text_from_pdf(self, pdf_path: str, original_filename: str) -> List[Dict]:
        doc = fitz.open(pdf_path)
        pages_data = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            if text.strip():
                pages_data.append({
                    "page_number": page_num + 1,
                    "text": text,
                    "source_file": original_filename
                })
        doc.close()
        return pages_data

    def extract_text_from_txt(self, txt_path: str, original_filename: str) -> List[Dict]:
        with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        if text.strip():
            return [{
                "page_number": 1,
                "text": text,
                "source_file": original_filename
            }]
        return []

    def extract_text_from_docx(self, docx_path: str, original_filename: str) -> List[Dict]:
        try:
            doc = docx.Document(docx_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            if text.strip():
                return [{
                    "page_number": 1,
                    "text": text,
                    "source_file": original_filename
                }]
        except Exception as e:
            print(f"Error reading docx: {e}")
        return []

    def extract_text_from_doc(self, doc_path: str, original_filename: str) -> List[Dict]:
        # Try macOS textutil first
        try:
            result = subprocess.run(['textutil', '-convert', 'txt', doc_path, '-stdout'], capture_output=True, text=True, check=True)
            text = result.stdout
            if text.strip():
                return [{
                    "page_number": 1,
                    "text": text,
                    "source_file": original_filename
                }]
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try antiword on Linux
            try:
                result = subprocess.run(['antiword', doc_path], capture_output=True, text=True, check=True)
                text = result.stdout
                if text.strip():
                    return [{
                        "page_number": 1,
                        "text": text,
                        "source_file": original_filename
                    }]
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"Failed to read .doc file {original_filename}. Please install textutil or antiword.")
        return []
        
    def extract_text(self, file_path: str, original_filename: str = None) -> List[Dict]:
        source_filename = original_filename if original_filename else os.path.basename(file_path)
        ext = source_filename.lower().split('.')[-1]
        
        if ext == 'pdf':
            return self.extract_text_from_pdf(file_path, source_filename)
        elif ext == 'txt':
            return self.extract_text_from_txt(file_path, source_filename)
        elif ext == 'docx':
            return self.extract_text_from_docx(file_path, source_filename)
        elif ext == 'doc':
            return self.extract_text_from_doc(file_path, source_filename)
        else:
            print(f"Unsupported file format: {ext}")
            return []
