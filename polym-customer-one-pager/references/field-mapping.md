# 字段映射：Prospection + 会议纪要 → 一客一策各章节

> 🔒 **输出语言永远是英文。** 本文档章节名用英文与 `one-pager-template.md` 对齐；无论源文档/示例是什么语言，最终一客一策一律英文输出，仅客户/产品/品牌名保留原文。

## 三类输入来源

| 输入 | 性质 | 典型来源 |
|---|---|---|
| **Prospection** | 会前外部画像（公开信息） | polym-customer-prospect 生成的 Lark 文档 |
| **Meeting notes** | 会后内部纪要（真实对话） | Lark 文档 / 飞书妙记 / VC 纪要 / 粘贴文本 |
| **SA 人工输入** | 内部敏感数字与判断 | 计收目标、钱包份额、内部 owner、商务策略 |

---

## 映射总表

> ⚠️ **风格提醒（v0.5）：一客一策不是 prospection。** 凡 prospection 的段落/表格，落到一客一策时**默认压成 bold 引导的 bullet**，只有 4 张「可追踪」表保留为表格：Engagement Log、Strategy & Targets、Opportunity List、Quarterly Action Plan（外加元信息条 + 可选财务表）。其余历史上是表格的章节（业务模式、核心产品、竞争份额矩阵、分产品线决策人、分产品线/分季度计收）一律改为 bullets/callout。重心在 **Section 3 合作现状叙事 + Section 9 我方策略与行动**。

| 一客一策章节（英文，对齐模板） | Prospection 提供 | Meeting notes 提供 | SA 人工 |
|---|---|---|---|
| ⭐ Highlights callout | ✅ 合作评级 (H/M/L)、公司一句话、核心机会 | ✅ 合作现状、已有 Revenue | — |
| 1. Company Profile（bullets） | ✅ **主来源** — 行业/规模/主营/AI 成熟度/母公司 | 补最新口径 | — |
| 1. Business Model & Products（**合并**为一个 bullets 块，非表格） | ✅ **主来源** — How they make money 压成 1 条 + Product Portfolio 每产品一条 bullet | 补会上谈到的调整 + 实际使用反馈 | — |
| 1. Business Challenges（**可选**，只留结构性/业务层挑战；与 §3/§5/§9 重复的痛点不写，可整块删） | ✅ 结构性挑战（股东压力、规模化一致性等） | ⚠️ 真实痛点交给 §3 Blocked / §9 Risk-defense，不在此重复 | — |
| 2. Strategic Goals & Direction（每方向一个**蓝色 callout**，内含 1/2/3 numbered targets） | ✅ **主来源** — Recent Developments + Strategic Direction | ✅ 补会上透露的战略 | — |
| 3. Partnership Status（**放最前面**，简短叙事） | ❌ 新客户无合作历史 | ✅ **主来源** — 已完成/进行中/风险 | 补 |
| 3. Partnership Rating & Directions（评级+主推方向**合并**，放 Status 之后） | ✅ **主来源** — BytePlus Opportunity Assessment + Recommended Solutions | ✅ 补会上确认的方向 | 修正优先级 |
| 3. Engagement Log（按日期会面记录） | ❌ | ✅ **主来源** — 每次会面一行：日期/形式/双方参会人/议题信号/产出 | 补参会人 |
| 3. Strategy & Targets（指标表） | 部分（预估用量） | ✅ **主来源** — 目标规模/时间节点 | ✅ Revenue 目标 |
| 4. Org Chart | 初版人物与职位 | ✅ 补汇报关系、新 KP、变动 | 📌 手动绘制白板 |
| 4. Key Decision Makers | 人名/职位（来自 Key Stakeholders） | ✅ **态度必须来自纪要** | 判断修正 |
| 4. Decision Makers by Product Line（**可选**，仅正式分线采购的大企业；媒体/agency/AI-native 跳过，改为每人一条具体评判标准 bullet） | 部分 | ✅ 补关注点 | — |
| 4. IT Procurement Process（bullets，非表格） | 少量 | ✅ **主来源** | — |
| 5. IT System Architecture（bullets） | ✅ **主来源** — AI & Technology Stack 章节 | 补 | 📌 手动绘架构图 |
| 5. Competitive Situation（bullets，已并入；真实份额/折扣/金额在 §3 Partnership Status 叙事或 §9 Strategy 里体现） | ✅ Competitive Landscape + Lock-in Risk | ✅ 补真实切量竞争、POC 状态、份额 | 补 |
| 6. IT Wallet Depth | 规模推断 | ✅ **主来源** — 会上谈到的预算盘子 | 补 |
| 6. Opportunity List | prospection 的机会假设 → 转为商机 | ✅ **主来源** — deal size、卡点、产解 owner | 补 |
| 7. Revenue Target & Wallet Share | ❌ | 偶有信号 | ✅ **主来源** — 全部 [TBD] 直到 SA 填 |
| 8. Retrospective（**默认整节删除**，不留占位，§9–12 顺序上移；得失→§3 Recap，关系→§4 Notes；仅跨季度账户才作为 §8 出现） | ❌ | ✅ 仅跨周期得失 | ✅ 量化数字（仅跨周期） |
| 9. Commercial Strategy | 部分（推荐策略） | ✅ action items 线索 | ✅ 主来源 |
| 9. Product / Solution | ✅ Recommended Solutions → 主推产品 | ✅ 补切入部门/真实痛点 + **我方引用的 reference 案例落到 `edge:`**（见专节） | 修正 |
| 9. Quarterly Action Plan | — | ✅ **主来源** — action items + owner + 时间 | ✅ 补里程碑目标 |
| 9. Brand Marketing / Ecosystem | 部分 | ✅ 会上提到的联合 PR/资源 | — |
| 10. Resource Requests | ❌ | ✅ **主来源** — 客户诉求 + 内部需要 | 补 |
| 11. To Do | — | ✅ **主来源** — action items + owner + 时间 | — |
| 12. Reference Materials | ✅ 两份源文档链接 | ✅ | — |

---

## 从 Prospection 提取的规则

### 提取什么，丢弃什么

**✅ 提取到一客一策：**
- Executive Summary → **⭐ Highlights callout** 的核心亮点（压缩为 3-5 条 bullets）
- Company Overview 表格 → **公司介绍 bullets**（Name/Industry/Size/Revenue/HQ/Parent）
- "What They Do" + "Market Position" → **公司介绍**第 2-3 条（1 句话，不要段落）
- "Recent Developments" → **公司介绍 — 近期重要事件** bullets
- Revenue/funding table → **财务指标表**
- Product Portfolio → **核心产品/业务表格**
- AI & Technology Stack → **IT 系统架构** bullets
- BytePlus Opportunity Assessment (H/M/L scores + rationale) → **合作评级** + **主要合作方向**
- Recommended BytePlus Solutions → **主要合作方向** + **九、产品/方案表格**
- Key Stakeholders → **四、关键决策人表格**（态度填 Neutral，来自纪要再改）
- Competitive Landscape + Lock-in Risk → **五、竞争态势**
- "Suggested Entry Points" → **九、商务策略 — 商机合作**

**❌ 不带入一客一策（prospection 独有内容）：**
- Meeting Preparation（Pre-meeting Research Actions、AE Questions、SA Questions）
- Conversation Starters & Icebreakers
- Sources Used 列表（过长；只保留链接到参考材料表）
- 详细段落分析（在一客一策里压缩成 bullets）

### 压缩原则

Prospection 是分析文档，一客一策是**提炼式追踪文档**。凡 Prospection 的段落文字，在一客一策中**默认压成 bold 引导的 bullet** 或一句判断 —— 表格只留 4 张可追踪表：
- **bullets（默认）**（公司介绍、业务挑战、战略方向、产品、竞争、商机假设、IT 架构）
- **一句判断**（合作评级理由、竞争 lock-in 等级）
- **保留为表格的只有**：Engagement Log、Strategy & Targets、Opportunity List、Quarterly Action Plan（+ 元信息条 + 可选财务表）
- 不影响决策/动作的事实 → 直接删，不带入

### 一个事实只展开一次（去冗余）

每个数字/信号/痛点只在它**归属的章节**完整写一次，其余地方只**引用**不重述：
- **承诺/金额**（如 400K/700K）→ 完整写在 §3 合作现状 + Strategy & Targets 表；§6/§7/§9/§11 只说「the 400K tier」，不再展开。
- **痛点**（如 latency）→ §3 Blocked 命名一次 + §9 Risk-defense 变成动作一次；不再占 §1 Challenges、§5 各一条。
- **友商**（如 Runway）→ §5 Competitive 写 lock-in + 切入角度一次；其他地方引用即可。
- **收尾自检（必做）**：挑 2-3 个头条事实（最大数字 / 最大痛点 / 主要友商 / 竞争叙事 / 成本%），数每个被**完整展开**几次；**目标 ≤2 次，到 3 次就已经在退化** → 把多余的压成回指（如「隐私叙事见 §3」）。一个头条事实不能在 Highlights、§5、§9 各完整说一遍。

---

## 从 Meeting Notes 提取的规则

### 必须从纪要获取（prospection 无法推断）

- **决策人态度**（Champion / Optimistic / Neutral / Detractor，直接写词不用颜色）— 必须来自真实对话，绝不从 prospection 推断
- **预算金额**（钱包深度、商机 deal size）— 真实数字来自对话
- **竞争份额**（友商实际占比、折扣、关系强弱）
- **合作现状**（POC 状态、已接入用量、已有 Revenue）
- **Action items**（To Do + 分季度行动计划）— 抽取时**每条都要带三要素**：①责任人 owner ②**绝对日期**（不要原样照抄「这周/下个月/七月」——按下方规则换算成 `YYYY-MM-DD`）③**出处**（这条动作出自哪次会议、谁提出/谁拍板）。出处不能只靠文末整篇 reference URL，要精确到「哪次 meeting + 谁说的」
- **资源诉求**（客户向火山的要求）
- **复盘信号**（赢/输单、关系进展、客户反馈）
- **我方引用的 reference 案例 / proof points**（会上我方报出的标杆客户、行业案例、demo —— 见下方专节）

### 🔢 量化信号穷尽规则

纪要里**每一个硬数字都要被抽干净**，不留在散落的句子里。逐句扫描，凡是数字一律落到对应字段：

- **用量/规模**：在产用户数、节点/卡数、调用量、覆盖区域数（→ Partnership Status「Live now」叙事 + Strategy & Targets 表）
- **时间节点**：上线日期、全量推广日期、续约窗口、POC 截止（→ Engagement Log + Quarterly Action Plan + To Do）
- **承诺/金额**：commitment 量级、deal size、折扣、预算盘子（→ Opportunity List + Partnership Status「In motion」，无内部确认仍标 [TBD] 不臆造）
- **竞争数字**：友商份额%、折扣、合同期（→ §5 Competitive Situation bullets）

> 自检：合成完成后回看纪要，若还有数字没进文档 → 漏抽了，补回。

### 🗓 Action items：绝对日期 + 出处（To Do / Quarterly Action Plan 通用）

To Do 和分季度行动计划是**给别人接手用的活追踪表**，必须自洽、不依赖隐性上下文。每条动作两件事缺一不可：

**① 绝对日期 — 禁用相对时间。** 把纪要里的「this week / 下周 / 月底 / 七月 / before the rollout」一律换算成具体日期：
- **锚点 = 会议日期**（取 §3 Engagement Log 里这次会面的日期）。例：会议在 `2026-06-16`，「this week」→ 当周周五 `2026-06-20`；「下周」→ `2026-06-23`～`2026-06-27`；「月底」→ `2026-06-30`。
- 只知道月份 → 写 `YYYY-MM`（如「七月」→ `2026-07`）。
- 日期挂在某个尚未定档的里程碑上（「before the 23k rollout」）→ 保留触发条件、把日期标蓝：`<text color="blue">[TBD date — before the 23k rollout]</text>`。

**② 出处 — 精确到「哪次会议 + 谁」。** 每条动作写清来自哪次 meeting、谁提出 / 谁拍板，格式 `src: <YYYY-MM-DD> mtg, raised by <name> / agreed with <name>`。文末整篇 reference URL **不算**单条动作的出处。真的查不到 → `src: <text color="blue">[TBD]</text>`，但绝不省略这一栏。

> 自检：每条 To Do 都应能回答「什么时候做完（具体日期）+ 这是哪次会、谁定的」。答不上来就是没抽干净。

### 🔑 关系与政治信号（放入 §4 Key Decision Makers 和 §9 Commercial Strategy）

软信号落到：
- **§4 Key Decision Makers** — 态度列（Champion / Optimistic / Neutral / Detractor）+ Notes 列写清谁支持/阻碍及原因、KPI、内部张力
- **§9 Commercial Strategy 的 Risk & defense 杠杆** — 决策政治、签字卡点、反制动作

具体抽取：
- 谁支持我们、为什么（部门/个人动机）→ KDM 表 Notes
- 谁阻碍、为什么（绑定友商 / 内部立场）→ KDM 表 Notes + §9 Risk 杠杆
- 内部张力（法务争议、预算 owner vs 技术 owner、总部 vs 区域）→ §9 Risk 杠杆
- 决策政治（谁拍板、谁能否决）→ Org Chart 「Decision chain」那行

### 🏅 我方引用的 reference 案例 / proof points（别丢进 source caveat）

会上**我方**（BytePlus/火山侧）为建立可信度，常会报出标杆客户、同行业案例、合作伙伴或现场 demo（如「我们已和 Babelsberg / Globo / 某知名导演的 AI 短片合作」「给你看两个 Seedance demo」）。这些是**我方的竞争/可信度资产**，也是**「客户对什么有反应」的信号**，必须被抽出来，**不能因为名字在 ASR 里拼错就只埋进 §11 的 source caveat**。

- **抽取什么**：我方提到的 ① reference 客户/标杆（尤其与客户同行业的）② 行业案例/合作伙伴 ③ 现场放过的 demo / 作品（含其效果反响，如客户当场认可哪一点）。
- **落到哪**：
  - 主入口 **§9 Product / Solution 的 `edge:`**（作为支撑我方主推产品的 proof point），
  - 若它揭示「客户对什么买账」→ 也在 **§3 Partnership Status / Directions** 点一句，
  - 同时进 **§3 Engagement Log 的「议题信号」**列（这次会谈了什么的客观记录）。
- **ASR 拼错照样要出**：名字错乱 → 按 ASR 规则还原（高置信加 `<text color="blue">[confirm]</text>`，不确定 `<text color="blue">[TBD — name garbled]</text>`），但**「我方引用了一个该行业标杆」这个事实必须出现在正文**，不能只在 caveat 里当乱码处理掉。

### 分产品线决策人「关注点」抽取（重点改进）

填 Section 4「Decision Makers by Product Line」的 **Focus areas** 行时，每人必须给**具体评判标准**，不要写「质量与价格」这种空话：
- 他的 KPI 是什么（如 cost-per-render、上线速度、合规过审）
- 他的真实痛点（如「J+ 套件没有视频生成」）
- 他评判方案的标准（如延迟、模型质量 vs 现有友商、provenance/合规）

### 6 杠杆商务策略脚手架（重点改进）

填 Section 9「Commercial Strategy」时，按 6 个杠杆逐条核对（适用就填，不适用标 n/a / [TBD]）：
1. Pricing & commercials（定价/折扣/承诺档）
2. Account care / cadence（服务节奏）
3. Opportunity plays — land（落地切入）
4. Expansion plays — expand（一单带一单 / 跨产品线 / 复制到其他区域）
5. Strategic / ecosystem plays（联合 PR、行业活动、战投引荐）
6. Risk & defense（什么会丢单 + 反制动作）

### 没有 Meeting Notes 时的处理

- 合作现状 → "新客户，尚未合作"
- 决策人态度 → 全部 Neutral
- 预算/份额 → [TBD]
- 商机列表 → 从 prospection "Opportunity Assessment" 和 "Suggested Entry Points" 生成初版（标注"来源：prospection，待会议核实"）
- 行动计划 → 填"第一次会议前/中/后"的准备动作
- 资源诉求 → "待首次会议确认"
- To Do → 从 prospection 的"Pre-meeting Research Actions"转化为会前 To Do

---

## 冲突处理

- Prospection 与纪要数字/判断冲突 → **以纪要为准**（更近、真实对话）
- 保留旧值注释：`（prospection 记为 X，纪要更新为 Y）`
- **⚠️ ASR 裁决例外：当冲突是「干净的 prospection 数字」对「错乱的 ASR 数字」时，「以纪要为准」不适用。** 逐字稿里的数字（国家数、办公室数、用户数、成本%、周期等）是低可信的（见 Phase 0 ASR 规则）。若 prospection 给的是来源可靠的硬数字，而纪要只是一段语音转写里听来的、明显口播/识别不稳的数字 → **保留 prospection 的值**，或保留并给纪要值加 `<text color="blue">[confirm]</text>`；**绝不让错乱 ASR 覆盖干净 prospection 数据**。「以纪要为准」针对的是**判断与态度更新**（决策链、商机、卡点），不是拿 ASR 杂音去推翻已核实的事实数字。
- **合作评级（H/M/L）特殊处理：会议没提 ≠ 降级。** 评级反映的是**结构性机会**（规模、用例契合），不是某次会议恰好聊了什么。不要因为一次会议偏重某条线就把另一条线降级（如视频为主的首会不该把 Image 从 H 降成 M，只要本地化素材需求还在）。**只在有正面证据时改评级**（客户明说不相关 / 友商已锁定 / 出现真实卡点）；**若确实要改，必须标注冲突**：`Image — M (prospection had H；本次会议聚焦视频，图像未探)`。

---

## 🔄 Update mode：增量合并（已有文档 + 新会议）

> 当 SA 给的是「**已有一客一策文档链接 + 新增纪要**」时走 Update mode。原则：**现有文档是基线与事实来源，只把新纪要的增量信号并进去，绝不从头重写、绝不丢历史。** 详见 SKILL.md §8.5。

**先 fetch 现有文档当基线**，记下：现有章节结构、**已填的内部数字**、历史 Engagement Log 行、现有评级/方向/策略、原 doc_id。

**保留（绝不动）：**
- **已填的内部数字**（计收目标、钱包份额、预算、内部 owner/定价）——现有是实数的**原样保留，绝不打回 `[TBD]`**；仅当新纪要给了新值才更新并注明。
- **历史 Engagement Log 旧行**一行不动，新会议**追加新行**（按日期排序）。
- 仍成立的现有评级/方向/策略/未完成 To Do——无新证据则保留。

**按章节并入新会议信号：**
- **§3 Engagement Log**：+1 行（日期/形式/双方参会人/议题信号/产出）。
- **§3 Partnership Status（Live now / In motion / Blocked）**：按新动量刷新（POC→上线、卡点解除/新增、新承诺量级）。
- **评级**：沿用上方「会议没提 ≠ 降级」纪律——只在有新证据时改，改则标注 `Image — M→H (2026-06-23 mtg: client requested image pilot)`。
- **§9 / Quarterly Action Plan**：关掉已完成 To Do、加新动作（带绝对日期 + `src:` 出处）；里程碑前推。
- **§8 Retrospective**：本次更新使账户**首次具备跨周期可对比得失**时才新增（沿用模板 §8 规则）。
- **冲突**：判断/态度以新纪要为准；事实数字遇「干净基线值 vs 错乱 ASR 值」仍按上方 ASR 裁决保留可靠值。

**写回**：把「基线 + 增量」合成为**完整文档**，`docs +update --mode overwrite` 打回**原 doc_id**（URL 不变），不新建。overwrite 是整篇替换 → 少写即丢失，务必带齐既有内容。

---

## TBD 清单生成规则

> 🔵 **所有 `[TBD]` 一律蓝色字渲染** — 在正文里写成 `<text color="blue">[TBD]</text>`，员工一打开就能立刻看到缺口。绝不出现裸的无颜色 `[TBD]`。详见 `one-pager-template.md` 的合规规则与格式说明。

合成完成后，把所有 `[TBD]` 汇总到文档末尾"待补充清单"，按优先级排列：

1. **计收目标 / 钱包份额**（最关键，SA 人工填）
2. **关键人态度**（首次建档全 Neutral，会后更新）
3. **商机预算**（会议前均为估算）
4. **IT 总预算 / 竞争份额**
5. **AE / Owner 信息**（未知时）
6. **其他技术细节**（如 J+ LLM 栈）
