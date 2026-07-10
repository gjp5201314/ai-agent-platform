import { useState, useEffect, useRef } from "react";
import { Upload, FileText, Trash2, X } from "lucide-react";
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
    if (type === "pdf") return "📄";
    if (type === "docx") return "📝";
    return "📃";
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-200">
          <div>
            <h2 className="text-xl font-bold text-slate-800">知识库管理</h2>
            <p className="text-sm text-slate-500 mt-1">
              {stats.document_count} 个文档 · {stats.chunk_count} 个分块 · {stats.total_size_mb} MB
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={22} />
          </button>
        </div>

        {/* Upload area */}
        <div className="p-5 border-b border-slate-200">
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
            className="w-full border-2 border-dashed border-slate-300 hover:border-brand-400 rounded-xl py-8 flex flex-col items-center gap-2 text-slate-500 hover:text-brand-600 transition-colors disabled:opacity-50"
          >
            {uploading ? (
              <>
                <div className="w-8 h-8 border-3 border-brand-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm">正在上传和处理...</span>
              </>
            ) : (
              <>
                <Upload size={32} />
                <span className="text-sm font-medium">点击上传文件</span>
                <span className="text-xs">支持 PDF, DOCX, TXT, MD</span>
              </>
            )}
          </button>
        </div>

        {/* Document list */}
        <div className="flex-1 overflow-y-auto p-5 space-y-2">
          {documents.length === 0 ? (
            <div className="text-center py-12">
              <FileText size={48} className="mx-auto text-slate-300 mb-3" />
              <p className="text-slate-400">还没有上传任何文档</p>
            </div>
          ) : (
            documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 hover:bg-slate-50"
              >
                <span className="text-2xl">{getFileIcon(doc.file_type)}</span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm text-slate-800 truncate">{doc.filename}</p>
                  <div className="flex items-center gap-3 text-xs text-slate-400 mt-0.5">
                    <span>{formatSize(doc.file_size)}</span>
                    <span>{doc.chunk_count} 分块</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs ${
                        doc.status === "ready"
                          ? "bg-green-100 text-green-600"
                          : doc.status === "processing"
                          ? "bg-yellow-100 text-yellow-600"
                          : "bg-red-100 text-red-600"
                      }`}
                    >
                      {doc.status === "ready" ? "✓ 就绪" : doc.status === "processing" ? "处理中" : "错误"}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(doc.id)}
                  className="text-slate-400 hover:text-red-500 p-2"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
