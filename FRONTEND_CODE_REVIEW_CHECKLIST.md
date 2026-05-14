# Frontend Code Review Checklist

> Review criteria based on `docs/checklist.md` — Senior CR Checklist (6 categories, 24 sub-items)

## Review Categories (per file)

### 一、架构与设计合理性 (Architecture & Design)
- [ ] SRP: 单一职责，无上帝类/超200行臃肿函数
- [ ] 依赖倒置与接口隔离：高层不依赖底层实现，DI/接口解耦
- [ ] 状态管理：无状态/不可变优先，全局变量/单例安全必要
- [ ] 复用性与防腐败 (DRY & ACL)：无复制粘贴，第三方交互有防腐层
- [ ] 扩展性 (OCP)：对扩展开放、对修改封闭，策略模式替 if-else/switch

### 二、鲁棒性与异常处理 (Robustness & Reliability)
- [ ] 错误不被吞噬：catch 块妥善处理，无空 catch
- [ ] 精准捕获：不捕获过大异常类
- [ ] 边界与极端情况：空/null/0/负数/空字符串/极大值/空集合
- [ ] 并发与线程安全：(前端: React状态安全、异步竞态、cleanup)
- [ ] 资源泄漏：(前端: 定时器/订阅/事件监听器清理)

### 三、性能与扩展性 (Performance & Scalability)
- [ ] 算法复杂度：无过深嵌套循环、无明显O(n²)低效遍历
- [ ] 数据库与I/O优化：(前端: API调用N+1问题、批量处理)
- [ ] 内存管理：(前端: 循环中避免频繁创建大对象、闭包泄漏、useMemo/useCallback)
- [ ] 超时与重试逻辑：外部调用设Timeout、失败重试、幂等性

### 四、安全性 (Security)
- [ ] 注入防御：XSS/HTML注入、输入校验与转义
- [ ] 权限越权：接口校验用户权限 (前端: 路由守卫、API鉴权)
- [ ] 敏感数据：无硬编码密钥/Token/密码、日志脱敏

### 五、测试覆盖与可测性 (Testing & Maintainability)
- [ ] 可测性：代码易编写单元测试、可mock、低耦合
- [ ] 测试用例质量：覆盖异常分支和边界、断言严格有效

### 六、语法规范与代码整洁 (Syntax & Clean Code)
- [ ] 命名规范：Intent-Revealing，严禁模糊命名
- [ ] 语言特性：正确使用TypeScript/React特性、无废弃API
- [ ] 圈复杂度：条件嵌套≤3层、Early Return扁平化
- [ ] 注释价值：解释Why而非What、无TODO/死代码

---

## File Review Tracker

### Root Config Files
- [ ] 01. `eslint.config.js`
- [ ] 02. `index.html`
- [ ] 03. `vite.config.ts`

### src/ Entry
- [ ] 04. `src/index.css`
- [ ] 05. `src/main.tsx`

### src/app/
- [ ] 06. `src/app/App.css`
- [ ] 07. `src/app/App.tsx`
- [ ] 08. `src/app/HomePage.test.tsx`
- [ ] 09. `src/app/HomePage.tsx`
- [ ] 10. `src/app/Layout.test.tsx`
- [ ] 11. `src/app/Layout.tsx`
- [ ] 12. `src/app/TaskDetailPage.tsx`
- [ ] 13. `src/app/TaskListPage.tsx`
- [ ] 14. `src/app/useTaskContext.test.tsx`
- [ ] 15. `src/app/useTaskContext.ts`
- [ ] 16. `src/app/useWorkbenchLayout.ts`
- [ ] 17. `src/app/WorkbenchPage.tsx`
- [ ] 18. `src/app/components/WorkbenchToolbar.tsx`

### src/auth/
- [ ] 19. `src/auth/AuthCallbackPage.test.tsx`
- [ ] 20. `src/auth/AuthCallbackPage.tsx`
- [ ] 21. `src/auth/AuthProvider.test.tsx`
- [ ] 22. `src/auth/AuthProvider.tsx`
- [ ] 23. `src/auth/RequireAuth.test.tsx`
- [ ] 24. `src/auth/RequireAuth.tsx`
- [ ] 25. `src/auth/useAuth.ts`

### src/components/
- [ ] 26. `src/components/TechScene.tsx`

### src/features/assist/
- [ ] 27. `src/features/assist/useAssistWorkbenchActions.ts`

### src/features/prompt-workspace/
- [ ] 28. `src/features/prompt-workspace/promptDrafts.test.ts`
- [ ] 29. `src/features/prompt-workspace/promptDrafts.ts`
- [ ] 30. `src/features/prompt-workspace/usePromptWorkspace.ts`

### src/features/results/
- [ ] 31. `src/features/results/ResultDetails.tsx`
- [ ] 32. `src/features/results/ResultsPanel.tsx`
- [ ] 33. `src/features/results/components/BatchRunnerWorkspace.tsx`
- [ ] 34. `src/features/results/components/FullscreenEditorShell.tsx`
- [ ] 35. `src/features/results/components/PromptWorkspace.tsx`
- [ ] 36. `src/features/results/components/ResultCommon.tsx`
- [ ] 37. `src/features/results/components/resultHelpers.ts`
- [ ] 38. `src/features/results/components/ScriptWorkspace.tsx`

### src/features/runtime/
- [ ] 39. `src/features/runtime/extensionBridge.ts`

### src/features/workflow/
- [ ] 40. `src/features/workflow/useWorkflowActions.ts`
- [ ] 41. `src/features/workflow/workbenchDefaults.ts`
- [ ] 42. `src/features/workflow/workflowContracts.ts`
- [ ] 43. `src/features/workflow/workflowNodePlacement.test.ts`
- [ ] 44. `src/features/workflow/workflowNodePlacement.ts`
- [ ] 45. `src/features/workflow/workflowState.test.ts`
- [ ] 46. `src/features/workflow/workflowState.ts`
- [ ] 47. `src/features/workflow/components/DslEditorPanel.tsx`
- [ ] 48. `src/features/workflow/components/NodePalette.tsx`
- [ ] 49. `src/features/workflow/components/PropertyPanel.tsx`
- [ ] 50. `src/features/workflow/components/WorkflowCanvas.tsx`
- [ ] 51. `src/features/workflow/components/workflowEdgeDecorators.test.ts`
- [ ] 52. `src/features/workflow/components/workflowEdgeDecorators.ts`
- [ ] 53. `src/features/workflow/components/node-editors/BasicNodeEditors.tsx`
- [ ] 54. `src/features/workflow/components/node-editors/ExtractFieldEditor.tsx`

### src/services/
- [ ] 55. `src/services/apiClient.test.ts`
- [ ] 56. `src/services/apiClient.ts`
- [ ] 57. `src/services/authApi.ts`
- [ ] 58. `src/services/taskApi.test.ts`
- [ ] 59. `src/services/taskApi.ts`
- [ ] 60. `src/services/workflowApi.test.ts`
- [ ] 61. `src/services/workflowApi.ts`

---

## Summary

- Total files: 61
- Completed: 0
- Remaining: 61
