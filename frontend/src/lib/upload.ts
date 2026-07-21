/**
 * 文件上传工具模块（基于XHR）
 * 
 * 为什么使用XHR而不是fetch？
 * - fetch()原生不支持上传进度事件
 * - XMLHttpRequest提供upload.onprogress接口
 * - 可实现实时上传进度条
 */

/**
 * 上传进度信息
 */
export interface UploadProgress {
  loaded: number;   // 已上传字节数
  total: number;    // 总字节数
  percent: number;  // 上传百分比（0-100）
}

/**
 * 上传结果
 */
export interface UploadResult<T = any> {
  data: T;          // 响应数据
  status: number;   // HTTP状态码
}

/**
 * 上传单个文件（带进度回调）
 * 
 * @param url - POST接口地址
 * @param file - 要上传的文件（FormData中字段名为"file"）
 * @param onProgress - 进度回调函数（可选）
 * @param extraFields - 额外的FormData字段（可选）
 * @returns Promise，包含解析后的JSON响应
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

    // 添加文件和额外字段
    formData.append("file", file);
    if (extraFields) {
      for (const [key, val] of Object.entries(extraFields)) {
        formData.append(key, val);
      }
    }

    // 上传进度跟踪
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress({
          loaded: e.loaded,
          total: e.total,
          percent: Math.round((e.loaded / e.total) * 100),
        });
      }
    });

    // 上传完成处理
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

    // 错误处理
    xhr.addEventListener("error", () => {
      reject(new Error("Network error during upload"));
    });
    xhr.addEventListener("abort", () => {
      reject(new Error("Upload aborted"));
    });
    xhr.addEventListener("timeout", () => {
      reject(new Error("Upload timed out"));
    });

    // 发送请求
    xhr.open("POST", url);
    // 让浏览器自动设置Content-Type（包含multipart边界）
    xhr.send(formData);
  });
}

/**
 * 批量上传文件（顺序上传，每个文件独立进度）
 * 
 * @param url - POST接口地址
 * @param files - 文件列表
 * @param onFileProgress - 单个文件的进度回调（可选）
 * @param onFileStart - 单个文件开始上传的回调（可选）
 * @returns 结果数组，顺序与输入文件列表一致
 */
export async function uploadFiles<T = any>(
  url: string,
  files: File[],
  onFileProgress?: (fileIndex: number, p: UploadProgress) => void,
  onFileStart?: (fileIndex: number, file: File) => void,
): Promise<Array<{ file: File; result?: UploadResult<T>; error?: Error }>> {
  const results: Array<{ file: File; result?: UploadResult<T>; error?: Error }> = [];

  // 顺序上传每个文件
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