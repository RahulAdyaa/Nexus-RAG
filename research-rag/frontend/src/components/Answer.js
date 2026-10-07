import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { API_BASE_URL } from '../services/api';

const Answer = ({ answer, sources, isStreaming, suggestions, confidence, quality, onSuggestionClick }) => {
  const [showSources, setShowSources] = useState(false);
  const [showQuality, setShowQuality] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(answer || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      const textArea = document.createElement("textarea");
      textArea.value = answer || '';
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (e) {
        console.error("Copy failed", e);
      }
      document.body.removeChild(textArea);
    }
  };



  const getVerdictColor = (verdict) => {
    if (!verdict) return 'text-zinc-400 bg-zinc-800 border-zinc-700';
    if (verdict.includes('Well supported')) return 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20';
    if (verdict.includes('Partially supported')) return 'text-amber-400 bg-amber-400/10 border-amber-400/20';
    if (verdict.includes('Not found in document')) return 'text-zinc-400 bg-zinc-400/10 border-zinc-400/20';
    if (verdict.includes('Not supported by document')) return 'text-rose-400 bg-rose-400/10 border-rose-400/20';
    return 'text-red-400 bg-red-400/10 border-red-400/20';
  };

  const renderQualityPanel = () => {
    if (isStreaming) return null;
    if (!quality) {
      return (
        <div className="flex items-center gap-2 text-xs text-zinc-500 animate-pulse mt-4 pt-3 border-t border-zinc-800 px-1">
          <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
          Analyzing answer quality...
        </div>
      );
    }

    const { verdict, groundedness, citations, retrieval, evidence_pages } = quality;
    const isErrorOrNotFound = verdict === "Not found in document";

    return (
      <div className="mt-4 pt-3 border-t border-zinc-800">
        <div 
          className="flex flex-wrap items-center justify-between cursor-pointer group"
          onClick={() => setShowQuality(!showQuality)}
        >
          <div className="flex flex-wrap items-center gap-3">
            <div className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border uppercase tracking-wider ${getVerdictColor(verdict)}`}>
              {verdict}
            </div>
            
            {!isErrorOrNotFound && (
              <div className="text-xs text-zinc-400 flex items-center gap-2">
                <span>{groundedness?.supported}/{groundedness?.total} claims</span>
                <span className="w-1 h-1 rounded-full bg-zinc-700"></span>
                <span>{evidence_pages?.length} pages</span>
              </div>
            )}
          </div>
          <button className="text-zinc-500 group-hover:text-zinc-300">
            <svg className={`w-4 h-4 transition-transform ${showQuality ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" /></svg>
          </button>
        </div>

        {showQuality && !isErrorOrNotFound && (
          <div className="mt-4 space-y-4 bg-zinc-900/50 p-4 rounded-xl border border-zinc-800/50">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <h5 className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 mb-2">Groundedness</h5>
                <div className="text-xs text-zinc-300">
                  <span className="font-semibold text-white">{groundedness.supported} of {groundedness.total}</span> claims are explicitly supported by retrieved context.
                </div>
                {groundedness.unsupported_claims?.length > 0 && (
                  <div className="mt-2 text-xs text-rose-400 bg-rose-400/10 p-2 rounded border border-rose-400/20">
                    <span className="font-semibold block mb-1">Unsupported Claims:</span>
                    <ul className="list-disc pl-4 space-y-1">
                      {groundedness.unsupported_claims.map((claim, i) => (
                        <li key={i}>{claim}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              <div>
                <h5 className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 mb-2">Retrieval & Citations</h5>
                <div className="space-y-1.5 text-xs text-zinc-300">
                  <div className="flex justify-between">
                    <span className="text-zinc-400">Citations Valid:</span>
                    <span className="font-semibold">{citations.valid} / {citations.total}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-400">Top Retrieval match:</span>
                    <span className="font-semibold">{(retrieval.top * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-400">Avg Retrieval match:</span>
                    <span className="font-semibold">{(retrieval.avg * 100).toFixed(0)}%</span>
                  </div>
                  {retrieval.top < 0.10 && (
                    <div className="mt-2 text-[10px] text-amber-400/80 bg-amber-400/10 p-1.5 rounded border border-amber-400/20 text-center">
                      ⚠ Document may not cover this
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="w-full space-y-6">
      {/* Answer Card */}
      <div className="relative group bg-[#0A0A0A] border border-zinc-800 rounded-2xl overflow-hidden shadow-xl">
        <div className="relative p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
               <div className="w-8 h-8 rounded-md bg-white flex items-center justify-center">
                  <svg className="w-4 h-4 text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
               </div>
               <div className="flex flex-col">
                 <h3 className="text-sm font-semibold text-zinc-200">Answer</h3>
               </div>
            </div>
            
            <div className="flex items-center gap-3">
               {!isStreaming && answer && (
                 <button 
                   onClick={copyToClipboard}
                   className="flex items-center gap-1.5 p-1.5 rounded-md hover:bg-zinc-800 transition-all text-zinc-500 hover:text-white opacity-100 md:opacity-0 group-hover:opacity-100"
                   title="Copy answer"
                 >
                   {copied ? (
                     <span className="text-[10px] font-medium text-zinc-300 px-1">Copied</span>
                   ) : (
                     <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                   )}
                 </button>
               )}
            </div>
          </div>

          <div className="prose prose-invert prose-zinc max-w-none text-zinc-300 prose-p:leading-relaxed prose-pre:bg-[#111] prose-pre:border prose-pre:border-zinc-800 prose-headings:text-zinc-100 text-sm select-text selection:bg-zinc-700">
            <ReactMarkdown
              remarkPlugins={[remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={{
                a: ({ node, ...props }) => {
                  const match = props.href?.match(/^#cite-(\d+)$/);
                  if (match) {
                    const id = parseInt(match[1]);
                    const source = sources?.find(s => s.id === id);
                    if (source) {
                      return (
                        <a 
                          href={`${API_BASE_URL}/uploads/${encodeURIComponent(source.source_file)}#page=${source.page_number}`}
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="inline-flex items-center justify-center w-5 h-5 ml-1 text-[10px] font-bold text-white bg-zinc-800 rounded-full hover:bg-zinc-700 transition-colors cursor-pointer group relative"
                          title={`${source.source_file}, Page ${source.page_number}\n\n"${source.chunk_text}"`}
                        >
                          {id}
                        </a>
                      );
                    }
                  }
                  return <a {...props} className="text-blue-400 hover:underline" target="_blank" rel="noopener noreferrer" />;
                }
              }}
            >
              {answer ? answer
                .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$')
                .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$')
                .replace(/\[(\d+)\]/g, '[$1](#cite-$1)') 
              : ''}
            </ReactMarkdown>
            {isStreaming && <span className="inline-block w-2 h-4 ml-1 bg-white animate-pulse align-middle"></span>}
          </div>
        </div>
      </div>

      {/* Sources Grid */}
      {sources && sources.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 flex items-center gap-2">
              <svg className="w-3.5 h-3.5 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>
              References ({sources.length})
            </h4>
            <button 
              onClick={() => setShowSources(!showSources)}
              className="text-xs font-medium text-zinc-400 hover:text-white transition-colors"
            >
              {showSources ? 'Collapse' : 'Expand'}
            </button>
          </div>

          {showSources && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 animate-fade-in">
              {sources.map((source, index) => (
                <div key={index} className="bg-[#0A0A0A] border border-zinc-800 rounded-xl p-3 hover:border-zinc-700 transition-colors group">
                  <div className="flex items-start justify-between mb-2 gap-2">
                    <a 
                      href={`${API_BASE_URL}/uploads/${encodeURIComponent(source.source_file)}#page=${source.page_number}`}
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="flex flex-col flex-1 min-w-0 group-hover:text-white transition-colors"
                    >
                      <span className="text-xs font-medium text-zinc-300 truncate">{source.source_file}</span>
                      <span className="text-[10px] text-zinc-600">Page {source.page_number}</span>
                    </a>
                    <div className="shrink-0 px-2 py-0.5 rounded border border-zinc-800 text-[9px] font-medium text-zinc-400 bg-zinc-900">
                      {(source.relevance_score * 100).toFixed(0)}%
                    </div>
                  </div>
                  <p className="text-[11px] text-zinc-500 leading-relaxed italic line-clamp-3 relative pl-2 border-l-2 border-zinc-800 group-hover:border-zinc-600 transition-colors">
                    "{source.chunk_text}"
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Answer Quality Panel */}
      {renderQualityPanel()}

      {/* Suggested Follow-ups */}
      {!isStreaming && suggestions !== undefined && (
        <div className="pt-2">
          {suggestions === null ? (
            <div className="flex items-center gap-2 text-xs text-zinc-600 animate-pulse px-1">
              <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
              Thinking of next steps...
            </div>
          ) : suggestions.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {suggestions.map((sug, idx) => (
                <button 
                  key={idx} 
                  className="px-3 py-1.5 rounded-md bg-[#0A0A0A] border border-zinc-800 text-xs text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200 transition-all text-left flex items-center gap-1.5 group"
                  onClick={() => onSuggestionClick(sug)}
                >
                  <svg className="w-3 h-3 text-zinc-600 group-hover:text-zinc-400 transition-colors shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
                  {sug}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
};

export default Answer;
