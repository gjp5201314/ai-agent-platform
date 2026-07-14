import { useState, useRef, useEffect } from "react";
import { Send, Square, Database, Paperclip, X, FileText, ChevronDown, Cpu, Check, Settings } from "lucide-react";
import { api } from "../api/client";
import { uploadFile } from "../lib/upload";
import { ProgressList, type FileProgress } from "./ProgressBar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Attachment } from "../types";

const API_BASE = "/api/v1";

interface Props {
  onSend: (message: string, attachments?: Attachment[]) => void;
  onStop: () => void;
  isStreaming: boolean;
  useRag: boolean;
  onToggleRag: () => void;
  modelProvider: string | null;
  onModelProviderChange: (provider: string | null) => void;
  onOpenAdmin: () => void;
}

const ALLOWED_TYPES = [
  "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
  "application/pdf",
  "text/plain", "text/markdown", "text/csv",
  "application/json",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];

const IMAGE_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"];
const PASTE_IMAGE_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/bmp", "image/tiff"];

export function MessageInput({
  onSend, onStop, isStreaming, useRag, onToggleRag,
  modelProvider, onModelProviderChange, onOpenAdmin,
}: Props) {
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [fileProgresses, setFileProgresses] = useState<FileProgress[]>([]);
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

  const fileToDataURL = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });

  /** Validate and upload a single file with progress */
  const uploadFileWithProgress = async (file: File, index: number): Promise<boolean> => {
    // Validate type
    if (!ALLOWED_TYPES.includes(file.type)) {
      const ext = file.name.split(".").pop()?.toLowerCase();
      const codeExts = ["py", "js", "ts", "jsx", "tsx", "yaml", "yml", "xml", "html", "css", "sql", "log", "env", "cfg", "ini", "toml", "md", "txt", "csv", "json"];
      if (!ext || !codeExts.includes(ext)) {
        setFileProgresses(prev => {
          const next = [...prev];
          next[index] = { ...next[index], percent: 100, state: "error", error: "不支持的文件类型" };
          return next;
        });
        return false;
      }
    }
    if (file.size > 20 * 1024 * 1024) {
      setFileProgresses(prev => {
        const next = [...prev];
        next[index] = { ...next[index], percent: 100, state: "error", error: "超过 20MB 限制" };
        return next;
      });
      return false;
    }

    try {
      const result = await uploadFile(
        `${API_BASE}/chat/upload`,
        file,
        (p) => {
          setFileProgresses(prev => {
            const next = [...prev];
            if (next[index]) next[index] = { ...next[index], percent: p.percent, state: "uploading" };
            return next;
          });
        },
      );

      const att: Attachment = result.data;
      if (IMAGE_TYPES.includes(file.type)) {
        const dataUrl = await fileToDataURL(file);
        setAttachments(prev => [...prev, { ...att, url: dataUrl }]);
      } else {
        setAttachments(prev => [...prev, att]);
      }

      setFileProgresses(prev => {
        const next = [...prev];
        if (next[index]) next[index] = { ...next[index], percent: 100, state: "success" };
        return next;
      });
      return true;
    } catch (err) {
      setFileProgresses(prev => {
        const next = [...prev];
        if (next[index]) next[index] = { ...next[index], percent: 100, state: "error", error: (err as Error).message };
        return next;
      });
      return false;
    }
  };

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const fileArr = Array.from(files);

    // Init progress bars
    const initial: FileProgress[] = fileArr.map(f => ({
      filename: f.name,
      percent: 0,
      state: "uploading" as const,
    }));
    setFileProgresses(initial);
    setUploading(true);

    for (let i = 0; i < fileArr.length; i++) {
      await uploadFileWithProgress(fileArr[i], i);
    }

    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
    // Clear progress after 2s
    setTimeout(() => setFileProgresses([]), 2000);
  };

  const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData.items;
    const imageItems: DataTransferItem[] = [];
    for (let i = 0; i < items.length; i++) {
      if (PASTE_IMAGE_TYPES.includes(items[i].type)) {
        imageItems.push(items[i]);
      }
    }
    if (imageItems.length === 0) return;
    e.preventDefault();

    const blobs: File[] = [];
    for (const item of imageItems) {
      const blob = item.getAsFile();
      if (!blob) continue;
      const ext = item.type.split("/")[1] || "png";
      const filename = `clipboard-${Date.now()}-${Math.random().toString(36).slice(2, 6)}.${ext}`;
      blobs.push(new File([blob], filename, { type: item.type }));
    }
    if (blobs.length === 0) return;

    // Init progress
    const initial: FileProgress[] = blobs.map(f => ({
      filename: f.name,
      percent: 0,
      state: "uploading" as const,
    }));
    setFileProgresses(initial);
    setUploading(true);

    for (let i = 0; i < blobs.length; i++) {
      await uploadFileWithProgress(blobs[i], i);
    }

    setUploading(false);
    setTimeout(() => setFileProgresses([]), 2000);
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
    <div className="px-4 pb-4">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
        {/* Upload progress bars */}
        {fileProgresses.length > 0 && (
          <div className="mb-2">
            <ProgressList files={fileProgresses} />
          </div>
        )}

        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {attachments.map((att) => (
              <div
                key={att.id}
                className="relative group rounded-lg overflow-hidden border border-gray-200 bg-white"
              >
                {isImage(att) ? (
                  <div className="w-20 h-20">
                    <img src={att.url} alt={att.filename} className="w-full h-full object-cover" />
                  </div>
                ) : (
                  <div className="flex items-center gap-2 px-3 py-2 min-w-[120px]">
                    <FileText size={16} className="text-gray-400 flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-[10px] text-gray-500 truncate max-w-[100px]">{att.filename}</p>
                      <p className="text-[9px] text-gray-300">{formatSize(att.size)}</p>
                    </div>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => removeAttachment(att.id)}
                  className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full
                             bg-gray-800/60 text-white hover:bg-gray-800
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
          {useRag && (
            <div className="absolute -top-3 left-3 z-10 flex items-center gap-1.5
                            px-2.5 py-0.5 rounded-full
                            bg-emerald-50 border border-emerald-200
                            text-emerald-600 text-[10px] font-medium">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
              </span>
              知识库检索已开启
            </div>
          )}

          <div className={`relative rounded-xl bg-white border transition-all
                          ${useRag
                            ? "border-emerald-300 ring-1 ring-emerald-100"
                            : "border-gray-200 focus-within:border-ds-400 focus-within:ring-2 focus-within:ring-ds-100"}`}>
            <div className="flex items-end gap-1.5 p-2.5">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*,.pdf,.txt,.md,.csv,.py,.js,.ts,.jsx,.tsx,.json,.yaml,.yml,.xml,.html,.css,.sql,.log"
                onChange={(e) => handleFileSelect(e.target.files)}
                className="hidden"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="flex-shrink-0 h-9 w-9 text-gray-400 hover:text-ds-500 hover:bg-ds-50"
                title="上传图片或文件"
              >
                {uploading ? (
                  <div className="w-4 h-4 border-2 border-ds-400 border-t-transparent rounded-full animate-spin" />
                ) : (
                  <Paperclip size={18} />
                )}
              </Button>

              <div className="flex-1 relative">
                <Textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onPaste={handlePaste}
                  placeholder={
                    attachments.length > 0
                      ? "输入问题或直接发送..."
                      : "输入消息... (Enter 发送, Shift+Enter 换行)"
                  }
                  rows={1}
                  className="resize-none bg-transparent border-0 shadow-none focus-visible:ring-0
                             px-1 py-1.5 text-sm placeholder:text-gray-300 min-h-0"
                  disabled={isStreaming}
                />
              </div>

              <div className="flex items-center gap-1">
                <ModelSelector
                  value={modelProvider}
                  onChange={onModelProviderChange}
                  onOpenAdmin={onOpenAdmin}
                />

                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={onToggleRag}
                  title={useRag ? "点击关闭知识库检索" : "点击开启知识库检索"}
                  className={`relative gap-1.5 text-xs h-8 transition-all ${
                    useRag
                      ? "text-emerald-600 bg-emerald-50 hover:bg-emerald-100 hover:text-emerald-700"
                      : "text-gray-400 hover:text-gray-600"
                  }`}
                >
                  <Database size={14} />
                  <span className="hidden sm:inline font-medium">RAG</span>
                  {useRag && (
                    <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full
                                     bg-emerald-500 ring-2 ring-white" />
                  )}
                </Button>

                {isStreaming ? (
                  <Button
                    type="button"
                    variant="destructive"
                    size="icon"
                    onClick={onStop}
                    className="h-9 w-9 shadow-sm"
                    title="停止生成"
                  >
                    <Square size={15} />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    size="icon"
                    disabled={!input.trim() && attachments.length === 0}
                    className="h-9 w-9 bg-ds-500 hover:bg-ds-600 shadow-sm"
                    title="发送"
                  >
                    <Send size={15} />
                  </Button>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center gap-1.5 mt-2">
            <span className="text-[10px] text-gray-300">
              Enter 发送 · Shift+Enter 换行 · 支持上传文件/粘贴图片
            </span>
          </div>
        </div>
      </form>
    </div>
  );
}

/* ============================================================
   ModelSelector — clean light dropdown
   ============================================================ */
function ModelSelector({
  value, onChange, onOpenAdmin,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
  onOpenAdmin: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [providers, setProviders] = useState<{ id: string; name: string; enabled: boolean; default_model: string }[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.adminModels().then((r) => setProviders(r.providers.filter((p: any) => p.enabled))).catch(() => {});
  }, []);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const selected = providers.find((p) => p.id === value);
  const label = selected?.name || "默认";
  const active = value !== null;

  if (providers.length === 0) return null;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`group h-8 px-2.5 rounded-lg flex items-center gap-1.5
                    text-xs font-medium transition-all
                    ${open
                      ? "bg-ds-50 text-ds-600 ring-1 ring-ds-200"
                      : active
                        ? "text-gray-700 bg-gray-50 hover:bg-gray-100"
                        : "text-gray-400 hover:text-gray-600 hover:bg-gray-50"
                    }`}
        title="选择大模型"
      >
        <Cpu size={13} className={open || active ? "text-ds-500" : ""} />
        <span className="hidden md:inline max-w-[80px] truncate">{label}</span>
        <ChevronDown size={12} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          className="absolute right-0 bottom-full mb-1.5 w-56
                      rounded-lg overflow-hidden
                      bg-white border border-gray-200
                      shadow-xl z-50"
        >
          <div className="px-3 py-2 text-[10px] text-gray-400 font-medium border-b border-gray-100">
            切换模型
          </div>

          <button
            onClick={() => { onChange(null); setOpen(false); }}
            className="w-full px-3 py-2 flex items-center gap-2 text-xs text-left
                       text-gray-600 hover:bg-gray-50 transition-colors"
          >
            <div className="w-1.5 h-1.5 rounded-full bg-gray-300" />
            <span className="flex-1">使用默认</span>
            {!active && <Check size={12} className="text-ds-500" />}
          </button>

          <div className="border-t border-gray-100">
            {providers.map((p) => (
              <button
                key={p.id}
                onClick={() => { onChange(p.id); setOpen(false); }}
                className="w-full px-3 py-2 flex items-center gap-2 text-xs text-left
                           text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <div className={`w-1.5 h-1.5 rounded-full ${value === p.id ? "bg-ds-500" : "bg-gray-300"}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-gray-700">{p.name}</div>
                  <div className="text-[10px] text-gray-400 truncate">{p.default_model}</div>
                </div>
                {value === p.id && <Check size={12} className="text-ds-500 flex-shrink-0" />}
              </button>
            ))}
          </div>

          <button
            onClick={() => { setOpen(false); onOpenAdmin(); }}
            className="w-full px-3 py-2 flex items-center gap-2 text-xs text-left
                       text-gray-400 hover:text-ds-500 hover:bg-gray-50 transition-colors
                       border-t border-gray-100"
          >
            <Settings size={12} />
            <span className="flex-1">管理模型</span>
          </button>
        </div>
      )}
    </div>
  );
}
