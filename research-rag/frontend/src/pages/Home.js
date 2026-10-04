import React, { useState, useEffect } from 'react';
import { getDocuments, getStats, clearAllData } from '../services/api';

const Home = () => {
  const [documents, setDocuments] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [docsResponse, statsResponse] = await Promise.all([
        getDocuments(),
        getStats()
      ]);
      
      setDocuments(docsResponse.documents || []);
      setStats(statsResponse);
    } catch (err) {
      setError('Failed to load data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleClearData = async () => {
    if (window.confirm('Are you sure you want to clear all data? This action cannot be undone.')) {
      try {
        await clearAllData();
        await fetchData(); // Refresh data
      } catch (err) {
        setError('Failed to clear data');
        console.error(err);
      }
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center h-full text-zinc-500">
        <svg className="animate-spin h-6 w-6 text-white mb-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
        <p className="text-sm font-medium tracking-wide uppercase">Loading Dashboard...</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto w-full space-y-12 animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex flex-col">
          <h2 className="text-2xl font-semibold text-white tracking-tight">Dashboard</h2>
          <p className="text-sm text-zinc-500 mt-1">System overview and knowledge base management.</p>
        </div>
        <button 
          onClick={handleClearData} 
          className="px-4 py-2 rounded-lg bg-red-950/30 text-red-500 hover:bg-red-900/50 hover:text-white border border-red-900/50 hover:border-red-500 transition-all text-sm font-medium"
        >
          Clear Data
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-950/30 border border-red-900/30 rounded-xl text-red-500 text-sm flex items-center gap-3">
           <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
           {error}
        </div>
      )}

      {/* Statistics Grid */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-zinc-800 flex flex-col">
            <span className="text-3xl font-bold text-white tracking-tight mb-1">{stats.total_documents}</span>
            <span className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Documents</span>
          </div>
          <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-zinc-800 flex flex-col">
            <span className="text-3xl font-bold text-white tracking-tight mb-1">{stats.total_chunks}</span>
            <span className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Text Chunks</span>
          </div>
          <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-zinc-800 flex flex-col">
            <span className="text-3xl font-bold text-white tracking-tight mb-1">{stats.bm25_index_size}</span>
            <span className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">BM25 Index</span>
          </div>
          <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-zinc-800 flex flex-col">
            <span className="text-3xl font-bold text-white tracking-tight mb-1">{stats.chroma_collection_size}</span>
            <span className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Chroma Collection</span>
          </div>
        </div>
      )}

      {/* Documents List */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-white tracking-wider uppercase">Uploaded Documents</h3>
        
        {documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl bg-[#0A0A0A] border border-zinc-800 border-dashed">
            <div className="w-12 h-12 rounded-full border border-zinc-700 bg-zinc-900 flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"></path></svg>
            </div>
            <p className="text-sm text-zinc-300 font-medium">No documents uploaded yet</p>
            <p className="text-xs text-zinc-500 mt-1">Upload PDF files using the sidebar to get started.</p>
          </div>
        ) : (
          <div className="rounded-2xl border border-zinc-800 overflow-hidden bg-[#0A0A0A]">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/50 text-[10px] uppercase tracking-widest text-zinc-500 font-semibold">
                  <th className="px-6 py-4 font-semibold">Document Name</th>
                  <th className="px-6 py-4 font-semibold">Pages</th>
                  <th className="px-6 py-4 font-semibold">Chunks</th>
                  <th className="px-6 py-4 font-semibold">Size</th>
                  <th className="px-6 py-4 font-semibold">Upload Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800 text-sm text-zinc-300">
                {documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-zinc-900/50 transition-colors">
                    <td className="px-6 py-4 flex items-center gap-3">
                      <svg className="w-4 h-4 text-zinc-500" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd"></path></svg>
                      <span className="font-medium text-zinc-200">{doc.filename}</span>
                    </td>
                    <td className="px-6 py-4 text-zinc-500">{doc.total_pages}</td>
                    <td className="px-6 py-4 text-zinc-500">{doc.total_chunks}</td>
                    <td className="px-6 py-4 text-zinc-500">{formatFileSize(doc.file_size)}</td>
                    <td className="px-6 py-4 text-zinc-500">{formatDate(doc.upload_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* System Info */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-white tracking-wider uppercase">System Specs</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-xl bg-[#0A0A0A] border border-zinc-800">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Backend</div>
            <div className="text-sm font-medium text-zinc-200">FastAPI / Python</div>
          </div>
          <div className="p-4 rounded-xl bg-[#0A0A0A] border border-zinc-800">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Vector Store</div>
            <div className="text-sm font-medium text-zinc-200">ChromaDB</div>
          </div>
          <div className="p-4 rounded-xl bg-[#0A0A0A] border border-zinc-800">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1">Retrieval</div>
            <div className="text-sm font-medium text-zinc-200">BM25 + Embeddings</div>
          </div>
          <div className="p-4 rounded-xl bg-[#0A0A0A] border border-zinc-800">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1">LLM Engine</div>
            <div className="text-sm font-medium text-zinc-200">Gemini Pro / OpenRouter</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Home;
