import React, { useState, useCallback, useRef } from 'react';
import Upload from './components/Upload';
import ChatBox from './components/Chatbox';
import Answer from './components/Answer';
import Home from './pages/Home';
import DocumentSidebar from './components/DocumentSidebar';
import { fetchSuggestions } from './services/api';

function App() {
  const [currentPage, setCurrentPage] = useState('chat');
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [currentAnswer, setCurrentAnswer] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [chatHistory, setChatHistory] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [streamingAnswer, setStreamingAnswer] = useState(null);
  const [selectedDocuments, setSelectedDocuments] = useState([]);
  const [sidebarRefreshTrigger, setSidebarRefreshTrigger] = useState(0);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const chatBoxRef = useRef(null);

  const handleDocumentsLoaded = useCallback((docs) => {
    setTotalDocuments(docs.length);
  }, []);

  const handleUploadSuccess = (response) => {
    setUploadedFiles(prev => [...prev, response.files_processed]);
    setCurrentSession({
      session_id: response.session_id,
      uploaded_files: response.uploaded_files,
      upload_time: new Date().toISOString()
    });
    setSidebarRefreshTrigger(prev => prev + 1);
  };

  const handleStreamingUpdate = (question, partialAnswer, sources, isStreaming, confidence) => {
    setStreamingAnswer({ question, answer: partialAnswer, sources: sources || [], isStreaming, confidence });
  };

  const handleNewAnswer = async (question, answer) => {
    const newEntry = {
      id: Date.now(),
      question,
      answer: answer.answer,
      sources: answer.sources,
      confidence: answer.confidence,
      timestamp: new Date().toLocaleTimeString()
    };
    
    setChatHistory(prev => [newEntry, ...prev]);
    setCurrentAnswer({ ...answer, suggestions: null });
    setStreamingAnswer(null);
    
    const historyForSuggestions = [newEntry, ...chatHistory].reverse().flatMap(entry => [
      { role: "user", content: entry.question },
      { role: "assistant", content: entry.answer }
    ]);

    const suggestions = await fetchSuggestions(historyForSuggestions);
    setCurrentAnswer(prev => prev ? { ...prev, suggestions } : null);
  };

  const displayAnswer = streamingAnswer || currentAnswer;

  return (
    <div className="flex h-screen w-full bg-black text-zinc-100 overflow-hidden font-sans selection:bg-zinc-800">
      
      {/* Left Sidebar - Navigation & History */}
      <aside className="w-80 border-r border-zinc-800 flex flex-col bg-[#0A0A0A] shrink-0 z-20">
        <div className="p-6 border-b border-zinc-800">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-md bg-white text-black flex items-center justify-center">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight">Retriv</h1>
          </div>
          <p className="text-xs text-zinc-500 font-medium tracking-wide">RESEARCH ASSISTANT</p>
        </div>
        
        <div className="p-4 flex gap-2 border-b border-zinc-800">
          <button 
            onClick={() => setCurrentPage('chat')}
            className={`flex-1 py-2 rounded-md text-sm font-medium transition-all ${currentPage === 'chat' ? 'bg-zinc-800 text-white' : 'bg-transparent hover:bg-zinc-900 text-zinc-400'}`}
          >
            Chat
          </button>
          <button 
            onClick={() => setCurrentPage('home')}
            className={`flex-1 py-2 rounded-md text-sm font-medium transition-all ${currentPage === 'home' ? 'bg-zinc-800 text-white' : 'bg-transparent hover:bg-zinc-900 text-zinc-400'}`}
          >
            Dashboard
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
          {chatHistory.length === 0 && (
            <div className="text-center text-sm text-zinc-600 mt-10">No recent history</div>
          )}
          {chatHistory.map(entry => (
            <div 
              key={entry.id} 
              onClick={() => { setCurrentAnswer({ answer: entry.answer, sources: entry.sources, confidence: entry.confidence }); setStreamingAnswer(null); }}
              className="cursor-pointer p-3 rounded-md border border-transparent hover:border-zinc-800 hover:bg-zinc-900 transition-all group"
            >
              <div className="text-sm font-medium text-zinc-300 line-clamp-1 mb-1 group-hover:text-white transition-colors">{entry.question}</div>
              <div className="text-xs text-zinc-500 line-clamp-2">{entry.answer}</div>
            </div>
          ))}
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col relative h-full min-w-0 bg-black">
        {currentPage === 'chat' ? (
          <>
            <div className="flex-1 overflow-y-auto p-6 md:p-12 z-10 custom-scrollbar flex flex-col">
              {!displayAnswer ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center max-w-2xl mx-auto opacity-70">
                   <div className="w-16 h-16 rounded-xl border border-zinc-800 flex items-center justify-center mb-6">
                      <svg className="w-6 h-6 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                   </div>
                   <h2 className="text-2xl font-semibold mb-2 text-white tracking-tight">How can I help you today?</h2>
                   <p className="text-zinc-500">Ask a question about your uploaded documents or search the knowledge base.</p>
                </div>
              ) : (
                <div className="max-w-3xl mx-auto w-full animate-fade-in pb-8">
                  <Answer 
                    answer={displayAnswer.answer}
                    sources={displayAnswer.sources}
                    isStreaming={displayAnswer.isStreaming}
                    suggestions={displayAnswer.suggestions}
                    confidence={displayAnswer.confidence}
                    onSuggestionClick={(suggestion) => {
                      if (chatBoxRef.current) {
                        chatBoxRef.current.submitQuestion(suggestion);
                      }
                    }}
                  />
                </div>
              )}
            </div>
            
            {/* Chat Input */}
            <div className="p-6 z-10 bg-gradient-to-t from-black via-black to-transparent pt-12 border-t border-zinc-900/50">
              <div className="max-w-3xl mx-auto w-full">
                <ChatBox 
                  ref={chatBoxRef}
                  onNewAnswer={handleNewAnswer}
                  onStreamingUpdate={handleStreamingUpdate}
                  isLoading={isLoading}
                  setIsLoading={setIsLoading}
                  hasDocuments={uploadedFiles.length > 0 || totalDocuments > 0 || selectedDocuments.length > 0}
                  currentSession={currentSession}
                  chatHistory={chatHistory}
                  selectedDocuments={selectedDocuments}
                />
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 overflow-y-auto p-12 z-10 custom-scrollbar">
            <Home />
          </div>
        )}
      </main>

      {/* Right Sidebar - Upload & Document Management */}
      <aside className="w-80 border-l border-zinc-800 flex flex-col bg-[#0A0A0A] shrink-0 z-20">
        <div className="p-6 border-b border-zinc-800">
          <h2 className="text-xs font-semibold tracking-widest text-zinc-500 uppercase mb-4">
            Add Knowledge
          </h2>
          <Upload onUploadSuccess={handleUploadSuccess} />
        </div>
        <div className="flex-1 overflow-y-auto p-0">
           <DocumentSidebar 
             refreshTrigger={sidebarRefreshTrigger}
             onSelectionChange={setSelectedDocuments}
             onDocumentDeleted={() => setSidebarRefreshTrigger(prev => prev + 1)}
             onDocumentsLoaded={handleDocumentsLoaded}
           />
        </div>
      </aside>
      
    </div>
  );
}

export default App;
