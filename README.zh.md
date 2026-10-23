# readproof · 读证

> *每篇论文都留一张读证。拿不到全文，就写不出结论。*

[English](./README.md) | 中文

**一个拒绝假装读过论文的研究助理 agent。**

基于 [DSH](https://github.com/deepseek-ai/deepseek-harness)（DeepSeek Harness，Cordis 插件架构）：它是 DSH 科研助理栈里的**引擎**，不是独立聊天机器人。哪一层属于 DSH、哪一层属于本仓库，见[「与 DSH 的关系」](#与-dsh-的关系)。

---

## 它治的两个病

**一、假读。** 让任何 LLM"总结这篇论文"，都能得到一段流畅的回答；再问一句"这是第几页说的"，就崩了。原因是全文没拿到——于是它用摘要和记忆凑了一段，而系统里没有任何东西让这件事暴露出来。

**二、图谱碎片化。** 读了 30 篇、记了 30 份笔记，还是答不出"这领域还有什么没解决"。因为答案不在任何单篇里，而在**论文之间的缝隙里**：一篇承认局限、另一篇从不引用它、第三篇报出一个和两者都矛盾的数字。自由文本的笔记装不住缝隙。

这个仓库的大部分内容，就是为了让这两件事发生不了。

## 快速开始

零依赖 —— Python 3.9+ 和标准库就够。

```console
$ pip install -e .                 # 或者不装：export PYTHONPATH=$PWD
$ readproof demo                   # 打印状态机，不需要台账
$ readproof init
created /path/readproof-ledger.json
$ readproof add 07 --title "A Paper Title" --venue "CVPR 2026" --arxiv 2601.00001
07 added at UNREAD
$ readproof advance 07 FETCHED
07 -> FETCHED
$ readproof advance 07 READ_FULL
readproof: refusing FETCHED -> READ_FULL: missing reading-receipt fingerprints:
  number_with_locator, hyperparameters, negative_quote, body_detail
$ echo $?
6
$ readproof receipt 07 --from-text paper.txt     # 让它自己去文本里找四项指纹
verdict : full
  pages : 7
  chars : 13869
  [v] number_with_locator  Table II: 41.2 dB / 38.7 dB / 36.4 dB (p.5)
  [v] hyperparameters      lr=1e-4, batch=4, iters=30000 (sec Experiments, p.5)
  [v] negative_quote       We do not evaluate on real underwater sequences ... (sec Limitations, p.6)
  [v] body_detail          We implement the residual weighting as a small module ... (sec Implementation, p.4)
receipt stored for 07 (4 fingerprints)
$ readproof advance 07 READ_FULL
07 -> READ_FULL
```

或者直接给它一个 PDF，让机器上已装的抽取器干活：

```console
$ export READPROOF_PDF_COMMAND='pdftotext -layout {} -'   # 可选，默认会自动探测
$ readproof intake 07 paper.pdf
intake ok: 07 -> FETCHED
  sha256: 4b6851c9c4ad1dcc...
  bytes: 451, 3 page object(s)
  identity: 4/4 title words found in the first pages
$ readproof receipt 07 --from-pdf paper.pdf
```

`intake` 就是设计里的「手动上传」通道：校验完整性（`%%EOF`、体积、页对象）、算 SHA-256、
核对首页是否真的像台账里那篇论文，然后**停在 `FETCHED`**——它永远不会直接给 `READ_FULL`。
下载截断退出 8；文件与标题不符退出 9，除非你显式 `--accept-mismatch`。

`paper.txt` 是带换页符（`\f`）分隔的纯文本，也就是 `pdftotext`、多数抽取器以及
[`dsh-pdf`](https://github.com/rrdongdong/dsh-pdf) 的输出。**readproof 不自己解析 PDF**：标准库解析器恰好
在 CVF/IEEE 文件最难的地方失效（子集化 CID 字体、页面藏在 `/ObjStm` 里），而抽出乱码比诚实失败更糟。

也可以用 `--number/--hyper/--negative/--body` 手填四项，或用 `--file` 读 JSON。
`readproof extract paper.txt` 只预览、不写入。

不想安装时用 `python -m readproof …`，行为完全一致。

### 退出码就是契约

闸门只有在调用方**无法忽略**时才算真的存在，所以失败给的是退出码，不是警告：

| 码 | 含义 |
|---|---|
| `0` | 正常 |
| `1` | 一般错误（未知论文、台账不可读、输入非法） |
| `2` | 论文重复 —— **阻断，不合并** |
| `5` | 非法状态转移（含手动上传越级） |
| `6` | 读证不完整 |
| `7` | 机器上没有可用的 PDF 文本抽取器 |
| `8` | PDF 完整性校验失败（截断 / 不是 PDF） |
| `9` | 手动上传的文件与台账标题不符 |

命令：`init`、`add`、`advance`、`receipt`、`extract`、`intake`、`check`、`status`、`list`、`demo`。台账是普通 JSON 文件
（`--ledger` 或 `$READPROOF_LEDGER`）；每次状态变化都进该论文的 `history`，事后可审计。

## 状态机（治假读）

```
                    ┌── 自动检索 ──┐
UNREAD ─────────────┤              ├──▶ FETCHED ──▶ READ_PARTIAL ──▶ READ_FULL ──▶ VERIFIED
                    └── 手动上传 ──┘         │              │             │          │
   │                                    文件+EOF+       覆盖率<90%   覆盖率≥90%  抽查通过
   │                                    身份核对
   └──▶ FETCH_FAILED ──▶ 请使用者上传 PDF
```

状态不是标签，是**权限**：

| 状态 | 能写什么 |
|---|---|
| `UNREAD` | 只有标题 |
| `FETCH_FAILED` | 禁止任何内容性产物，进上传队列 |
| `FETCHED` | 只能写元数据 |
| `READ_PARTIAL` | 摘要级笔记，**必须写明"仅读到 pp.X–Y"** |
| `READ_FULL` | 完整 8 问 |
| `VERIFIED` | 才能进 gap 表、才能被引用 |

**跳级是错误，不是警告。手动上传最多只能到 `FETCHED`**——它放宽的是"怎么拿到文件"，从不放宽"什么算证据"。

### 读证（reading receipt）

`READ_FULL` 必须留下四项指纹，全是摘要里不会有的：

1. 一个具体数字，带表号**和**页码
2. 一组超参，带节号
3. 一句负面表述的原话（`"we do not …"`）
4. 一处非结论性的正文细节（实验设置、基线配置、失败案例）

只有摘要时四项一项都填不出来 → 状态停在 `READ_PARTIAL` → 8 问写不进去 → 报告生不成。**格式本身就是闸门。**

## 四道闸门

| 闸 | 机制 | 失败 |
|---|---|---|
| ① 去重 | 台账短名 / DOI / arXiv ID | `exit 2` **阻断** |
| ② 全文 | `%%EOF` + 覆盖率 ≥90% + 读证四项 | 拒绝写精读笔记 |
| ③ 证据 | 断言挂 `{位置, E1–E5}`；E3–E5 **禁止**写成"作者承认" | `check` 报错 |
| ④ 核验 | 引用白名单 + 行号存在性 + 章节可定位 | 该句删除或降级 |

四道全是代码，没有一道是 prompt 指令。

## 语义层（治碎片化）

论文是节点，它解决的问题、依赖的假设、承认的局限也是节点。边必须带证据，**没有 `evidenced_by` 的边不入图**。

问题名自由写会毁掉这张图：一个概念变四个节点，图永远连不上。所以节点创建走**受控词表**——canonical id + 别名、`对象@条件` 命名、六个固定类目（SCALE / ROBUST / ASSUME / THEORY / EVAL / ENGINEER）。构建过程**绝不自动创建 canonical**，匹配不上的进待归类池。

六类缺口查询：

| 查询 | 条件 | 含义 |
|---|---|---|
| G1 共鸣 | ≥3 篇都承认没解决 | 真问题，风险最低 |
| G2 沉默 | ≥2 篇提到会坏、无人修 | 性价比最高 |
| G3 争议 | A 说 B 不行，B 没把 A 当基线 | 空间最大 |
| G4 假设 | 两方法假设互斥 | 最适合课程设计 |
| G5 孤证 | 只 1 篇提过、无后续 | 可能是伪问题，只列不荐 |
| G6 异常 | 数字与直觉相反且未解释 | 最容易出真创新 |

产出是 **gap 表**，刻意不产出"创新点"：创新需要知道你的算力、数据和导师方向的人来判断，而 AI 生成的"创新点"被当成自己的工作属于诚信问题。所以 gap 表只给：问题陈述、证据链（页码/章节）、已试过的解法、未试的角度、验证成本——再附一张给使用者的问题清单。

## 什么算成功

- 随便抽一条结论，能指出它在哪一页哪张表
- 同一篇不会被读两遍，同一个问题不会变成两个节点
- 读满约 30 篇后，gap 表里至少有一条会让你想"这确实没人做"

## 不是什么

不是论文摘要器，不是自动写论文，不是全领域综述器，也不是聊天框——它产出文件，价值累积在台账里而不是对话历史里。

## 当前进度

| 部分 | 状态 |
|---|---|
| 状态机 + 能力门控（`readproof/states.py`） | ✅ 已实现，18 个测试 |
| JSON 台账 + 带闸门退出码的 CLI（`store.py`、`cli.py`） | ✅ 可运行，24 个测试 |
| 读证**校验** | ✅ 已实现（只有摘要的读证会被拒） |
| 读证**抽取**（从已抽好的文本里找四项指纹，`receipt.py`） | ✅ 已实现，19 个测试 |
| PDF 完整性 + 身份核对（`pdf.py`） | ✅ 已实现 |
| PDF → 文本（委托给已安装的抽取器，`sources.py`） | ✅ 已实现，23 个测试 |
| 随机抽查 | 设计完成，未实现 |
| 受控词表 + 图构建 | 设计完成，未实现 |
| 缺口查询 G1–G6 | 设计完成，未实现 |

今天能端到端做到的：维护一份去重台账；从论文文本里抽出四项读证指纹，且当输入只是摘要或节选时**拒绝**；
没有完整读证就拒绝把论文推过 `FETCHED`；每条规则被违反都给明确退出码。
还不能做的：自己解析 PDF 文本（它转去调用 `pdftotext`/`mutool`/你的 `$READPROOF_PDF_COMMAND`，
一个都没有时明确退出 7），以及构建问题图谱。

设计说明：[`docs/design.md`](./docs/design.md)

## 与 DSH 的关系

[DSH](https://github.com/deepseek-ai/deepseek-harness) 是 Cordis 架构的 agent harness：提供工具契约、技能/插件模型、沙箱、会话持久化和消息通道。`readproof` 是插进去的**引擎**。整套是分层的，而且各层**刻意分开版本化**：

| 层 | 决定什么 | 在哪 |
|---|---|---|
| **能力层** | 怎么读一个 PDF：抽取、`%%EOF` 完整性、下载重试 | [`dsh-pdf`](https://github.com/rrdongdong/dsh-pdf) —— DSH **插件**（v0.4.2） |
| **流程层** | 怎么读：检索 → 分层 → 精读 → 台账 → 总结 | [`paper-trawl`](https://github.com/rrdongdong/paper-trawl) —— DSH **技能**（v1.0.1） |
| **引擎层** | 什么算读过、什么能写、缺口怎么找 | **本仓库** |
| **纪律层** | 规则本身：证据分级、禁止措辞、闸门语义 | 本仓库 + 技能的提示词 |

```
DSH（harness：工具、技能、沙箱、会话、通道）
└── readproof   引擎：状态机、证据闸门、问题图谱、缺口查询
    ├── paper-trawl   它跑的一个工序   （DSH 技能）
    └── dsh-pdf       它怎么读         （DSH 插件）
```

### 引擎本身不绑框架

`readproof/states.py` **只用标准库，不 import 任何 DSH 代码**。这是刻意的，不是巧合：

> 决定「一条结论能不能写」的那部分，必须能在没有 agent 的情况下被测试——在 CI 里、每次提交、三个 Python 版本都跑。

只有连着活体 agent 才能验证的闸门，等于没人验证的闸门。DSH 提供工具与技能边界，但不提供规则；所以规则留成可移植的 Python，让 CI 反复砸。

> **与 DeepSeek 无隶属关系。** "DeepSeek Harness (DSH)" 与 "Cordis" 仅作描述性使用。

## License

MIT
