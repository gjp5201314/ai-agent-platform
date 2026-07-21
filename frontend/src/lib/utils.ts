/**
 * 样式工具函数
 * 
 * 功能说明：
 * - 合并Tailwind CSS类名
 * - 自动处理类名冲突（后面的覆盖前面的）
 * - 常用于组件的className属性
 */

import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/**
 * 合并CSS类名
 * 
 * @param inputs - 类名列表（可以是字符串、对象、数组等）
 * @returns 合并后的类名字符串
 * 
 * @example
 * cn('px-2 py-1', 'px-4') // => 'py-1 px-4' (px-4覆盖px-2)
 * cn('text-red-500', condition && 'text-blue-500') // 条件类名
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}