import re
from typing import List

# Common abbreviations that should NOT trigger a sentence split
ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st", "ave", "blvd",
    "vs", "etc", "incl", "approx", "dept", "est", "vol", "rev", "gen",
    "fig", "eq", "ref", "sec", "ch", "pt", "no", "al",  # academic
    "i.e", "e.g", "cf", "viz",  # Latin abbreviations
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "u.s", "u.k", "e.u",  # countries
}


class TextPreprocessor:
    def __init__(self):
        # Build abbreviation pattern for sentence splitting
        abbr_pattern = "|".join(re.escape(a) for a in sorted(ABBREVIATIONS, key=len, reverse=True))
        self._abbr_re = re.compile(rf'\b({abbr_pattern})\.', re.IGNORECASE)
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text extracted from PDFs"""
        # Remove page headers/footers that are just numbers
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        
        # Normalize unicode characters
        text = text.replace('\u2018', "'").replace('\u2019', "'")
        text = text.replace('\u201c', '"').replace('\u201d', '"')
        text = text.replace('\u2013', '-').replace('\u2014', '-')
        
        # Remove extra whitespace but preserve paragraph breaks
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove special characters but keep punctuation, math symbols, and brackets
        text = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\{\}\/\%\+\=\<\>\@\#\&\*\"\'°±×÷≤≥≠≈∞∑∏∫√]', '', text)
        
        # Remove multiple consecutive punctuation (but preserve ellipsis)
        text = re.sub(r'\.{4,}', '...', text)
        
        return text.strip()
    
    def split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using rule-based boundary detection.
        Handles abbreviations, decimal numbers, and academic citations correctly.
        """
        if not text.strip():
            return []
        
        # Step 1: Protect abbreviations by replacing their periods with a placeholder
        protected = self._abbr_re.sub(lambda m: m.group(0).replace('.', '__DOT__'), text)
        
        # Step 2: Protect decimal numbers (e.g., 3.14, 0.05)
        protected = re.sub(r'(\d)\.(\d)', r'\1__DOT__\2', protected)
        
        # Step 3: Protect common patterns like "et al.", "p < 0.05"
        protected = re.sub(r'\bal__DOT__', 'al__DOT__', protected)  # already handled
        
        # Step 4: Split on sentence-ending punctuation followed by space + uppercase
        # or end of string
        parts = re.split(r'(?<=[.!?])\s+(?=[A-Z\d\(\[])', protected)
        
        # Step 5: Restore protected periods
        sentences = []
        for part in parts:
            restored = part.replace('__DOT__', '.').strip()
            if restored and len(restored) > 5:  # Skip tiny fragments
                sentences.append(restored)
            elif sentences and restored:
                # Merge tiny fragments into the previous sentence
                sentences[-1] = sentences[-1] + " " + restored
        
        # If splitting produced nothing useful, return the whole text as one sentence
        if not sentences and text.strip():
            sentences = [text.strip()]
        
        return sentences
