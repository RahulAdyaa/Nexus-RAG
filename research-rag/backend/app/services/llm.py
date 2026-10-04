import requests
import json
from typing import List, Dict, Optional, Generator
from app.utils.config import config


class LLMService:
    """
    Unified LLM service supporting both Ollama (local) and Gemini (cloud).
    
    Provider is controlled by the LLM_PROVIDER env var:
      - "ollama" (default): Uses a local Ollama model — free, no API key needed.
      - "gemini": Uses Google Gemini API — requires GEMINI_API_KEY.
    """
    
    def __init__(self):
        self.provider = config.LLM_PROVIDER  # "ollama", "gemini", or "groq"
        
        if self.provider == "gemini":
            self.api_key = config.GEMINI_API_KEY
            self.gemini_model = config.GEMINI_MODEL
            self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        elif self.provider == "groq":
            self.api_key = config.GROQ_API_KEY
            self.groq_model = config.GROQ_MODEL
            self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
            if not self.api_key:
                raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        elif self.provider == "openrouter":
            self.api_key = config.OPENROUTER_API_KEY
            self.openrouter_model = config.OPENROUTER_MODEL
            self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
            if not self.api_key:
                raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
        elif self.provider == "ollama":
            self.ollama_url = config.OLLAMA_URL
            self.ollama_model = config.OLLAMA_MODEL
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
        """Generate 2-3 alternative phrasings or keywords for query expansion"""
        prompt = f"""You are an expert research librarian. The user is searching a document database for: "{query}"
Generate exactly 2 alternative search queries that capture the same intent but use different academic/technical synonyms or related concepts to improve search recall.
Return ONLY a JSON array of 2 strings, e.g., ["query one", "query two"]. Do not include any other text."""
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
                queries = json.loads(json_str)
                if isinstance(queries, list):
                    return [str(q) for q in queries][:2]
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
2. For every claim, cite the source in brackets like [Source 1] or [Source 2, Page 5].
3. If the context does not contain enough information, say: "The provided documents do not contain sufficient information to answer this question."
4. Be concise but thorough. Use bullet points for multi-part answers.
5. Never speculate or infer beyond what the context explicitly states.

ANSWER:"""
        
        # Qwen3 supports /no_think to skip chain-of-thought — makes response 2-3x faster
        if self.provider == "ollama" and "qwen3" in self.ollama_model.lower():
            prompt = "/no_think\n" + prompt
        
        return prompt
    
    def _prepare_sources(self, chunks: List[Dict]) -> List[Dict]:
        """Prepare source information for the response"""
        sources = []
        seen_sources = set()
        
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            source_file = metadata.get("source_file", "Unknown")
            page_number = metadata.get("page_number", "Unknown")
            
            # Create unique identifier for source
            source_id = f"{source_file}_{page_number}"
            
            if source_id not in seen_sources:
                # Raw scores are usually logits (-10 to +10) if using a cross-encoder
                score = chunk.get("reranker_score", chunk.get("combined_score", chunk.get("score", 0.0)))
                
                # Convert logit to a 0-1 probability using sigmoid so the frontend can show it as a percentage
                if "reranker_score" in chunk:
                    import math
                    try:
                        score = 1.0 / (1.0 + math.exp(-score))
                    except OverflowError:
                        score = 0.0 if score < 0 else 1.0
                
                sources.append({
                    "source_file": source_file,
                    "page_number": page_number,
                    "chunk_text": chunk.get("text", "")[:200] + "..." if len(chunk.get("text", "")) > 200 else chunk.get("text", ""),
                    "relevance_score": score
                })
                seen_sources.add(source_id)
        
        # Sort by relevance score
        sources.sort(key=lambda x: x["relevance_score"], reverse=True)
        
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
        return re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL).strip()
    
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
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        response = requests.post(self.groq_url, headers=headers, json=data, timeout=120 if not stream else 10, stream=stream)
        
        if response.status_code != 200:
            raise Exception(f"Groq API error: {response.status_code} - {response.text}")
            
        if not stream:
            return response.json()
        return response
        
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


# Backward-compatible alias so existing imports don't break
GeminiLLMService = LLMService
