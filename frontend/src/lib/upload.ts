/**
 * XHR-based file upload with progress tracking.
 *
 * Replaces fetch() for file uploads because fetch() does not support
 * upload progress events natively. XMLHttpRequest provides upload.onprogress
 * for real-time progress bars.
 */

export interface UploadProgress {
  loaded: number;
  total: number;
  percent: number;
}

export interface UploadResult<T = any> {
  data: T;
  status: number;
}

/**
 * Upload a file via XHR with progress callback.
 *
 * @param url     - POST endpoint
 * @param file    - File to upload (appended as "file" in FormData)
 * @param onProgress - Optional callback receiving { loaded, total, percent }
 * @param extraFields - Additional FormData fields (e.g. metadata)
 * @returns Promise with parsed JSON response
 */
export function uploadFile<T = any>(
  url: string,
  file: File,
  onProgress?: (p: UploadProgress) => void,
  extraFields?: Record<string, string>,
): Promise<UploadResult<T>> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();

    formData.append("file", file);
    if (extraFields) {
      for (const [key, val] of Object.entries(extraFields)) {
        formData.append(key, val);
      }
    }

    // Progress tracking
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress({
          loaded: e.loaded,
          total: e.total,
          percent: Math.round((e.loaded / e.total) * 100),
        });
      }
    });

    // Completion
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText);
          resolve({ data, status: xhr.status });
        } catch {
          reject(new Error("Invalid JSON response"));
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `HTTP ${xhr.status}`));
        } catch {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
        }
      }
    });

    // Error handling
    xhr.addEventListener("error", () => {
      reject(new Error("Network error during upload"));
    });
    xhr.addEventListener("abort", () => {
      reject(new Error("Upload aborted"));
    });
    xhr.addEventListener("timeout", () => {
      reject(new Error("Upload timed out"));
    });

    xhr.open("POST", url);
    // Let browser set Content-Type with boundary for multipart
    xhr.send(formData);
  });
}

/**
 * Upload multiple files sequentially with per-file progress.
 *
 * @returns Array of results in the same order as files
 */
export async function uploadFiles<T = any>(
  url: string,
  files: File[],
  onFileProgress?: (fileIndex: number, p: UploadProgress) => void,
  onFileStart?: (fileIndex: number, file: File) => void,
): Promise<Array<{ file: File; result?: UploadResult<T>; error?: Error }>> {
  const results: Array<{ file: File; result?: UploadResult<T>; error?: Error }> = [];

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    onFileStart?.(i, file);
    try {
      const result = await uploadFile<T>(
        url,
        file,
        (p) => onFileProgress?.(i, p),
      );
      results.push({ file, result });
    } catch (err) {
      results.push({ file, error: err as Error });
    }
  }

  return results;
}
