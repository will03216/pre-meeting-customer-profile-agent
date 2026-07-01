---
name: polym-customer-one-pager
version: 0.5.0
description: "客户「一客一策」完整账户计划合成。输入：prospection 文档链接（会前画像）+ meeting notes 文档链接（会后纪要），可选 SA 人工补充的内部数字。拉取两份源文档，按字段映射抽取信息，套用「一客一策」标准模板（骨架学习火山引擎模板，风格学习 Havas/爱诗科技/广实案例）合成账户计划。**风格是提炼式追踪文档，不是 prospection**：信息压成 bold bullet + callout，仅 4 张可追踪表保留为表格，重心在合作现状叙事 + 我方策略/行动/进展。**输出永远是英文（无论源文档/示例是什么语言）**，写入 Lark 文档；可选归档到 SA Wiki。内部敏感数字（计收目标/钱包份额/预算）无来源一律标 [TBD]，绝不臆造。"
metadata:
  requires:
    bins: ["lark-cli"]
---

# polym-customer-one-pager — 一客一策账户计划合成 Skill

> **衔接：** `polym-customer-prospect`（产出 prospection 画像，是本 skill 的输入之一）
> **依赖：** `polym-sa-wiki`（wiki 归档）· `lark-cli`（Lark 文档读写）
> **可选联动：** `lark-minutes`（妙记）· `lark-vc`（VC 会议纪要）· `lark-sheets`（读嵌入式表格）
> **可选 env：** `ONEPAGER_FOLDER_TOKEN`（一客一策文档的 Lark 文件夹）

## 0. 前置依赖：lark-cli 认证（每次运行前先做）

> **本 skill 唯一的硬依赖是 `lark-cli` 已安装且已登录。** 拉源文档、写一客一策都靠它。**在执行任何 Phase 之前，先跑这个认证检查**——这样换一台机器 / 换一个人，只要装了 `lark-cli`，都能自助完成登录，不再卡在「没认证」上。

**Step 1 — 检查是否已登录（read-only）：**

```bash
lark-cli auth status --json
```
- `identities.user.status` 为 `ready` 或 `needs_refresh`（会在下次调用自动刷新）→ **已认证，跳过 Step 2-4，直接进 Phase 0**。
- 报错 / `user.available=false` / `not logged in` → 走 Step 2 引导登录。
- 若 `lark-cli` 命令本身不存在（`command not found` / `127`）→ 这是**安装**缺失，认证流程救不了，先走下面的 **Step 0 安装**，装好再回 Step 1。

**Step 0 — lark-cli 未安装时，先安装（仅当 Step 1 报 command not found 才做）：**

```
help me to install CLI：https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md
```

- WebFetch 上面这份官方安装指南，按其中对应当前操作系统（macOS / Linux / Windows）的步骤把 `lark-cli` 装上；装完用 `lark-cli --version` 验证可用，再回到 Step 1 重新检查认证。
- 安装可能需要用户授权（包管理器 / sudo / 下载）——把需要用户手动执行的命令清楚地给出来，不要静默假设成功。

**Step 2 — 发起 Device Flow，拿到验证 URL（不阻塞）：**

```bash
lark-cli auth login --no-wait --json --recommend
```
返回 `verification_url`、`device_code`、`expires_in`（600s）。`--recommend` 只申请推荐 scope；本 skill 需要 `docx`/`drive`，必要时改用 `--domain docs,drive,wiki` 或 `--scope` 显式申请。

**Step 3 — 生成二维码并把 URL + 二维码发给用户，然后结束本轮：**

```bash
lark-cli auth qrcode --output ./lark_auth_qr.png   # PNG（默认推荐）；用户明确要 ASCII 才加 --ascii
```
把 `verification_url` **原样**（不要 URL-encode、不加空格）先输出，二维码图片放 URL 下面，并提示用户：「在浏览器/飞书完成授权后回来告诉我」。`verification_url` 与 `device_code` 是一次性的，**不要缓存**；每次需要认证都重新跑 Step 2。

**Step 4 — 用户确认授权后，由你执行完成登录：**

```bash
lark-cli auth login --device-code "<Step 2 拿到的 device_code>"
```
成功后 `auth status` 应变为 `ready`，再继续 Phase 0。授权超时（>600s）→ 回 Step 2 重新发起。

> ⚠️ 对「只投递最终消息」的 harness：Step 3 把二维码/URL 作为**本轮最后一条消息**返回并交还控制权，**不要**在同一轮里阻塞等 `--device-code`；等用户回来确认后再在新一轮跑 Step 4。

## 1. 何时使用

### 1.1 触发场景
- "做一个客户的一客一策 / one pager"
- "把 prospection 和会议纪要合成账户计划"
- "会后整理这个客户的账户档案"
- "结合会前画像和会后纪要做客户档案"
- "<客户名> 的一客一策更新一下"

### 1.2 本 skill 不做
- 不替代真实判断 — 内部数字（计收/钱包份额/预算）由 SA 人工给，缺则标 `[TBD]`
- 不臆造任何数据 — 每个字段都有来源或标 `[TBD]`
- 不自动生成白板/架构图 — 用表格替代并提示手动补图
- 不强制归档 wiki — wiki 归档是**可选**步骤，仅在 SA 要求时进行；进行时走 write_queue（不直接改页面）

## 2. 输入参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `existing_onepager` | 否 | **已有的一客一策文档链接**；给了 → 进 **Update mode**（增量更新，不新建） |
| `prospection` | 推荐 | prospection 文档链接 / 文本（会前画像） |
| `meeting_notes` | 推荐 | 会议纪要链接 / 文本（Lark 文档 / 妙记 / VC 纪要 / 粘贴文本）；Update mode 下**只给新增的那次（几次）纪要**，不必重喂旧纪要 |
| `company_name` | 否 | 客户名；缺则从 prospection / 已有文档提取 |
| `sa_inputs` | 否 | SA 人工补充的内部数字（计收目标、钱包份额、owner、商务策略等） |
| `sa_name` | 否 | SA 的飞书显示名，用于 owner 与 wiki 归档；查 memory，无则问一次 |

**🔀 两种运行模式（Phase 0 自动判定）：**
- **Create mode（首次建档）**：没有 `existing_onepager` → 从 prospection + 纪要从头合成，`docs +create` 新建文档。
- **Update mode（已有文档 + 新会议）**：给了 `existing_onepager` → **以现有文档为基线**，只把**新增纪要**增量合并进去，`docs +update --mode overwrite` **打回原文档**（doc_id/URL 不变）。**绝不从头重跑、绝不新建**——否则会丢掉已填的内部数字与历史 Engagement Log。详见 §8.5。
- 触发语判定：用户给了「现有 one-pager 链接 + 新纪要」，或说「更新 / update / 加一次会议 / 会后更新一下」→ Update mode。不确定就问一句「是更新这篇现有的，还是新建？」

**缺失输入协议：**
- **Create mode**：两份源文档**至少要有一份**才能开始；都没有 → 让 SA 至少给一个链接。
- **Update mode**：`existing_onepager` + **至少一份新纪要**才有意义；只给现有文档没有新纪要 → 问 SA 这次要更新什么。
- 只有 prospection 没有纪要 → 可生成，但「复盘 / 商机 / 跟进 / To Do」会大量 `[TBD]`，提示 SA。
- 只有纪要没有 prospection → 可生成，但「企业背景 / 行业」会较薄，建议先跑 prospection skill。
- 内部数字缺失 → 标 `[TBD]`，最后汇总成待补充清单返回。

## 3. 架构总览

```
输入：[existing_onepager 链接?] + prospection 链接 + meeting notes 链接 (+ SA 人工输入)
         │
         ▼
Phase 0  判定模式（有 existing_onepager → Update / 否 → Create）；fetch 源文档
         │       Update mode 额外 fetch 现有一客一策当基线
         │
         ▼
Phase 1  抽取：按 field-mapping.md 提取结构化信息，标注来源
         │       Update mode 只抽「新增纪要」的增量信号
         │
         ▼
Phase 2  缺口分析：对照模板，列出缺失字段；向 SA 索取内部数字，或标 [TBD]
         │       Update mode：保留现有文档里已填的内部数字，不要打回 [TBD]
         │
         ▼
Phase 3  合成：套用 one-pager-template.md（输出永远英文），冲突以纪要为准
         │       Update mode：增量合并进基线（见 §8.5），不从头重写
         │
         ▼
Phase 4  写 Lark 文档：Create → docs +create 新建；Update → docs +update overwrite 打回原 doc
         │
         ▼
返回：文档链接 + 关键摘要 + 待补充清单（Update mode 标明本次变更）
         │
         ▼
Phase 5  (可选) 归档到 SA Wiki write_queue — 仅当 SA 要求时
```

## 4. Phase 0 — 解析输入

详见 [`references/extraction-workflow.md`](references/extraction-workflow.md)。

```bash
# Update mode：先 fetch 现有一客一策当基线（拿到现有结构 + 已填的内部数字 + 历史 Engagement Log + 原 doc_id）
lark-cli docs +fetch --api-version v2 --doc "<existing_onepager_url>" --format pretty --as user

# Prospection（普通 Lark 文档）— Update mode 下通常已融进现有文档，可不重拉
lark-cli docs +fetch --api-version v2 --doc "<prospection_url>" --format pretty --as user

# Meeting notes（先按普通文档试；妙记/VC 走对应 skill）— Update mode 下只拉「新增的那次（几次）」
lark-cli docs +fetch --api-version v2 --doc "<meeting_notes_url>" --format pretty --as user
```

- **Update mode 必做**：先 fetch `existing_onepager`，把它当**基线 + 事实来源**——记下现有的 11/12 章节结构、**已填的内部数字（绝不打回 [TBD]）**、历史 Engagement Log 行、现有评级与方向，以及**原 doc_id（Phase 4 要 overwrite 回这篇）**。
- `--doc` 传 URL（不能用位置参数），必须 `--api-version v2`。
- 输出过大会落盘到 tool-results，用 Read 读取。
- 链接是妙记 → 调 `lark-minutes` skill；是 VC 纪要 → 调 `lark-vc` skill；是粘贴文本 → 直接用。
- 嵌入式 `<sheet>`/`<whiteboard>` 取不到单元格数据 → 提示 SA 人工提供或用 `lark-sheets` 单独读。
- **⚠️ 原始逐字稿（ASR）识别**：若纪要是**未经整理的语音转写**（满屏 `Speaker 1/2/3`、断句破碎、专有名词明显拼错，如「Bybersburg→Babelsberg」「Rocca Baseline→Luc Besson?」），按以下规则处理：
  - **人名/公司名/产品名/数字一律视为低可信**。能高置信还原的（结合上下文唯一确定）→ 还原并在该处加 `<text color="blue">[confirm]</text>`；不能确定的 → 直接 `<text color="blue">[TBD — name garbled in transcript]</text>`，**绝不把猜测当事实写死**。
  - 成本%、周期、用户数等口播数字标注「approx.」，并进 §12 的 source caveat。
  - **务必在 §12 Reference Materials 放一条 ASR source-caveat callout**（模板已含），提醒对外引用前先核实。

## 5. Phase 1 — 抽取

按 [`references/field-mapping.md`](references/field-mapping.md) 把两份源文档映射到一客一策章节。

- **从 prospection 取：** 企业概况、行业、AI/技术栈、竞争 landscape、opportunity 评分（→ 主推产品）、初版关键人。
- **从纪要取（重点信号）：** 决策链态度（支持/反对/中立）、预算与商机（金额/卡点/产解 owner）、真实竞争份额、复盘信号、action items（→ To Do + 分季度行动）、资源诉求。
- **🔢 量化信号穷尽**：逐句扫描纪要，把**每一个硬数字**（在产用户数、上线/全量日期、commitment 量级、覆盖区域、友商份额%）都落到对应字段（Partnership Status 叙事「Live now/In motion」/ Strategy & Targets / Opportunity List / Engagement Log）。合成后回看纪要自检：还有数字没进文档=漏抽。
- **🗓 Engagement Log**：每次会面在 Section 3 的 Engagement Log 表里建一行（日期/形式/双方参会人/议题信号/产出）。
- **✅ Action items 可追踪（To Do + Quarterly Action Plan 通用）**：每条动作都带 ①owner ②**绝对日期**（把「this week / 七月 / before the rollout」换算成 `YYYY-MM-DD`/`YYYY-MM`，锚点取会议日期；挂未定档里程碑的把日期标蓝 `[TBD date — <触发条件>]`）③**出处**（`src: <YYYY-MM-DD> mtg, raised by <谁> / agreed with <谁>`）。文末整篇 reference URL 不算单条动作的出处。详见 field-mapping「🗓 Action items：绝对日期 + 出处」。
- **🏅 我方引用的 reference 案例 / proof points**：会上**我方**为建立可信度报出的标杆客户、同行业案例、合作伙伴、现场 demo（如「我们和 Babelsberg / Globo 合作过」「给你看两个 Seedance demo」）是**我方竞争资产**，也是「客户对什么买账」的信号——必须抽进正文：主入口 §9 Product/Solution 的 `edge:`，揭示客户偏好的也点进 §3 Directions，并进 §3 Engagement Log 议题信号列。**ASR 把名字拼错也照样要出**（按 ASR 规则还原/标蓝），绝不只埋进 §11 source caveat 当乱码丢掉。详见 field-mapping「🏅 我方引用的 reference 案例 / proof points」。
- **🔑 关系与政治信号**：软信号落到 §4 Key Decision Makers 的 Notes 列（谁支持/阻碍及原因、KPI、内部张力）+ §9 Commercial Strategy 的 Risk & defense 杠杆（签字卡点、反制动作）。
- **分产品线关注点要具体**：Section 4 的 Focus areas 每人给真实评判标准（KPI / 痛点 / eval 标准），不写「质量与价格」空话。
- **商务策略走 6 杠杆**：Section 9 按 Pricing / Account care / Land / Expand / Strategic / Risk-defense 六条核对。
- **每条信息标来源**（prospection / 纪要），便于冲突处理与可追溯。

## 6. Phase 2 — 缺口分析

1. 对照模板逐章检查，列出无来源的字段。
2. **内部敏感字段**（计收目标、钱包份额、分产品线/分季度计收、内部 owner、内部定价）→ 优先问 SA 一次性补；SA 不补则标 `[TBD]`。
3. 其余字段无来源直接标 `[TBD]`，绝不臆造。

> 一次性把需要 SA 补的内部数字列清单问出来，避免反复打断。

## 7. Phase 3 — 合成

套用 [`references/one-pager-template.md`](references/one-pager-template.md)。严守模板合规规则：

- **🎯 风格第一：提炼式追踪文档，不是 prospection。** 三条原则：
  1. **压缩不堆砌** — prospection 的每段文字 → 压成 **bold 引导的 bullet** 或一句判断；不影响决策/动作的事实直接删。
  2. **表格是例外不是默认** — 只有 4 张真正可追踪的表保留为表格：**Engagement Log · Strategy & Targets · Opportunity List · Quarterly Action Plan**（外加元信息条 + 可选财务表）。其余一律 bullets/callout。满屏表格 = 像 prospection。
  3. **以我为主** — 重心在 §3 合作现状叙事 + §9 我方策略/行动/进展；客户背景从简。
  4. **一个事实只展开一次** — 每个数字/信号/痛点只在它**归属的那个章节**完整写一次，其余地方只**引用**（如「the 400K tier」「latency（见 §3）」），不重复叙述。承诺金额 → 归 §3 合作现状 + 追踪表；痛点 → §3 Blocked 写一次、§9 Risk-defense 变成动作一次（不要再占 §1「Challenges」和 §5 各一条）。**收尾自检**：挑出 2-3 个头条事实（最大数字/最大痛点/主要友商），数一下每个被**展开**了几次；若某个在 4+ 处展开 → 把多余的压成回指。跨「视角」重复是本文档退化成臃肿 prospection 的头号原因。
- **🎨 用 Lark 富文本**：开头 `<callout emoji="⭐">` Highlights 块；`> ` blockquote 做「蓝色/加框」强调（合作现状、dense callout、内部敏感提示）；`<grid><column width-ratio="0.5">` 做并排战略/land-expand；每条 bullet **bold** 引导词；挑战/杠杆用 **【tag】** 方括号分类。
- **§1 Customer Overview 从简 — 硬上限 8 条 bullet（整节合计，不是每块 8 条）**：Company Profile + Business Model & Products + Business Challenges **三块加起来 ≤8**。**Business Model 与 Core Business/Products 合并**为一个「Business Model & Products」块（先一句怎么赚钱，再列产品）。**品牌/产品线一律压成一条** bullet：只点名跟**我方商机**直接相关的 2-3 个，其余收进同一行「Other brands: …」，不要每个品牌单独占一条。**Business Challenges 子块设为可选**：只写 §3/§5/§9 没覆盖的**结构性/业务层**挑战（如股东增长压力、规模化品牌一致性）；若内容只会重复下游章节的痛点（latency、友商定价等）→ **整块删掉**，痛点交给 §3 Blocked / §9 Risk-defense。**离开 §1 前数一遍 bullet：>8 就是在写 prospection，砍回来。**
- **§2 Strategic Goals**：每个方向一个**全宽蓝色 callout**（`background-color="light-blue"`），标题下用 **1/2/3 numbered list** 写明该方向的具体 targets；numbered list **每条之间留空行**（否则 Lark 会嵌套），且**不要套在 `<grid>` 里**（grid 会吞掉空行导致嵌套）。
- **§3 顺序**：**Partnership Status 放最前面**且简短（state 不是 prose，每条一行）；其后是合并的 **Partnership Rating & Directions**（评级带理由 + 主推方向 1/2/3）；再 Engagement Log、Strategy & Targets。
- **🏅 评级纪律：评级以 prospection 为基线，会议没提 ≠ 降级。** 一条产品线 H/M/L 评级从 prospection 带过来；**会议只聚焦了某个方向（如全程谈视频）不代表其他方向要降级**——那只是本次没探到。**只在有正面或负面证据时改评级**，凭「没提到」擅自下调是臆造。**若确实要改，必须在评级旁标注冲突**：`Image — M (prospection had H; meeting centered on video, image not yet probed)`，保留旧值可追溯。
- **§3 合作现状写成叙事**（Havas 风），不写表格：Background / Live now / In motion / Blocked，让人一眼看出动量。
- **§8 Retrospective 默认整节删除（不留占位文字）**：单时点账户不写这一节，**后续 §9–12 顺序上移一位**（Follow-up Strategy→§8、Resource Requests→§9、To Do→§10、Reference Materials→§11）。得失已在 §3 的 Live now/In motion/Blocked + §3 的 **Recap (so far)** 一句话，关系已在 §3 Background + §4 Notes。**只有账户跨多个季度、有可对比的跨周期得失**（如「Q1 上线 3 个团队、Q2 LLM 槽位丢给 AVA、净用量环比 +40%」）时，才作为 §8 出现并保持原 8–12 编号。
- **§4 分产品线决策人表** 仅大企业正式分线采购才用；媒体/agency/AI-native 跳过，改每人一条具体评判标准 bullet。
- **章节名/4 张核心表的列严格按模板**，不增删改、不自创。
- **🔒 输出永远是英文 — 永久规则。** 无论 prospection、meeting notes 或任何参考/示例是什么语言（参考案例常为中文），最终一客一策**一律英文**。唯一例外：客户/产品/品牌名保留原文（如 Seedance、Runway、ModelArk、Seedream；火山引擎写 "Volcano Engine"/"BytePlus"）。章节名、表头、正文全部英文，绝不切换到示例的语言。
- **Prospection 内容压缩规则**：段落 → bullets；详细分析 → 一句判断；Meeting prep 章节（问题/冰破话题/来源列表）→ 不带入一客一策。
- **白板/架构图/嵌入 Sheet**：用 `> 📌 需手动添加：xxx图` 占位，不用表格替代。
- **🔵 所有 `[TBD]`（一切需手动填的缺口）一律用蓝色字** — 写成 `<text color="blue">[TBD]</text>`（带说明的也一样，如 `<text color="blue">[TBD — SA to break down]</text>`）。这样员工一打开文档就能立刻看到哪些信息缺失、需要手动补。**绝不出现裸的、无颜色的 `[TBD]`**。语法注意：只有 `<text color="…">` 能在 Lark markdown 层存活，`<font color>` 会被静默丢弃；已验证可用颜色：`blue`/`green`/`red`。回写后 Lark 可能把标签拆开（`<text color="blue">[</text><text color="blue">TBD]</text>`），这是表象，颜色仍保留、仍渲染为蓝色。
- **冲突以纪要为准**，保留旧值注释：`（prospection 记为 X，纪要更新为 Y）`。**但 ASR 例外**：当冲突是「干净 prospection 数字」对「错乱 ASR 数字」（国家数/办公室数/成本%/周期等口播数字），ASR-低可信优先于「纪要为准」——保留 prospection 值，或给纪要值加 `[confirm]`，绝不让 ASR 杂音覆盖已核实事实数字。「纪要为准」针对的是判断/态度更新（决策链、商机、卡点），不是事实数字。
- 决策人态度直接写词，不用颜色：**Champion**（拥护者）· **Optimistic**（乐观）· **Neutral**（观望/中立）· **Detractor**（主要反对，在 Notes 列备注倾向，如「leans Alibaba Cloud」）。
- 全文控制在 50,000 字符内。

## 8. Phase 4 — 写 Lark 文档

```bash
# 标题格式（英文）："Account Plan · <Company> · <YYYY-MM-DD>"
DOC_TITLE="Account Plan · $COMPANY_NAME · $(date +%Y-%m-%d)"
ONEPAGER_FOLDER="${ONEPAGER_FOLDER_TOKEN:-}"

# Step 1: 把合成内容写到当前目录的文件（lark-cli 需相对路径）
cat > ./onepager_content.md << 'EOF'
<填好的模板内容>
EOF

# Step 2A: Create mode — 新建文档
lark-cli docs +create \
  --title "$DOC_TITLE" \
  ${ONEPAGER_FOLDER:+--folder-token "$ONEPAGER_FOLDER"} \
  --markdown "@onepager_content.md" \
  --as user
# → 返回 doc_id (doc_token) 和 doc_url

# Step 2B: Update mode — 不新建，直接 overwrite 打回原文档（doc_id 取自 Phase 0 fetch 的 existing_onepager）
lark-cli docs +update \
  --doc "<existing_onepager_doc_id>" \
  --mode overwrite \
  --markdown "@onepager_content.md" \
  --as user
# → URL 不变，原文档被整篇合成结果覆盖（增量已在 Phase 3 合并进 onepager_content.md）

# Step 3: 内容过大导致 +create 不全时，用 overwrite 补写（Create mode 用）
lark-cli docs +update \
  --doc "<doc_id_from_create>" \
  --mode overwrite \
  --markdown "@onepager_content.md" \
  --as user

rm ./onepager_content.md
```

> **⚠️ Update mode 的 overwrite 不是「拿新内容覆盖旧文档」那么简单**：`onepager_content.md` 必须是「**基线 + 本次增量合并后的完整文档**」（见 §8.5），不是只写新会议那一段。overwrite 会整篇替换，所以**少写的部分 = 丢失**——务必把现有文档的全部既有内容（含已填内部数字、历史 Engagement Log 行）一起带进 `onepager_content.md` 再 overwrite。

> **⚠️ 验证回写时别被「假失败」骗到**：`lark-cli docs +create` 用 `--markdown` 创建时，**文字颜色（`<text color="blue">`）和 callout 背景色（`background-color="light-blue"`）是作为 block 的 style 属性存的，不会在 `+fetch` 的 HTML/markdown 回写里以标签形式回显**。所以 fetch 回来看到的是裸 `[TBD]`、callout 没有 `background-color` —— 这是**序列化表象，不代表颜色没生效**，在 Lark UI 里仍渲染为蓝色/浅蓝底。验证时**只核对结构**（章节齐全、4 张表是表格没塌成段落、callout/emoji 在、`[TBD]` 数量对），颜色以「我写入的源文件里有正确标签」为准，不要因为 fetch 不回显就反复重写或误报失败。

文档创建后立即回复（默认到此即结束，不自动归档 wiki）：

```
✅ Account Plan ready:
   [Account Plan · <Company> · <YYYY-MM-DD>](<doc_url>)

Key highlights:
• <最重要的 3-5 条：客户阶段、核心商机、主要竞争、下一步动作>

⚠️ TBD (needs SA manual input):
• <所有 [TBD] 字段清单，尤其计收目标/钱包份额/预算>
```

若 [TBD] 中含计收/钱包份额等内部数字，可顺带问一句「要不要现在补上这些数字？」。

**Update mode 的返回另加一段「本次变更」**，让 SA 一眼看出这次更新动了什么：

```
🔄 Updated in place (same doc): [Account Plan · <Company>](<doc_url>)

Changes this round (from <new meeting date>):
• Engagement Log: +1 row (<date> · <form> · <topic>)
• Partnership Status: <e.g. moved "POC" → "Live now: 2 teams onboarded">
• Rating: <e.g. Video H→H unchanged; Image M→H — new evidence: client asked for image pilot>
• To Do: closed <N>, added <N>; Quarterly milestones advanced
• <若跨多季度首次具备可对比得失 → §8 Retrospective 本次新增>

Preserved from prior version: <已填的内部数字 / 历史 Engagement Log 行 — 均保留未动>
```

## 8.5 Update mode — 增量合并规则（Update mode 必读）

> 仅 Update mode 走本节。核心：**以现有文档为基线，只把新增纪要的信号增量合并进去，绝不从头重写、绝不丢历史。**

**保留（绝不动）：**
- **已填的内部数字**（计收目标、钱包份额、预算、内部 owner/定价等）——现有文档里已是实数的，**原样保留，绝不打回 `[TBD]`**。仅当新纪要明确给了新值才更新，并注明。
- **历史 Engagement Log 行**：旧行**一行不动**，新会议**追加新行**（按日期排序）。
- 仍然成立的现有评级、方向、策略、To Do——除非有新证据，否则保留。

**增量合并（按章节）：**
- **§3 Engagement Log**：+1 行（新会议：日期/形式/双方参会人/议题信号/产出）。
- **§3 Partnership Status（Live now / In motion / Blocked）**：按新动量刷新——POC→上线、卡点解除/新增、新承诺量级等。
- **评级（§3 / Highlights）**：沿用 v0.6.0 纪律——**只在有新正/负面证据时改**，改则标注 `Image — M→H (2026-06-23 mtg: client requested image pilot)`；新会议没碰到的维度**不因「这次没提」而降级**。
- **§9 Commercial Strategy / Quarterly Action Plan**：关掉已完成 To Do、加新动作（带绝对日期 + `src:` 出处，沿用 v0.7.0）；里程碑前推。
- **§8 Retrospective**：当本次更新使账户**首次具备跨周期可对比得失**（如「Q1 上线 3 团队、Q2 净用量 +40%」）→ 这时**新增 §8** 并把后续章节恢复原 8–12 编号（沿用模板 §8 规则）。单时点仍不写。
- **冲突**：沿用 §7——判断/态度以**新纪要**为准；事实数字遇「干净基线值 vs 错乱 ASR 值」仍按 ASR 裁决保留可靠值。

**合并后自检（overwrite 前必做）：**
1. `onepager_content.md` 是否为**完整文档**（基线全部章节 + 增量），不是只有新会议片段？
2. 已填内部数字是否都还在、没被打回 `[TBD]`？
3. 历史 Engagement Log 旧行是否都在、只是多了新行？
4. doc_id 是否为 `existing_onepager`（overwrite 打回原文档，不新建）？

> 详见 [`references/field-mapping.md`](references/field-mapping.md)「🔄 Update mode：增量合并」。

## 10. Phase 5 — 归档到 SA Wiki（可选）

> **默认不执行。** 仅当 SA 明确说「归档到 wiki / 存进知识库」时才走此步。
> 询问意向可附在返回里：「需要的话我可以把它归档到 SA Wiki。」

走 `polym-sa-wiki` 的 write_queue（agent 绝不直接写 wiki 页面）。

```bash
# 先拉最新脱敏规则（wiki 为准，不靠记忆）
lark-cli docs +fetch --api-version v2 --doc $META_DESENSITIZATION --as user

# 提交 write_queue（一客一策属决策类，归到 customers/<name>/decisions/）
lark-cli base +record-upsert --base-token $BASE_TOKEN --table-id $WQ_TABLE \
  --json '{
    "fields": {
      "SA": "<SA 飞书显示名>",
      "action": "CREATE",
      "target_path": "customers/<customer-name>/decisions/<YYYY-MM-DD>-one-pager",
      "content_md": "<account plan 正文或摘要 + 文档链接>",
      "source_refs": "<prospection_url>; <meeting_notes_url>; <生成的 doc_url>",
      "status": "pending"
    }
  }' --as user
```

> ⚠️ **脱敏**：计收金额、个人评价、冲突细节默认 `Sensitivity: Restricted`。
> 真实 AK/SK、PII、个人绩效不得入 wiki。先过脱敏检查再提交，常量见 polym-sa-wiki SKILL.md §3。
> 归档成功后告诉 SA proposal_id（P-XXXXX）。

## 11. References

| 文件 | 内容 |
|---|---|
| [one-pager-template.md](references/one-pager-template.md) | 完整账户计划模板（默认英文）+ 模板合规规则 + 格式说明 |
| [field-mapping.md](references/field-mapping.md) | prospection + 纪要 → 各章节的字段映射、提取要点、冲突处理 |
| [extraction-workflow.md](references/extraction-workflow.md) | 两份源文档的拉取方式（Lark 文档 / 妙记 / VC / 文本）+ 常见坑 |
