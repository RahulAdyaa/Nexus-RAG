import requests
import json
from typing import List, Dict, Optional, Generator
from app.utils.config import config
import concurrent.futures
import re

QUALITY_THRESHOLDS = {
    "well_supported_groundedness": 0.90,
    "low_supported_groundedness": 0.50,
    "required_citation_validity": 1.0,
    "high_relevance_score": 0.50,
    "low_relevance_score": 0.10,
}


class LLMService:
    """
    Unified LLM service supporting both Ollama (local) and Gemini (cloud).
    
    Provider is controlled by the LLM_PROVIDER env var:
      - "ollama" (default): Uses a local Ollama model — free, no API key needed.
      - "gemini": Uses Google Gemini API — requires GEMINI_API_KEY.
    """
    
    def __init__(self, provider_override=None, model_override=None):
        self.provider = provider_override or config.LLM_PROVIDER  # "ollama", "gemini", or "groq"
        
        if self.provider == "gemini":
            self.api_key = config.GEMINI_API_KEY
            self.gemini_model = model_override or config.GEMINI_MODEL
            self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        elif self.provider == "groq":
            self.api_key = config.GROQ_API_KEY
            self.groq_model = model_override or config.GROQ_MODEL
            self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
            if not self.api_key:
                raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        elif self.provider == "openrouter":
            self.api_key = config.OPENROUTER_API_KEY
            self.openrouter_model = model_override or config.OPENROUTER_MODEL
            self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
            if not self.api_key:
                raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
        elif self.provider == "ollama":
            self.ollama_url = config.OLLAMA_URL
            self.ollama_model = model_override or config.OLLAMA_MODEL
            # Verify Ollama is reachable
            try:
                requests.get(self.ollama_url, timeout=3)
            except requests.ConnectionError:
                raise ConnectionError(
                    f"Cannot reach Ollama at {self.ollama_url}. "
                    "Make sure Ollama is running ('ollama serve') and the URL is correct."
                )
        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {self.provider}. Must be 'ollama', 'gemini', 'groq', or 'openrouter'.")
        
        model_name = self.ollama_model if self.provider == "ollama" else (self.gemini_model if self.provider == "gemini" else (self.groq_model if self.provider == "groq" else self.openrouter_model))
        print(f"[LLM] Using provider: {self.provider} (model: {model_name})")
        
        # Instantiate a separate judge service if this is the main service
        if provider_override is None:
            if config.JUDGE_PROVIDER == self.provider and config.JUDGE_MODEL == model_name:
                print("[LLM] Warning: Judge model is the same as the answer model. This may cause bias.")
                self.judge_service = self
            else:
                self.judge_service = LLMService(provider_override=config.JUDGE_PROVIDER, model_override=config.JUDGE_MODEL)
        else:
            self.judge_service = None
    
    # ─── Non-streaming answer generation ──────────────────────────────
    
    def generate_answer(self, query: str, context_chunks: List[Dict], max_tokens: int = 1000, chat_history: List[Dict[str, str]] = None) -> Dict:
        """
        Generate answer using the configured LLM provider with retrieved context.
        
        Args:
            query: User's question
            context_chunks: List of relevant chunks from retrieval
            max_tokens: Maximum tokens in response
            
        Returns:
            Dict with answer and metadata
        """
        try:
            # Filter out irrelevant chunks (combined_score == 0 means no match in either index)
            relevant_chunks = self._filter_relevant_chunks(context_chunks)
            
            # Prepare context from chunks
            context = self._prepare_context(relevant_chunks)
            
            # Create prompt
            prompt = self._create_prompt(query, context, chat_history)
            
            # Call the appropriate provider
            if self.provider == "ollama":
                answer = self._call_ollama(prompt, max_tokens)
            elif self.provider == "groq":
                response = self._call_groq_api(prompt, max_tokens, stream=False)
                answer = self._extract_groq_answer(response)
            elif self.provider == "openrouter":
                response = self._call_openrouter_api(prompt, max_tokens, stream=False)
                answer = self._extract_openrouter_answer(response)
            else:
                response = self._call_gemini_api(prompt, max_tokens)
                answer = self._extract_gemini_answer(response)
                
            # Regex check for citations; retry once if missing
            import re
            if not re.search(r'\[Source \d+.*?\]', answer):
                print("[LLM] Missing citations in generated answer. Retrying once...")
                if self.provider == "ollama":
                    answer = self._call_ollama(prompt, max_tokens)
                elif self.provider == "groq":
                    response = self._call_groq_api(prompt, max_tokens, stream=False)
                    answer = self._extract_groq_answer(response)
                elif self.provider == "openrouter":
                    response = self._call_openrouter_api(prompt, max_tokens, stream=False)
                    answer = self._extract_openrouter_answer(response)
                else:
                    response = self._call_gemini_api(prompt, max_tokens)
                    answer = self._extract_gemini_answer(response)
            
            # Prepare sources (only relevant ones)
            sources = self._prepare_sources(relevant_chunks)
            
            return {
                "answer": answer,
                "sources": sources,
                "context_used": len(relevant_chunks),
                "confidence": self._calculate_confidence(relevant_chunks),
                "model": self.ollama_model if self.provider == "ollama" else (self.gemini_model if self.provider == "gemini" else (self.groq_model if self.provider == "groq" else self.openrouter_model)),
                "provider": self.provider,
                "success": True
            }
            
        except Exception as e:
            return {
                "answer": f"I apologize, but I encountered an error while processing your question: {str(e)}",
                "sources": [],
                "context_used": 0,
                "success": False,
                "error": str(e)
            }
    
    def generate_suggestions(self, chat_history: List[Dict[str, str]]) -> List[str]:
        """Generate 3 follow-up questions based on the chat history"""
        if not chat_history:
            return []
            
        history_text = "PREVIOUS CONVERSATION HISTORY:\n"
        for msg in chat_history[-5:]: # Keep last 5 messages
            role = "User" if msg.get("role") == "user" else "Assistant"
            history_text += f"{role}: {msg.get('content')}\n\n"
            
        prompt = f"""{history_text}
Based on the conversation history above, suggest exactly 3 concise follow-up questions the user might want to ask next to explore the topic further.
Return ONLY a valid JSON array of strings, like this: ["Question 1?", "Question 2?", "Question 3?"]
Do not include any other text, reasoning, or markdown formatting.
"""
        import re
        try:
            if self.provider == "ollama":
                answer = self._call_ollama(prompt, max_tokens=1500)
            elif self.provider == "groq":
                response = self._call_groq_api(prompt, max_tokens=1500, stream=False)
                answer = self._extract_groq_answer(response)
            elif self.provider == "openrouter":
                response = self._call_openrouter_api(prompt, max_tokens=1500, stream=False)
                answer = self._extract_openrouter_answer(response)
            else:
                response = self._call_gemini_api(prompt, max_tokens=1500)
                answer = self._extract_gemini_answer(response)
                
            # Extract JSON array using regex in case the model adds extra text
            match = re.search(r'\[(.*?)\]', answer, re.DOTALL)
            if match:
                json_str = "[" + match.group(1) + "]"
                suggestions = json.loads(json_str)
                if isinstance(suggestions, list):
                    return [str(s) for s in suggestions][:3]
            return []
        except Exception as e:
            print(f"Error generating suggestions: {e}")
            return []

    def expand_query(self, query: str) -> List[str]:
        """Generate 5-8 alternative phrasings or keywords for query expansion"""
        prompt = f"""You are an expert research librarian. The user is searching a document database for: "{query}"
Generate 6 alternative search questions that capture the same intent but use different academic/technical synonyms or related concepts to improve search recall.
Return ONLY a valid JSON array of 6 strings, e.g., ["question one?", "question two?", ...]. Do not include any other text or markdown formatting."""
        import re
        try:
            if self.provider == "ollama":
                answer = self._call_ollama(prompt, max_tokens=200)
            elif self.provider == "groq":
                response = self._call_groq_api(prompt, max_tokens=200, stream=False)
                answer = self._extract_groq_answer(response)
            elif self.provider == "openrouter":
                response = self._call_openrouter_api(prompt, max_tokens=200, stream=False)
                answer = self._extract_openrouter_answer(response)
            else:
                response = self._call_gemini_api(prompt, max_tokens=200)
                answer = self._extract_gemini_answer(response)
            
            match = re.search(r'\[(.*?)\]', answer, re.DOTALL)
            if match:
                json_str = "[" + match.group(1) + "]"
                try:
                    queries = json.loads(json_str)
                    if isinstance(queries, list):
                        return [str(q) for q in queries][:8]
                except json.JSONDecodeError:
                    pass
            return []
        except Exception as e:
            print(f"Error expanding query: {e}")
            return []

    # ─── Streaming answer generation ──────────────────────────────────
    
    def generate_answer_stream(self, query: str, context_chunks: List[Dict], max_tokens: int = 1000, chat_history: List[Dict[str, str]] = None) -> Generator:
        """
        Stream answer tokens as they are generated by the LLM.
        Yields JSON strings for Server-Sent Events (SSE).
        """
        # Filter out irrelevant chunks
        relevant_chunks = self._filter_relevant_chunks(context_chunks)
        
        # Prepare context and prompt
        context = self._prepare_context(relevant_chunks)
        prompt = self._create_prompt(query, context, chat_history)
        sources = self._prepare_sources(relevant_chunks)
        
        # Send sources metadata first
        yield json.dumps({
            "type": "sources",
            "sources": sources,
            "context_used": len(relevant_chunks),
            "confidence": self._calculate_confidence(relevant_chunks),
            "model": self.ollama_model if self.provider == "ollama" else (self.gemini_model if self.provider == "gemini" else (self.groq_model if self.provider == "groq" else self.openrouter_model)),
            "provider": self.provider
        }) + "\n"
        
        # Stream answer tokens
        if self.provider == "ollama":
            yield from self._stream_ollama(prompt, max_tokens)
        elif self.provider == "groq":
            yield from self._stream_groq(prompt, max_tokens)
        elif self.provider == "openrouter":
            yield from self._stream_openrouter(prompt, max_tokens)
        else:
            # Gemini doesn't stream easily via REST — fall back to non-streaming
            response = self._call_gemini_api(prompt, max_tokens)
            answer = self._extract_gemini_answer(response)
            yield json.dumps({"type": "token", "content": answer}) + "\n"
        
        # Send completion signal
        yield json.dumps({"type": "done"}) + "\n"
    
    # ─── Shared helpers ───────────────────────────────────────────────
    
    def _filter_relevant_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """
        Filter out irrelevant chunks dynamically.
        Cross-encoder scores are logits (often -10 to +10).
        Bi-encoder combined scores are 0.0 to 1.0.
        """
        if not chunks:
            return []
            
        relevant = []
        for c in chunks:
            if "reranker_score" in c:
                # Logit > -2 is usually vaguely relevant for MS-MARCO models
                if c["reranker_score"] > -2.0:
                    relevant.append(c)
            else:
                if c.get("combined_score", c.get("score", 0.0)) > 0.05:
                    relevant.append(c)
                    
        # If no chunks pass the filter, keep the top 1 anyway just in case
        if not relevant and chunks:
            return chunks[:1]
            
        return relevant
        
    def _calculate_confidence(self, chunks: List[Dict]) -> str:
        """Calculate a confidence level (High/Medium/Low) based on top scores"""
        if not chunks:
            return "Low"
            
        top_chunk = chunks[0]
        
        if "reranker_score" in top_chunk:
            score = top_chunk["reranker_score"]
            if score > 3.0: return "High"
            if score > 0.0: return "Medium"
            return "Low"
        else:
            score = top_chunk.get("combined_score", top_chunk.get("score", 0.0))
            if score > 0.7: return "High"
            if score > 0.4: return "Medium"
            return "Low"
    
    def _prepare_context(self, chunks: List[Dict]) -> str:
        """Prepare context string from retrieved chunks"""
        if not chunks:
            return "No relevant context found."
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            metadata = chunk.get("metadata", {})
            source_file = metadata.get("source_file", "Unknown")
            page_number = metadata.get("page_number", "Unknown")
            
            context_part = f"""[Source {i}: {source_file}, Page {page_number}]
{chunk.get("text", "")}"""
            context_parts.append(context_part)
        
        return "\n\n".join(context_parts)
    
    def _create_prompt(self, query: str, context: str, chat_history: List[Dict[str, str]] = None) -> str:
        """
        Create a well-structured prompt optimized for groundedness and faithfulness.
        Uses /no_think for Qwen3 to skip the internal reasoning step (2-3x faster).
        """
        history_text = ""
        if chat_history:
            history_text = "PREVIOUS CONVERSATION HISTORY:\n"
            for msg in chat_history[-5:]: # Keep last 5 messages
                role = "User" if msg.get("role") == "user" else "Assistant"
                history_text += f"{role}: {msg.get('content')}\n\n"

        prompt = f"""You are a research assistant answering questions strictly from provided PDF context.

{history_text}CONTEXT:
{context}

QUESTION: {query}

RULES:
1. Answer ONLY using information from the CONTEXT above. Do NOT use outside knowledge.
2. Every sentence must end with a citation. For every claim, cite the source in brackets. Use ONLY numbered format: [1], [2], etc. Map these numbers to the [Source X: ...] metadata provided above. Do not invent page numbers.
3. If the context does not contain enough information, say: "The provided documents do not contain sufficient information to answer this question."
4. Format your answer using clean Markdown. Use short paragraphs and bold text for key terms.
5. For mathematical expressions, ALWAYS use `$` for inline math and `$$` for block math. Do NOT use `\(` or `\[`.

EXAMPLE:
Question: What is the formula for the energy and when was it proposed?
Answer: The formula is $E = mc^2$ [1]. It was proposed in 1905 [2].

ANSWER:"""
        
        # Qwen3 supports /no_think to skip chain-of-thought — makes response 2-3x faster
        if self.provider == "ollama" and "qwen3" in self.ollama_model.lower():
            prompt = "/no_think\n" + prompt
        
        return prompt
    
    def _prepare_sources(self, chunks: List[Dict]) -> List[Dict]:
        """Prepare source information for the response"""
        sources = []
        
        for i, chunk in enumerate(chunks, 1):
            metadata = chunk.get("metadata", {})
            source_file = metadata.get("source_file", "Unknown")
            page_number = metadata.get("page_number", "Unknown")
            
            score = chunk.get("reranker_score", chunk.get("combined_score", chunk.get("score", 0.0)))
            
            if "reranker_score" in chunk:
                # The bge-reranker-base model loaded via sentence_transformers CrossEncoder 
                # already applies a sigmoid activation, returning a probability in [0, 1].
                score = score
            
            sources.append({
                "id": i,
                "source_file": source_file,
                "page_number": page_number,
                "chunk_text": chunk.get("text", "")[:200] + "..." if len(chunk.get("text", "")) > 200 else chunk.get("text", ""),
                "relevance_score": score
            })
            
        return sources
    
    # ─── Ollama provider ──────────────────────────────────────────────
    
    def _call_ollama(self, prompt: str, max_tokens: int) -> str:
        """Call local Ollama model (non-streaming)"""
        url = f"{self.ollama_url}/api/generate"
        
        data = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.95,
                "num_predict": max_tokens,
            }
        }
        
        response = requests.post(url, json=data, timeout=120)
        
        if response.status_code != 200:
            raise Exception(f"Ollama error: {response.status_code} - {response.text}")
        
        result = response.json()
        answer = result.get("response", "").strip()
        
        # Strip <think>...</think> blocks if present (Qwen3 sometimes adds them)
        answer = self._strip_think_tags(answer)
        
        if not answer:
            return "I couldn't generate a response. Please try rephrasing your question."
        
        return answer
    
    def _stream_ollama(self, prompt: str, max_tokens: int) -> Generator:
        """Stream tokens from Ollama"""
        url = f"{self.ollama_url}/api/generate"
        
        data = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.1,
                "top_p": 0.95,
                "num_predict": max_tokens,
            }
        }
        
        in_think_block = False
        
        with requests.post(url, json=data, timeout=120, stream=True) as response:
            if response.status_code != 200:
                yield json.dumps({"type": "error", "content": f"Ollama error: {response.status_code}"}) + "\n"
                return
            
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        
                        # Filter out <think>...</think> blocks from Qwen3
                        if "<think>" in token and "</think>" in token:
                            in_think_block = False
                            pre_think = token.split("<think>")[0]
                            post_think = token.split("</think>")[-1]
                            token = pre_think + post_think
                        elif "<think>" in token:
                            in_think_block = True
                            token = token.split("<think>")[0]
                        elif "</think>" in token:
                            in_think_block = False
                            token = token.split("</think>")[-1]
                        elif in_think_block:
                            continue
                        
                        if token:
                            yield json.dumps({"type": "token", "content": token}) + "\n"
                        
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
    
    def _strip_think_tags(self, text: str) -> str:
        """Remove <think>...</think> blocks from model output"""
        import re
        return re.sub(r'<think>.*?(?:</think>|$)\s*', '', text, flags=re.DOTALL).strip()
    
    # ─── Gemini provider ──────────────────────────────────────────────
    
    def _call_gemini_api(self, prompt: str, max_tokens: int) -> Dict:
        """Make API call to Gemini"""
        url = f"{self.gemini_url}?key={self.api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.1,  # Low temperature for factual responses
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": max_tokens,
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code != 200:
            raise Exception(f"Gemini API error: {response.status_code} - {response.text}")
        
        return response.json()
    
    def _extract_gemini_answer(self, response: Dict) -> str:
        """Extract answer text from Gemini response"""
        try:
            candidates = response.get("candidates", [])
            if not candidates:
                return "I couldn't generate a response. Please try rephrasing your question."
            
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            
            if not parts:
                return "I couldn't generate a response. Please try rephrasing your question."
            
            answer = parts[0].get("text", "").strip()
            
            if not answer:
                return "I couldn't generate a response. Please try rephrasing your question."
            
            return answer
            
        except Exception as e:
            return f"Error processing response: {str(e)}"
    
    # ─── Groq provider ────────────────────────────────────────────────
    
    def _call_groq_api(self, prompt: str, max_tokens: int, stream: bool = False) -> Dict:
        """Make API call to Groq using OpenAI-compatible REST endpoint"""
        import time
        import re
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if "120b" in self.groq_model.lower() or "20b" in self.groq_model.lower():
            data["reasoning_format"] = "hidden"
            
        import requests
        
        retries = 5
        for attempt in range(retries):
            response = requests.post(self.groq_url, headers=headers, json=data, timeout=120 if not stream else 10, stream=stream)
            
            if response.status_code == 429:
                match = re.search(r"try again in ([0-9.]+)s", response.text)
                if match:
                    wait_time = float(match.group(1)) + 1.0
                    print(f"[Judge] Rate limited by Groq API. Waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[Judge] Rate limited by Groq API. Waiting 10s...")
                    time.sleep(10)
                    continue
                    
            if response.status_code != 200:
                raise Exception(f"Groq API error: {response.status_code} - {response.text}")
                
            if not stream:
                return response.json()
            return response
            
        raise Exception("Groq API rate limit exhausted after 5 retries")
        
        
    def _extract_groq_answer(self, response: Dict) -> str:
        """Extract answer text from Groq non-streaming response"""
        try:
            choices = response.get("choices", [])
            if not choices:
                return "I couldn't generate a response. Please try rephrasing your question."
            
            answer = choices[0].get("message", {}).get("content", "").strip()
            
            if not answer:
                return "I couldn't generate a response. Please try rephrasing your question."
            
            return answer
            
        except Exception as e:
            return f"Error processing response: {str(e)}"
            
    def _stream_groq(self, prompt: str, max_tokens: int) -> Generator:
        """Stream tokens from Groq API (OpenAI compatible SSE stream)"""
        try:
            response = self._call_groq_api(prompt, max_tokens, stream=True)
            
            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices", [])
                            if choices:
                                token = choices[0].get("delta", {}).get("content", "")
                                if token:
                                    yield json.dumps({"type": "token", "content": token}) + "\n"
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield json.dumps({"type": "error", "content": f"Groq error: {str(e)}"}) + "\n"
    
    # ─── OpenRouter provider ──────────────────────────────────────────
    
    def _call_openrouter_api(self, prompt: str, max_tokens: int, stream: bool = False) -> Dict:
        """Make API call to OpenRouter"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "Research RAG"
        }
        
        data = {
            "model": self.openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        response = requests.post(self.openrouter_url, headers=headers, json=data, timeout=120 if not stream else 10, stream=stream)
        
        if response.status_code != 200:
            raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")
            
        if not stream:
            return response.json()
        return response
        
    def _extract_openrouter_answer(self, response: Dict) -> str:
        """Extract answer text from OpenRouter"""
        try:
            choices = response.get("choices", [])
            if not choices:
                return "I couldn't generate a response."
            
            content = choices[0].get("message", {}).get("content")
            answer = content.strip() if content else ""
            return answer if answer else "I couldn't generate a response."
        except Exception as e:
            return f"Error processing response: {str(e)}"
            
    def _stream_openrouter(self, prompt: str, max_tokens: int) -> Generator:
        """Stream tokens from OpenRouter API"""
        try:
            response = self._call_openrouter_api(prompt, max_tokens, stream=True)
            
            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices", [])
                            if choices:
                                token = choices[0].get("delta", {}).get("content", "")
                                if token:
                                    yield json.dumps({"type": "token", "content": token}) + "\n"
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield json.dumps({"type": "error", "content": f"OpenRouter error: {str(e)}"}) + "\n"

    # ─── Document summarization ───────────────────────────────────────
    
    def summarize_document(self, chunks: List[Dict], max_tokens: int = 500) -> Dict:
        """Generate a summary of document chunks"""
        try:
            if not chunks:
                return {
                    "summary": "No content available to summarize.",
                    "success": False
                }
            
            # Prepare content for summarization
            content = "\n\n".join([chunk.get("text", "") for chunk in chunks[:10]])  # Limit to first 10 chunks
            
            prompt = f"""Please provide a concise summary of the following document content:

CONTENT:
{content}

INSTRUCTIONS:
1. Provide a clear, structured summary
2. Highlight the main topics and key points
3. Keep the summary concise but informative
4. Use bullet points if appropriate

SUMMARY:"""
            
            if self.provider == "ollama":
                summary = self._call_ollama(prompt, max_tokens)
            elif self.provider == "groq":
                response = self._call_groq_api(prompt, max_tokens, stream=False)
                summary = self._extract_groq_answer(response)
            elif self.provider == "openrouter":
                response = self._call_openrouter_api(prompt, max_tokens, stream=False)
                summary = self._extract_openrouter_answer(response)
            else:
                response = self._call_gemini_api(prompt, max_tokens)
                summary = self._extract_gemini_answer(response)
            
            return {
                "summary": summary,
                "chunks_processed": len(chunks),
                "success": True
            }
            
        except Exception as e:
            return {
                "summary": f"Error generating summary: {str(e)}",
                "success": False,
                "error": str(e)
            }

    def evaluate_answer_quality(self, query: str, answer: str, sources: List[Dict]) -> Dict:
        """Evaluate the generated answer for groundedness, citations, and retrieval quality."""
        import asyncio
        import re
        
        # 1. Retrieval Relevance
        scores = [s.get("relevance_score", 0) for s in sources]
        if not scores:
            scores = [s.get("combined_score", s.get("score", 0)) for s in sources]
        
        # Use top-1 reranker score
        top_score = scores[0] if scores else 0
        avg_score = sum(scores) / len(scores) if scores else 0
            
        # 2. Source Evidence
        evidence_pages = list(set([f"{s.get('source_file')} Page {s.get('page_number')}" for s in sources]))
        
        # Split answer into claims (sentences)
        claims = [s.strip() for s in re.split(r'(?<=[.!?])\s+', answer) if len(s.strip()) > 10]
        if not claims:
            claims = [answer.strip()] if answer.strip() else []
            
        # Filter out refusal phrases from claims
        refusal_phrases = ["couldn't find any relevant information", "do not contain sufficient information", "does not contain sufficient information"]
        actual_claims = [c for c in claims if not any(p in c.lower() for p in refusal_phrases)]
        
        if not actual_claims and any(p in answer.lower() for p in refusal_phrases):
            return {
                "verdict": "Not found in document",
                "groundedness": {"supported": 0, "total": 0, "unsupported_claims": []},
                "citations": {"valid": 0, "total": 0},
                "retrieval": {"top": top_score, "avg": avg_score, "chunks_used": len(sources)},
                "evidence_pages": [],
                "answer_relevance": "N/A"
            }
        
        # Use actual claims for verification (skipping the refusal sentence if they also added facts)
        claims = actual_claims if actual_claims else claims

        context_text = "\n".join([f"[Source {s.get('id')}]: {s.get('chunk_text')}" for s in sources])

        def check_claim(claim: str):
            prompt = f"""Evaluate this claim against the CONTEXT.
            
CONTEXT:
{context_text}

CLAIM:
{claim}

INSTRUCTIONS:
Is this claim explicitly supported by the CONTEXT?
If NO, output exactly "UNSUPPORTED".
If YES, output a direct quote from the CONTEXT that supports it. Do not output anything else.
"""
            service = self.judge_service if hasattr(self, 'judge_service') and self.judge_service else self
            
            for attempt in range(2):
                try:
                    if service.provider == "ollama":
                        resp = service._call_ollama(prompt, 500)
                    elif service.provider == "groq":
                        print(f"[Judge] Calling Groq with model: {service.groq_model}")
                        max_toks = 2048 if "120b" in service.groq_model.lower() else 500
                        raw = service._call_groq_api(prompt, max_toks, stream=False)
                        choices = raw.get("choices", [])
                        if not choices:
                            raise Exception("Empty choices")
                        choice = choices[0]
                        if choice.get("finish_reason") == "length":
                            raise Exception("finish_reason length")
                        msg = choice.get("message", {})
                        content = msg.get("content", "")
                        if not content or not content.strip():
                            raise Exception("Empty content")
                        resp = content.strip()
                    elif service.provider == "openrouter":
                        resp = service._extract_openrouter_answer(service._call_openrouter_api(prompt, 500, stream=False))
                    else:
                        resp = service._extract_gemini_answer(service._call_gemini_api(prompt, 500))
                    
                    return (claim, resp.strip())
                except Exception as e:
                    if attempt == 1:
                        raise e
                    import time
                    time.sleep(1)

        async def run_checks():
            tasks = [asyncio.to_thread(check_claim, claim) for claim in claims]
            return await asyncio.gather(*tasks) if tasks else []
            
        try:
            results = asyncio.run(run_checks())
        except Exception as e:
            print(f"[Judge] Verification failed: {e}")
            return {
                "verdict": "Verification unavailable",
                "groundedness": {"supported": 0, "total": len(claims), "unsupported_claims": []},
                "citations": {"valid": 0, "total": answer.count("[")},
                "retrieval": {"top": top_score, "avg": avg_score, "chunks_used": len(sources)},
                "evidence_pages": evidence_pages,
                "answer_relevance": "N/A"
            }
        
        supported_claims = 0
        unsupported_list = []
        for claim, resp in results:
            if "UNSUPPORTED" in resp.upper() or not resp:
                unsupported_list.append(claim)
            else:
                supported_claims += 1

        total_claims = len(claims)
        groundedness_ratio = supported_claims / total_claims if total_claims > 0 else 1.0
        
        total_citations = answer.count("[")
        valid_citations = min(supported_claims, total_citations) if total_citations > 0 else (supported_claims if total_claims > 0 else 0)
        citation_validity = valid_citations / total_citations if total_citations > 0 else 1.0
        
        # 4. Overall Verdict (Worst tier across metrics)
        verdict = "Well supported"
        
        if citation_validity < QUALITY_THRESHOLDS["required_citation_validity"]:
            verdict = "Partially supported"
        if groundedness_ratio < QUALITY_THRESHOLDS["well_supported_groundedness"]:
            verdict = "Partially supported"
            
        if groundedness_ratio < QUALITY_THRESHOLDS["low_supported_groundedness"]:
            verdict = "Low support: verify manually"
            
        if supported_claims == 0 and total_claims > 0:
            verdict = "Not supported by document"
            
        return {
            "verdict": verdict,
            "groundedness": {
                "supported": supported_claims,
                "total": total_claims,
                "unsupported_claims": unsupported_list
            },
            "citations": {
                "valid": valid_citations,
                "total": total_citations if total_citations > 0 else total_claims
            },
            "retrieval": {
                "top": top_score,
                "avg": avg_score,
                "chunks_used": len(sources)
            },
            "evidence_pages": evidence_pages,
            "answer_relevance": "N/A"
        }

# Backward-compatible alias so existing imports don't break
GeminiLLMService = LLMService
