/**
 * 应用入口文件
 * 
 * 功能说明：
 * 1. 创建React根节点
 * 2. 渲染App组件到DOM
 * 3. 启用React严格模式（开发环境额外检查）
 */

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// 创建React根节点并渲染应用
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);