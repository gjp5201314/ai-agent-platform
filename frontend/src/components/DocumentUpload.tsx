import { useState, useEffect, useRef } from "react";
import { Upload, FileText, Trash2, Database } from "lucide-react";
import { api } from "../api/client";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
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
    <Dialog open onOpenChange={() => onClose()}>
      <DialogContent className="!max-w-2xl w-[90vw] h-[80vh] p-0 gap-0 flex flex-col bg-surface-900 border border-white/[0.08]">
        <DialogHeader className="px-6 py-4 border-b flex-shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Database size={18} className="text-primary" />
            知识库管理
          </DialogTitle>
          <DialogDescription className="text-xs">
            上传文档构建 RAG 知识库，让 AI 基于文档内容回答
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-5 px-6 py-2.5 border-b text-xs text-muted-foreground flex-shrink-0">
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-primary" />
            {stats.document_count} 文档
          </span>
          <span>{stats.chunk_count} 分块</span>
          <span>{stats.total_size_mb} MB</span>
        </div>

        {/* Upload area */}
        <div className="px-6 py-4 border-b flex-shrink-0">
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
            className="w-full border border-dashed rounded-xl py-8 flex flex-col items-center gap-3
                       text-muted-foreground hover:text-primary hover:border-primary/30
                       bg-muted/20 hover:bg-muted/40 transition-all disabled:opacity-50"
          >
            {uploading ? (
              <>
                <div className="w-7 h-7 border-2 border-primary/50 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm">正在上传和处理...</span>
              </>
            ) : (
              <>
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Upload size={20} className="text-primary" />
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
        <ScrollArea className="flex-1">
          <div className="p-6">
            {documents.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <FileText size={32} className="mx-auto mb-3 opacity-15" />
                <p className="text-sm">还没有上传任何文档</p>
                <p className="text-xs mt-1 opacity-60">上传文档后即可开启 RAG 知识库问答</p>
              </div>
            ) : (
              <div className="space-y-2">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center gap-3 rounded-lg border bg-card/50 p-3
                               hover:bg-card/80 transition-colors group"
                  >
                    <div className="w-10 h-10 rounded-md bg-muted border flex items-center justify-center flex-shrink-0">
                      <span className="text-[10px] font-bold text-muted-foreground uppercase">
                        {getFileIcon(doc.file_type)}
                      </span>
                    </div>

                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{doc.filename}</p>
                      <div className="flex items-center gap-3 text-[11px] text-muted-foreground mt-1">
                        <span>{formatSize(doc.file_size)}</span>
                        <span>{doc.chunk_count} 分块</span>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
                            doc.status === "ready"
                              ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
                              : doc.status === "processing"
                              ? "bg-amber-500/10 text-amber-500 border border-amber-500/20"
                              : "bg-destructive/10 text-destructive border border-destructive/20"
                          }`}
                        >
                          {doc.status === "ready" ? "就绪" : doc.status === "processing" ? "处理中" : "错误"}
                        </span>
                      </div>
                    </div>

                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 opacity-0 group-hover:opacity-100 text-muted-foreground
                                 hover:text-destructive"
                      onClick={() => handleDelete(doc.id)}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
