import { useState, useEffect, useRef } from "react";
import { Upload, FileText, Trash2, X, Database, FileCheck } from "lucide-react";
import { api } from "../api/client";
import type { Document } from "../types";

interface Props {
  onClose: () => void;
}

export function DocumentUpload({ onClose }: Props) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [uploading, setUploading] = useState(false);
  const [stats, setStats] = useState({ document_count: 0, chunk_count: 0, total_size_mb: 0 });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadData = async () => {
    try {
      const [docs, st] = await Promise.all([api.listDocuments(), api.getRagStats()]);
      setDocuments(docs);
      setStats(st);
    } catch (err) {
      console.error("Failed to load documents:", err);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    for (const file of Array.from(files)) {
      try {
        await api.uploadDocument(file);
      } catch (err) {
        alert(`上传失败: ${(err as Error).message}`);
      }
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
    await loadData();
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此文档？")) return;
    try {
      await api.deleteDocument(id);
      await loadData();
    } catch (err) {
      alert(`删除失败: ${(err as Error).message}`);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  const getFileIcon = (type: string) => {
    if (type === "pdf") return "pdf";
    if (type === "docx") return "doc";
    return "txt";
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-panel-strong rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col
                     shadow-glow-neon overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-white/[0.06]">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Database size={18} className="text-cyber-400" />
              <h2 className="text-lg font-bold text-white">知识库管理</h2>
            </div>
            <div className="flex items-center gap-3 text-xs text-white/30">
              <span className="flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-cyber-400/60" />
                {stats.document_count} 文档
              </span>
              <span>{stats.chunk_count} 分块</span>
              <span>{stats.total_size_mb} MB</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-white/20 hover:text-white/60 transition-colors p-1"
          >
            <X size={20} />
          </button>
        </div>

        {/* Upload area */}
        <div className="p-5 border-b border-white/[0.06]">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.md"
            onChange={(e) => handleUpload(e.target.files)}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="w-full border border-dashed border-white/[0.08] hover:border-cyber-400/30
                       rounded-xl py-10 flex flex-col items-center gap-3
                       text-white/20 hover:text-cyber-400/60
                       bg-surface-800/50 hover:bg-surface-700/50
                       transition-all duration-300 disabled:opacity-50 group"
          >
            {uploading ? (
              <>
                <div className="w-8 h-8 border-2 border-cyber-400/50 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm text-white/40">正在上传和处理...</span>
              </>
            ) : (
              <>
                <div className="w-12 h-12 rounded-xl bg-cyber-400/5 border border-cyber-400/10
                                flex items-center justify-center group-hover:bg-cyber-400/10
                                transition-all duration-300">
                  <Upload size={24} className="group-hover:scale-110 transition-transform duration-300" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium">点击上传文件</p>
                  <p className="text-xs mt-1 opacity-60">支持 PDF, DOCX, TXT, MD</p>
                </div>
              </>
            )}
          </button>
        </div>

        {/* Document list */}
        <div className="flex-1 overflow-y-auto p-5 space-y-2">
          {documents.length === 0 ? (
            <div className="text-center py-16">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-surface-700/50
                              border border-white/[0.04] flex items-center justify-center">
                <FileText size={28} className="text-white/10" />
              </div>
              <p className="text-sm text-white/20">还没有上传任何文档</p>
            </div>
          ) : (
            documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center gap-3 rounded-xl border border-white/[0.05]
                           bg-surface-700/30 p-3.5 hover:bg-surface-700/50
                           hover:border-white/[0.08] transition-all duration-200 group"
              >
                {/* File type badge */}
                <div className="w-10 h-10 rounded-lg bg-surface-800 border border-white/[0.06]
                                flex items-center justify-center flex-shrink-0">
                  <span className="text-[10px] font-bold text-cyber-400/60 uppercase tracking-wider">
                    {getFileIcon(doc.file_type)}
                  </span>
                </div>

                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm text-white/70 truncate">{doc.filename}</p>
                  <div className="flex items-center gap-3 text-[11px] text-white/20 mt-1">
                    <span>{formatSize(doc.file_size)}</span>
                    <span>{doc.chunk_count} 分块</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
                        doc.status === "ready"
                          ? "bg-accent-green/10 text-accent-green border border-accent-green/20"
                          : doc.status === "processing"
                          ? "bg-accent-amber/10 text-accent-amber border border-accent-amber/20"
                          : "bg-accent-pink/10 text-accent-pink border border-accent-pink/20"
                      }`}
                    >
                      {doc.status === "ready" ? "✓ 就绪" : doc.status === "processing" ? "处理中" : "错误"}
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => handleDelete(doc.id)}
                  className="text-white/10 hover:text-accent-pink p-1.5
                             opacity-0 group-hover:opacity-100 transition-all duration-200"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Footer glow */}
        <div className="neon-divider mx-5 mb-1" />
      </div>
    </div>
  );
}
