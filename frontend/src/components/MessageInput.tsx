import { useState, useRef, useEffect } from "react";
import { Send, Square, Database, Sparkles, Paperclip, X, Image, FileText } from "lucide-react";
import { api } from "../api/client";
import type { Attachment } from "../types";

interface Props {
  onSend: (message: string, attachments?: Attachment[]) => void;
  onStop: () => void;
  isStreaming: boolean;
  useRag: boolean;
  onToggleRag: () => void;
}

const ALLOWED_TYPES = [
  "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
  "application/pdf",
  "text/plain", "text/markdown", "text/csv",
  "application/json",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];

const IMAGE_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"];

export function MessageInput({ onSend, onStop, isStreaming, useRag, onToggleRag }: Props) {
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + "px";
    }
  }, [input]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if ((!input.trim() && attachments.length === 0) || isStreaming) return;
    onSend(input.trim() || "请分析附件内容", attachments);
    setInput("");
    setAttachments([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);

    for (const file of Array.from(files)) {
      if (!ALLOWED_TYPES.includes(file.type)) {
        const ext = file.name.split(".").pop()?.toLowerCase();
        if (ext && ["py", "js", "ts", "jsx", "tsx", "yaml", "yml", "xml", "html", "css", "sql", "log", "env", "cfg", "ini", "toml", "md", "txt", "csv", "json"].includes(ext)) {
          // Allow these extensions even if MIME type doesn't match
        } else {
          alert(`不支持的文件类型: ${file.name}`);
          continue;
        }
      }

      if (file.size > 20 * 1024 * 1024) {
        alert(`文件太大 (${file.name}): 最大 20MB`);
        continue;
      }

      try {
        const att = await api.uploadAttachment(file);
        setAttachments((prev) => [...prev, att]);
      } catch (err) {
        alert(`上传失败 (${file.name}): ${(err as Error).message}`);
      }
    }

    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const isImage = (att: Attachment) => IMAGE_TYPES.includes(att.type);
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  return (
    <div className="px-4 pb-4 pt-2">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
        {/* Attachment previews */}
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {attachments.map((att) => (
              <div
                key={att.id}
                className="relative group rounded-lg overflow-hidden border border-white/[0.08]
                           bg-surface-700/50"
              >
                {isImage(att) ? (
                  <div className="w-20 h-20">
                    <img
                      src={att.url}
                      alt={att.filename}
                      className="w-full h-full object-cover"
                    />
                  </div>
                ) : (
                  <div className="flex items-center gap-2 px-3 py-2 min-w-[120px]">
                    <FileText size={16} className="text-cyber-400/60 flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-[10px] text-white/60 truncate max-w-[100px]">
                        {att.filename}
                      </p>
                      <p className="text-[9px] text-white/20">{formatSize(att.size)}</p>
                    </div>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => removeAttachment(att.id)}
                  className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full
                             bg-black/60 text-white/80 hover:bg-black/80
                             flex items-center justify-center
                             opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="relative">
          {/* Input container */}
          <div className="relative rounded-2xl bg-surface-700/50 backdrop-blur-xl
                          border border-white/[0.06] focus-within:border-cyber-400/30
                          focus-within:shadow-glow-cyan transition-all duration-300
                          overflow-hidden">
            <div className="absolute top-0 left-4 right-4 h-px bg-gradient-to-r from-transparent via-cyber-400/20 to-transparent" />

            <div className="flex items-end gap-2 p-2">
              {/* Upload button */}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*,.pdf,.txt,.md,.csv,.py,.js,.ts,.jsx,.tsx,.json,.yaml,.yml,.xml,.html,.css,.sql,.log"
                onChange={(e) => handleFileSelect(e.target.files)}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="flex-shrink-0 rounded-lg p-2.5 text-white/25
                           hover:text-cyber-400 hover:bg-cyber-400/5
                           transition-all duration-200"
                title="上传图片或文件"
              >
                {uploading ? (
                  <div className="w-5 h-5 border-2 border-cyber-400/50 border-t-transparent rounded-full animate-spin" />
                ) : (
                  <Paperclip size={18} />
                )}
              </button>

              <div className="flex-1 relative">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    attachments.length > 0
                      ? "输入问题或直接发送..."
                      : "输入消息... (Enter 发送, Shift+Enter 换行)"
                  }
                  rows={1}
                  className="w-full resize-none bg-transparent px-1 py-2 text-sm text-white/80
                             placeholder-white/20 focus:outline-none"
                  disabled={isStreaming}
                />
              </div>

              <div className="flex items-center gap-1.5 pr-1">
                {/* RAG toggle */}
                <button
                  type="button"
                  onClick={onToggleRag}
                  title={useRag ? "知识库检索已开启" : "知识库检索已关闭"}
                  className={`flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs
                             transition-all duration-300 ${
                    useRag
                      ? "bg-accent-green/10 border border-accent-green/30 text-accent-green shadow-[0_0_10px_rgba(0,230,118,0.15)]"
                      : "bg-transparent border border-white/[0.06] text-white/20 hover:text-white/40"
                  }`}
                >
                  <Database size={14} />
                  <span className="hidden sm:inline">RAG</span>
                </button>

                {/* Send / Stop button */}
                {isStreaming ? (
                  <button
                    type="button"
                    onClick={onStop}
                    className="rounded-lg bg-accent-pink/20 border border-accent-pink/30
                               text-accent-pink hover:bg-accent-pink/30
                               p-2.5 transition-all duration-300
                               hover:shadow-[0_0_12px_rgba(255,64,129,0.25)]"
                    title="停止生成"
                  >
                    <Square size={16} />
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!input.trim() && attachments.length === 0}
                    className={`rounded-lg p-2.5 transition-all duration-300 ${
                      input.trim() || attachments.length > 0
                        ? "bg-gradient-to-r from-cyber-500 to-cyber-600 text-white shadow-glow-cyan hover:shadow-glow-strong"
                        : "bg-white/[0.04] text-white/15 cursor-not-allowed"
                    }`}
                    title="发送"
                  >
                    <Send size={16} />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Hint */}
          <div className="flex items-center justify-center gap-2 mt-2">
            <Sparkles size={10} className="text-white/10" />
            <span className="text-[10px] text-white/15 tracking-wider">
              Enter 发送 · Shift+Enter 换行 · 📎 上传图片/文件
            </span>
          </div>
        </div>
      </form>
    </div>
  );
}
