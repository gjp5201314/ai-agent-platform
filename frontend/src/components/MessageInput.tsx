import { useState, useRef, useEffect } from "react";
import { Send, Square, Database, Sparkles, Paperclip, X, FileText, ChevronDown, Cpu, Check, Settings } from "lucide-react";
import { api } from "../api/client";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Attachment } from "../types";

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

  const uploadFile = async (file: File): Promise<boolean> => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext && ["py", "js", "ts", "jsx", "tsx", "yaml", "yml", "xml", "html", "css", "sql", "log", "env", "cfg", "ini", "toml", "md", "txt", "csv", "json"].includes(ext)) {
        // Allow
      } else {
        alert(`不支持的文件类型: ${file.name}`);
        return false;
      }
    }
    if (file.size > 20 * 1024 * 1024) {
      alert(`文件太大 (${file.name}): 最大 20MB`);
      return false;
    }
    try {
      const att = await api.uploadAttachment(file);
      if (IMAGE_TYPES.includes(file.type)) {
        const dataUrl = await fileToDataURL(file);
        setAttachments((prev) => [...prev, { ...att, url: dataUrl }]);
      } else {
        setAttachments((prev) => [...prev, att]);
      }
      return true;
    } catch (err) {
      alert(`上传失败 (${file.name}): ${(err as Error).message}`);
      return false;
    }
  };

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    for (const file of Array.from(files)) {
      await uploadFile(file);
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
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
    setUploading(true);
    for (const item of imageItems) {
      const blob = item.getAsFile();
      if (!blob) continue;
      const ext = item.type.split("/")[1] || "png";
      const filename = `clipboard-${Date.now()}-${Math.random().toString(36).slice(2, 6)}.${ext}`;
      const file = new File([blob], filename, { type: item.type });
      await uploadFile(file);
    }
    setUploading(false);
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
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {attachments.map((att) => (
              <div
                key={att.id}
                className="relative group rounded-lg overflow-hidden border bg-card/50"
              >
                {isImage(att) ? (
                  <div className="w-20 h-20">
                    <img src={att.url} alt={att.filename} className="w-full h-full object-cover" />
                  </div>
                ) : (
                  <div className="flex items-center gap-2 px-3 py-2 min-w-[120px]">
                    <FileText size={16} className="text-muted-foreground flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-[10px] text-muted-foreground truncate max-w-[100px]">{att.filename}</p>
                      <p className="text-[9px] text-muted-foreground/50">{formatSize(att.size)}</p>
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
          {useRag && (
            <div className="absolute -top-3.5 left-3 z-10 flex items-center gap-1.5
                            px-2.5 py-0.5 rounded-full
                            bg-emerald-500/10 border border-emerald-500/30
                            text-emerald-500 text-[10px] font-medium tracking-wider
                            shadow-[0_0_12px_rgba(0,230,118,0.3)] backdrop-blur">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-500 opacity-75 animate-ping" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
              </span>
              知识库检索已开启
            </div>
          )}

          <div className={`relative rounded-xl bg-card border transition-all overflow-hidden
                          ${useRag
                            ? "border-emerald-500/30 ring-1 ring-emerald-500/10"
                            : "focus-within:border-primary/30 focus-within:ring-1 focus-within:ring-primary/20"}`}>
            <div className="flex items-end gap-1.5 p-2">
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
                className="flex-shrink-0 h-10 w-10 text-muted-foreground hover:text-primary"
                title="上传图片或文件"
              >
                {uploading ? (
                  <div className="w-4 h-4 border-2 border-primary/50 border-t-transparent rounded-full animate-spin" />
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
                             px-1 py-2 text-sm placeholder:text-muted-foreground/50 min-h-0"
                  disabled={isStreaming}
                />
              </div>

              <div className="flex items-center gap-1 pr-1">
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
                  className={`relative gap-1.5 text-xs h-9 transition-all ${
                    useRag
                      ? "text-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/20 hover:text-emerald-400 shadow-[0_0_10px_rgba(0,230,118,0.25)]"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Database size={14} />
                  <span className="hidden sm:inline font-medium">RAG</span>
                  {useRag && (
                    <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full
                                     bg-emerald-500 ring-2 ring-card animate-pulse" />
                  )}
                </Button>

                {isStreaming ? (
                  <Button
                    type="button"
                    variant="destructive"
                    size="icon"
                    onClick={onStop}
                    className="h-10 w-10"
                    title="停止生成"
                  >
                    <Square size={16} />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    size="icon"
                    disabled={!input.trim() && attachments.length === 0}
                    className="h-10 w-10"
                    title="发送"
                  >
                    <Send size={16} />
                  </Button>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center gap-2 mt-2">
            <Sparkles size={10} className="text-muted-foreground/20" />
            <span className="text-[10px] text-muted-foreground/30 tracking-wider">
              Enter 发送 · Shift+Enter 换行 · 📎 上传/Ctrl+V 粘贴图片
            </span>
          </div>
        </div>
      </form>
    </div>
  );
}

/* ============================================================
   ModelSelector — custom dark dropdown matching app aesthetic
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
        className={`group h-9 px-2.5 rounded-lg flex items-center gap-1.5
                    text-xs font-medium transition-all
                    ${open
                      ? "bg-cyber-500/10 text-cyber-400 ring-1 ring-cyber-500/30"
                      : active
                        ? "text-foreground bg-surface-700/40 hover:bg-surface-700/70"
                        : "text-muted-foreground hover:text-foreground hover:bg-surface-700/40"
                    }`}
        title="选择大模型"
      >
        <Cpu size={13} className={open || active ? "text-cyber-400" : ""} />
        <span className="hidden md:inline max-w-[80px] truncate">{label}</span>
        <ChevronDown size={12} className={`transition-transform ${open ? "rotate-180" : "opacity-50"}`} />
      </button>

      {open && (
        <div
          className="absolute right-0 bottom-full mb-1.5 w-56
                      rounded-lg overflow-hidden
                      bg-[#0b0b16]/95 backdrop-blur-xl
                      border border-white/10
                      shadow-[0_8px_32px_rgba(0,0,0,0.5),0_0_0_1px_rgba(0,229,255,0.08)]
                      z-50"
        >
          <div className="px-3 py-2 text-[10px] text-white/30 tracking-widest uppercase border-b border-white/5">
            切换模型
          </div>

          <button
            onClick={() => { onChange(null); setOpen(false); }}
            className="w-full px-3 py-2 flex items-center gap-2 text-xs text-left
                       text-white/70 hover:bg-white/5 transition-colors"
          >
            <div className="w-1.5 h-1.5 rounded-full bg-white/20" />
            <span className="flex-1">使用默认</span>
            {!active && <Check size={12} className="text-cyber-400" />}
          </button>

          <div className="border-t border-white/5">
            {providers.map((p) => (
              <button
                key={p.id}
                onClick={() => { onChange(p.id); setOpen(false); }}
                className="w-full px-3 py-2 flex items-center gap-2 text-xs text-left
                           text-white/70 hover:bg-white/5 transition-colors"
              >
                <div className={`w-1.5 h-1.5 rounded-full ${value === p.id ? "bg-cyber-400 shadow-[0_0_6px_rgba(0,229,255,0.6)]" : "bg-white/20"}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-white/90">{p.name}</div>
                  <div className="text-[10px] text-white/30 truncate">{p.default_model}</div>
                </div>
                {value === p.id && <Check size={12} className="text-cyber-400 flex-shrink-0" />}
              </button>
            ))}
          </div>

          <button
            onClick={() => { setOpen(false); onOpenAdmin(); }}
            className="w-full px-3 py-2 flex items-center gap-2 text-xs text-left
                       text-white/40 hover:text-cyber-400 hover:bg-white/5 transition-colors
                       border-t border-white/5"
          >
            <Settings size={12} />
            <span className="flex-1">管理模型</span>
          </button>
        </div>
      )}
    </div>
  );
}
