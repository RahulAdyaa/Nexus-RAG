import axios from 'axios';

export const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 120 seconds timeout (local Ollama models need more time)
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    console.log(`Making ${config.method.toUpperCase()} request to ${config.url}`);
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

export const uploadPDFs = async (files) => {
  const formData = new FormData();
  files.forEach(file => {
    formData.append('files', file);
  });

  try {
    const response = await api.post('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Upload failed');
  }
};

/**
 * Ask a question with streaming response.
 * Tokens appear word-by-word as the LLM generates them.
 * 
 * @param {object} questionData - The question request payload
 * @param {function} onToken - Called with each new token string
 * @param {function} onSources - Called with sources metadata
 * @param {function} onDone - Called when generation is complete
 * @param {function} onError - Called on error
 */
export const askQuestionStream = async (questionData, { onToken, onSources, onDone, onError }) => {
  try {
    const response = await fetch(`${API_BASE_URL}/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(questionData),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Server error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep incomplete line in buffer

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const data = JSON.parse(line);
          
          if (data.type === 'token' && data.content) {
            onToken(data.content);
          } else if (data.type === 'sources') {
            onSources(data);
          } else if (data.type === 'done') {
            onDone();
          } else if (data.type === 'error') {
            onError(new Error(data.content));
          }
        } catch (parseErr) {
          console.warn('Failed to parse stream chunk:', line);
        }
      }
    }

    // Process any remaining buffer
    if (buffer.trim()) {
      try {
        const data = JSON.parse(buffer);
        if (data.type === 'token') onToken(data.content);
        if (data.type === 'done') onDone();
      } catch (e) { /* ignore */ }
    }
  } catch (error) {
    onError(error);
  }
};

// Keep the non-streaming version as fallback
export const askQuestion = async (questionData) => {
  try {
    const response = await api.post('/ask', questionData);
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to get answer');
  }
};

export const getDocuments = async () => {
  try {
    const response = await api.get('/documents');
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to get documents');
  }
};

export const getStats = async () => {
  try {
    const response = await api.get('/stats');
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to get stats');
  }
};

export const deleteDocument = async (documentId) => {
  try {
    const response = await api.delete(`/documents/${documentId}`);
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to delete document');
  }
};

export const clearAllData = async () => {
  try {
    const response = await api.delete('/clear');
    return response.data;
  } catch (error) {
    throw new Error(error.response?.data?.detail || 'Failed to clear data');
  }
};

// Fetch suggestions based on chat history
export const fetchSuggestions = async (chatHistory) => {
  try {
    const response = await api.post('/ask/suggest', { chat_history: chatHistory });
    return response.data.suggestions;
  } catch (error) {
    console.error('Error fetching suggestions:', error);
    return [];
  }
};

export default api;
