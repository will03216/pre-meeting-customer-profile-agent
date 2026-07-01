# 输入提取工作流

把两份源文档（prospection + meeting notes）拉成纯文本，供合成阶段使用。
SA 直接发链接即可，**无需下载再上传**。

## 0. （Update mode）先拉现有一客一策当基线

若 SA 给的是「**已有一客一策文档链接 + 新增纪要**」→ 进 Update mode，**先 fetch 现有文档**当基线，再拉新纪要：

```bash
lark-cli docs +fetch --api-version v2 --doc "<existing_onepager_url>" --format pretty --as user
```

- 记下：现有章节结构、**已填的内部数字（绝不打回 [TBD]）**、历史 Engagement Log 行、现有评级/方向、**原 doc_id**（Phase 4 要 overwrite 回这篇）。
- Update mode 下 prospection 通常已融进现有文档，可不重拉；meeting notes 只拉**新增的那次（几次）**。
- 合并规则见 [`field-mapping.md`](field-mapping.md)「🔄 Update mode：增量合并」与 SKILL.md §8.5。

## 1. Prospection 文档

通常是 polym-customer-prospect 生成的 Lark 文档。SA 给链接：

```bash
lark-cli docs +fetch --api-version v2 --doc "<prospection_url>" --format pretty --as user
```

- 返回 HTML-ish 结构（含 `<table>`、`<h1>` 等），直接阅读即可。
- 若内容很大（>40KB），输出会被落盘到 tool-results 文件，用 Read 工具读取。

## 2. Meeting notes 文档

会议纪要来源可能有多种，按链接类型选工具：

| 链接/来源类型 | 工具 |
|---|---|
| 普通 Lark 文档 (`/docx/`) | `lark-cli docs +fetch --api-version v2 --doc <url> --as user` |
| 飞书妙记（音视频转写） | 调用 **lark-minutes** skill 获取转写文本 |
| VC 视频会议纪要（总结/待办/章节/逐字稿） | 调用 **lark-vc** skill 查询会议纪要 |
| SA 直接粘贴的文本 | 直接使用 |
| SA Wiki 里已归档的纪要 | 调用 **polym-sa-wiki** skill 读取 |

**默认先尝试 `docs +fetch`。** 若链接是妙记/VC，或 fetch 失败，再走对应 skill。

## 3. 提取后的处理

1. 两份都拉到后，按 [`field-mapping.md`](field-mapping.md) 抽取结构化信息。
2. 标注每条信息的来源（prospection / 纪要），便于冲突处理与可追溯。
3. **冲突以纪要为准**（更近、真实对话），并在字段后注明 prospection 旧值。

## 4. 常见坑

- `lark-cli docs +fetch` 用 `--doc` flag 传 URL，**不能用位置参数**。
- 必须加 `--api-version v2`（v1 已废弃）。
- 嵌入式 `<sheet>`、`<whiteboard>`、`<img>` 在 fetch 结果里只是 token 引用，
  **拿不到表格内单元格数据**。若关键数字在嵌入 sheet 里：
  - 提示 SA「纪要里的 X 在嵌入表格中，fetch 取不到，请人工提供或我用 lark-sheets 单独读取」。
  - 需要时可调用 **lark-sheets** skill 按 sheet token 读取。
- 代理告警 `[WARN] proxy detected` 可忽略，不影响结果。
