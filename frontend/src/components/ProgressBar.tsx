/**
 * Reusable progress bar for file uploads.
 *
 * Shows filename, percentage, and a colored progress bar.
 * Supports states: uploading (animated), success (green flash), error (red).
 */

export interface ProgressBarProps {
  /** File name to display */
  filename: string;
  /** Progress percentage 0–100 */
  percent: number;
  /** Visual state */
  state?: "uploading" | "success" | "error";
  /** Error message (shown when state="error") */
  error?: string;
}

export function ProgressBar({ filename, percent, state = "uploading", error }: ProgressBarProps) {
  const barColor =
    state === "error"
      ? "bg-red-500"
      : state === "success"
        ? "bg-emerald-500"
        : "bg-ds-500";

  const textColor =
    state === "error"
      ? "text-red-600"
      : state === "success"
        ? "text-emerald-600"
        : "text-ds-600";

  const bgStripes = state === "uploading" ? "bg-[length:20px_20px] animate-[progress-stripe_0.6s_linear_infinite]" : "";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <span className="truncate max-w-[180px] font-medium text-gray-700">{filename}</span>
          {state === "error" && error && (
            <span className="text-[10px] text-red-400 truncate max-w-[120px]">{error}</span>
          )}
        </div>
        <span className={`font-semibold flex-shrink-0 ${textColor}`}>
          {state === "error" ? "失败" : state === "success" ? "完成" : `${percent}%`}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor} ${bgStripes}`}
          style={{
            width: `${state === "error" ? 100 : percent}%`,
            backgroundImage:
              state === "uploading"
                ? "linear-gradient(45deg, rgba(255,255,255,0.15) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0.15) 75%, transparent 75%, transparent)"
                : undefined,
          }}
        />
      </div>
    </div>
  );
}

/**
 * Multi-file upload progress list.
 * Renders individual ProgressBar for each file in the queue.
 */
export interface FileProgress {
  filename: string;
  percent: number;
  state: "uploading" | "success" | "error";
  error?: string;
}

export function ProgressList({ files }: { files: FileProgress[] }) {
  if (files.length === 0) return null;

  return (
    <div className="space-y-3 p-3 bg-white rounded-lg border border-gray-200 shadow-sm">
      {files.map((f, i) => (
        <ProgressBar
          key={`${f.filename}-${i}`}
          filename={f.filename}
          percent={f.percent}
          state={f.state}
          error={f.error}
        />
      ))}
    </div>
  );
}
