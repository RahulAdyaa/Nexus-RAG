import React, { useState, useEffect } from 'react';
import { getDocuments, deleteDocument } from '../services/api';

const DocumentSidebar = ({ refreshTrigger, onSelectionChange, onDocumentDeleted, onDocumentsLoaded }) => {
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());

  useEffect(() => {
    const fetchDocuments = async () => {
      try {
        setIsLoading(true);
        const data = await getDocuments();
        setDocuments(data.documents);
        if (onDocumentsLoaded) onDocumentsLoaded(data.documents);
        setError(null);
      } catch (err) {
        setError(err.message || 'Failed to load documents');
      } finally {
        setIsLoading(false);
      }
    };
    fetchDocuments();
  }, [refreshTrigger, onDocumentsLoaded]);

  const handleCheckboxChange = (docId) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(docId)) newSelected.delete(docId);
    else newSelected.add(docId);
    
    setSelectedIds(newSelected);
    const selectedFilenames = documents.filter(doc => newSelected.has(doc.id)).map(doc => doc.filename);
    onSelectionChange(selectedFilenames);
  };

  const handleDelete = async (docId) => {
    try {
      await deleteDocument(docId);
      if (selectedIds.has(docId)) handleCheckboxChange(docId);
      setDocuments(prev => {
        const updated = prev.filter(doc => doc.id !== docId);
        if (onDocumentsLoaded) onDocumentsLoaded(updated);
        return updated;
      });
      onDocumentDeleted();
    } catch (err) {
      alert('Error deleting document: ' + err.message);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="w-full flex flex-col h-full bg-transparent">
      <div className="p-6 border-b border-zinc-800 bg-[#0A0A0A]">
        <h3 className="text-xs font-semibold tracking-widest text-zinc-500 uppercase flex items-center gap-2 mb-1">
          <svg className="w-3.5 h-3.5 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
          Repository
        </h3>
        <p className="text-[10px] text-zinc-500">Select files to constrain your search scope.</p>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center h-32 gap-3 text-zinc-600">
             <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
             <span className="text-[11px] font-medium uppercase tracking-wider">Loading...</span>
          </div>
        ) : error ? (
          <div className="p-3 bg-red-950/30 border border-red-900/30 rounded-lg text-red-500 text-xs text-center">
             {error}
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center px-4">
             <div className="w-10 h-10 rounded-full border border-zinc-800 bg-[#0A0A0A] flex items-center justify-center mb-3">
                <svg className="w-4 h-4 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"></path></svg>
             </div>
             <p className="text-xs text-zinc-400 font-medium mb-1 uppercase tracking-wider">Empty Repository</p>
             <p className="text-[10px] text-zinc-600">Upload PDF documents to query them.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {documents.map(doc => {
              const isSelected = selectedIds.has(doc.id);
              return (
                <div 
                  key={doc.id} 
                  className={`group relative overflow-hidden flex items-center justify-between p-3 rounded-lg border transition-all cursor-pointer ${
                    isSelected 
                      ? 'bg-zinc-900 border-zinc-700' 
                      : 'bg-[#0A0A0A] border-zinc-800 hover:border-zinc-700'
                  }`}
                  onClick={() => handleCheckboxChange(doc.id)}
                >
                  <div className="flex items-center gap-3 overflow-hidden">
                    <div className={`shrink-0 w-3.5 h-3.5 rounded-sm border flex items-center justify-center transition-colors ${
                      isSelected ? 'bg-white border-white' : 'bg-transparent border-zinc-700 group-hover:border-zinc-500'
                    }`}>
                      {isSelected && <svg className="w-2.5 h-2.5 text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7"></path></svg>}
                    </div>
                    
                    <div className="flex flex-col overflow-hidden">
                      <span className={`text-[11px] font-medium truncate transition-colors ${isSelected ? 'text-white' : 'text-zinc-400 group-hover:text-zinc-300'}`}>
                        {doc.filename}
                      </span>
                      <div className="flex items-center gap-1.5 text-[9px] text-zinc-600 mt-0.5">
                        <span className="flex items-center gap-1"><svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg> {doc.total_pages} p</span>
                        <span>•</span>
                        <span>{formatFileSize(doc.file_size)}</span>
                      </div>
                    </div>
                  </div>
                  
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm(`Are you sure you want to delete ${doc.filename}?`)) {
                        handleDelete(doc.id);
                      }
                    }}
                    className={`shrink-0 w-6 h-6 rounded flex items-center justify-center transition-all ${
                      isSelected 
                        ? 'opacity-100 bg-zinc-800 text-zinc-400 hover:bg-red-900/30 hover:text-red-500' 
                        : 'opacity-0 group-hover:opacity-100 hover:bg-red-900/30 hover:text-red-500 text-zinc-600'
                    }`}
                    title="Delete document"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentSidebar;
