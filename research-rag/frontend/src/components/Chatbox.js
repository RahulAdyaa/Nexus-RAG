import React, { useState, useEffect, forwardRef, useImperativeHandle } from 'react';
import { askQuestionStream } from '../services/api';

const ChatBox = forwardRef(({ onNewAnswer, onStreamingUpdate, onQualityUpdate, isLoading, setIsLoading, hasDocuments, currentSession, chatHistory = [], selectedDocuments = [] }, ref) => {
  const [question, setQuestion] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (error && (hasDocuments || selectedDocuments.length > 0)) {
      setError('');
    }
  }, [hasDocuments, selectedDocuments, error]);

  const submitQuestion = async (qText) => {
    if (!qText.trim()) { setError('Please enter a question'); return; }
    
    const effectiveHasDocuments = hasDocuments || (selectedDocuments && selectedDocuments.length > 0);
    if (!effectiveHasDocuments) { setError('Please upload some PDF documents first'); return; }

    setIsLoading(true);
    setError('');

    const currentQuestion = qText.trim();
    setQuestion('');

    let streamedAnswer = '';
    let sourcesData = { sources: [], context_used: 0 };

    if (onStreamingUpdate) onStreamingUpdate(currentQuestion, '', [], true, null);

    const formattedHistory = chatHistory.flatMap(entry => [
      { role: "user", content: entry.question },
      { role: "assistant", content: entry.answer }
    ]).reverse();

    let searchScope = "session";
    if (selectedDocuments && selectedDocuments.length > 0) searchScope = "selected";
    else if (!currentSession) searchScope = "all";

    const requestData = {
      question: currentQuestion,
      top_k: 5,
      bm25_weight: 0.5,
      embedding_weight: 0.5,
      search_scope: searchScope,
      session_id: currentSession?.session_id || null,
      selected_documents: selectedDocuments,
      chat_history: formattedHistory
    };

    await askQuestionStream(requestData, {
      onToken: (token) => {
        streamedAnswer += token;
        if (onStreamingUpdate) onStreamingUpdate(currentQuestion, streamedAnswer, sourcesData.sources, true, sourcesData.confidence);
      },
      onSources: (data) => {
        sourcesData = data;
        if (onStreamingUpdate) onStreamingUpdate(currentQuestion, streamedAnswer, data.sources, true, data.confidence);
      },
      onDone: () => {
        onNewAnswer(currentQuestion, {
          answer: streamedAnswer,
          sources: sourcesData.sources,
          context_used: sourcesData.context_used,
          confidence: sourcesData.confidence,
          success: true
        });
        setIsLoading(false);
      },
      onQuality: (qualityData) => {
        if (onQualityUpdate) onQualityUpdate(qualityData);
      },
      onError: (err) => {
        setError(`Failed to get answer: ${err.message}`);
        onNewAnswer(currentQuestion, {
          answer: `**Error:** ${err.message}`,
          sources: [],
          context_used: 0,
          confidence: 'Low',
          success: false
        });
        setIsLoading(false);
      }
    });
  };

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    submitQuestion(question);
  };

  useImperativeHandle(ref, () => ({
    submitQuestion
  }));

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="w-full relative group">
      
      <div className="relative bg-[#0A0A0A] border border-zinc-800 rounded-xl shadow-2xl flex flex-col p-2 transition-all group-focus-within:border-zinc-700">
        {/* Scope Indicators */}
        <div className="px-3 py-2 flex items-center justify-between text-[11px] font-medium text-zinc-500">
          <div className="flex items-center gap-2">
            <span className="flex h-1.5 w-1.5 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-zinc-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-zinc-500"></span>
            </span>
            {selectedDocuments && selectedDocuments.length > 0 ? (
              <span>Filtering {selectedDocuments.length} document(s)</span>
            ) : currentSession ? (
              <span>Session Search ({currentSession.uploaded_files.length} files)</span>
            ) : (
              <span>Searching Knowledge Base</span>
            )}
          </div>
          {isLoading && <span className="text-zinc-400 animate-pulse">Generating...</span>}
        </div>

        {/* Text Input */}
        <form onSubmit={handleSubmit} className="flex items-end gap-2 px-2 pb-1 relative">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            disabled={isLoading}
            className="question-input w-full bg-transparent border-0 text-zinc-100 text-[15px] placeholder-zinc-600 resize-none outline-none focus:ring-0 min-h-[50px] max-h-[200px] py-3 custom-scrollbar"
            rows="1"
            style={{ height: 'auto' }}
          />
          <button 
            type="submit" 
            disabled={isLoading || !question.trim()}
            className="mb-1 p-2.5 rounded-lg bg-white hover:bg-zinc-200 disabled:opacity-30 disabled:bg-white text-black transition-all shadow-sm flex-shrink-0 flex items-center justify-center"
          >
            {isLoading ? (
               <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
               </svg>
            ) : (
               <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 10l7-7m0 0l7 7m-7-7v18"></path></svg>
            )}
          </button>
        </form>

        {error && (
          <div className="mx-2 mt-2 p-2 bg-red-950/50 border border-red-900/50 rounded-md flex items-center gap-2 text-red-500 text-sm animate-fade-in">
             <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
             {error}
          </div>
        )}
      </div>
    </div>
  );
});

export default ChatBox;
