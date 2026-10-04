import React, { useState, useRef } from 'react';
import { uploadPDFs } from '../services/api';

const Upload = ({ onUploadSuccess }) => {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileSelect = (event) => {
    const selectedFiles = Array.from(event.target.files);
    const pdfFiles = selectedFiles.filter(file => file.type === 'application/pdf');
    if (pdfFiles.length !== selectedFiles.length) {
      setUploadStatus('Only PDF files are allowed');
      setTimeout(() => setUploadStatus(''), 3000);
    }
    setFiles(prev => [...prev, ...pdfFiles]);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragActive(false);
    const droppedFiles = Array.from(event.dataTransfer.files);
    const pdfFiles = droppedFiles.filter(file => file.type === 'application/pdf');
    if (pdfFiles.length !== droppedFiles.length) {
      setUploadStatus('Only PDF files are allowed');
      setTimeout(() => setUploadStatus(''), 3000);
    }
    setFiles(prev => [...prev, ...pdfFiles]);
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    setIsDragActive(true);
  };
  
  const handleDragLeave = () => {
    setIsDragActive(false);
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setUploadStatus('Uploading and processing...');

    try {
      const response = await uploadPDFs(files);
      setUploadStatus(`Processed ${response.files_processed} files (${response.total_chunks} chunks)`);
      setFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onUploadSuccess(response);
      setTimeout(() => setUploadStatus(''), 5000);
    } catch (error) {
      setUploadStatus(`Upload failed: ${error.message}`);
    } finally {
      setUploading(false);
    }
  };

  const removeFile = (index) => {
    setFiles(files.filter((_, i) => i !== index));
  };

  return (
    <div className="w-full flex flex-col gap-4">
      <div 
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`relative overflow-hidden group rounded-xl border-2 border-dashed transition-all duration-300 ease-out flex flex-col items-center justify-center p-6 text-center
          ${isDragActive ? 'border-zinc-400 bg-zinc-900 scale-[1.02]' : 'border-zinc-800 bg-[#0A0A0A] hover:border-zinc-700 hover:bg-zinc-900/50'}
          ${uploading ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
        `}
        onClick={() => !uploading && fileInputRef.current?.click()}
      >
        <div className="w-10 h-10 mb-3 rounded-md bg-zinc-800/50 flex items-center justify-center group-hover:scale-110 transition-transform duration-300 border border-zinc-700/50">
           <svg className="w-5 h-5 text-zinc-400 group-hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
        </div>
        
        <p className="text-sm font-medium text-zinc-400 mb-1 group-hover:text-zinc-200 transition-colors">
          Click or drag PDF files here
        </p>
        <p className="text-[10px] text-zinc-600">Max file size 50MB</p>
        
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      {files.length > 0 && (
        <div className="flex flex-col gap-2 max-h-32 overflow-y-auto custom-scrollbar pr-1">
          {files.map((file, index) => (
            <div key={index} className="flex items-center justify-between p-2 rounded-lg bg-[#0A0A0A] border border-zinc-800 hover:border-zinc-700 transition-colors group">
              <div className="flex items-center gap-2 overflow-hidden">
                <svg className="w-3.5 h-3.5 text-zinc-500 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd"></path></svg>
                <div className="flex flex-col overflow-hidden">
                  <span className="text-xs font-medium text-zinc-300 truncate">{file.name}</span>
                  <span className="text-[9px] text-zinc-600">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                </div>
              </div>
              <button 
                onClick={(e) => { e.stopPropagation(); removeFile(index); }}
                className="w-5 h-5 rounded hover:bg-zinc-800 hover:text-white flex items-center justify-center text-zinc-500 transition-colors shrink-0"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {files.length > 0 && (
        <button 
          onClick={handleUpload}
          disabled={uploading}
          className="w-full py-2 rounded-lg bg-white hover:bg-zinc-200 disabled:opacity-50 disabled:bg-zinc-800 disabled:text-zinc-500 text-black text-sm font-medium transition-all flex items-center justify-center gap-2"
        >
          {uploading ? (
             <>
               <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
               Processing...
             </>
          ) : 'Upload'}
        </button>
      )}

      {uploadStatus && (
        <div className={`text-[11px] px-2 py-1.5 rounded-md text-center font-medium animate-fade-in ${
          uploadStatus.includes('failed') ? 'bg-red-950/30 text-red-500 border border-red-900/30' : 'bg-emerald-950/30 text-emerald-500 border border-emerald-900/30'
        }`}>
          {uploadStatus}
        </div>
      )}
    </div>
  );
};

export default Upload;
