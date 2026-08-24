<h1 align="center">No Re-Ask</h1>
<p align="center"><strong>完成已获授权的工作，不要再次询问。</strong></p>
<p align="center"><em>用户已经要求的事，直接完成。</em></p>
<p align="center"><a href="./README.md">English</a> · <strong>中文</strong></p>

<p align="center">
  <a href="https://github.com/Rachel560lu/no-reask/actions/workflows/test.yml"><img src="https://github.com/Rachel560lu/no-reask/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10+">
</p>

## 它解决什么问题

代理可能已经开始执行明确的多项工作，却在部分完成、进度更新、轮次边界或长时间操作之后停下，把仍在授权范围内的工作当作可选项再次交给用户决定。这一特定失误重复询问用户已经给出的许可，并让原本可行的工作停在半途。

例如：

```diff
- 解析器已完成。
- 要我继续添加测试吗？
+ 解析器和测试均已完成。
+ 测试套件：54 项测试通过。
```

No Re-Ask 是一项行为技能，用于把用户最初提出的任务推进到完整结果，避免这种不必要的交接。

## 如何工作

该技能会持续跟踪用户要求的交付项，直到每一项已经完成、遇到实质性阻碍，或被用户明确撤回。

- 继续完成授权范围内仍然可行的工作。
- 报告完整结果和具体证据，例如刚刚运行的测试结果。
- 只有在确实缺少选择、授权或安全事实而无法正确行动时，才提出一次简洁的实质性澄清。
- 先完成用户要求的范围，再提出范围外的相关可选建议。

部分进度、已用时间、长时间运行、上下文变化和轮次边界本身都不是阻碍。此时应保存状态并继续，而不是重新询问是否要完成已经要求的工作。

## 适用场景

- 完成包含多个交付项的编码任务，例如实现功能、补充测试、执行验证并报告结果。
- 等待长时间测试或操作结束，然后继续完成已要求的后续工作并给出结果。
- 对明确要求的建议作出收尾，给出清晰的最终建议及理由。
- 在确实缺少目标、授权或安全事实而阻碍下一步已授权行动时，保留已完成的工作，并只提出一次聚焦的澄清。

## 安装

请在克隆后的仓库根目录运行以下带保护检查的命令。它会创建指向技能运行目录的链接；如果目标路径已经存在文件、目录、有效符号链接或悬空符号链接，则会拒绝覆盖。

```sh
skill_target="${HOME}/.codex/skills/no-reask"

if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
  printf '%s\n' "$skill_target already exists; rename or remove it before installing."
else
  mkdir -p ~/.codex/skills
  ln -s "$(pwd)/no-reask" "$skill_target"
fi
```

## 使用

对于重要任务，请显式调用该技能：

```text
$no-reask 实现解析器和测试，运行测试套件，并报告结果。
```

它也适用于建议类任务：

```text
$no-reask 审阅现有选项，选择一项，并给出最终建议和理由。
```

安装后，技能可能被隐式发现；但对于重要任务，显式调用是最可靠的方式。

## 判断边界

| 状态 | 行动 |
|---|---|
| 已要求的工作尚未完成且仍然可行 | 继续并完成它。 |
| 已要求的工作已经完成 | 报告结果和支持证据。 |
| 缺少实质性的选择、授权或安全事实 | 在保留进度的同时，提出一次简洁的实质性澄清，涵盖已知阻碍。 |
| 工作属于范围外的相关可选事项 | 先完成用户要求的范围；只有确有帮助时，才在之后建议额外工作。 |

实质性澄清是为了取得正确或安全行动所需的新信息，不是再次请求批准已经要求的工作。进度更新、已用时间和轮次边界不会形成新的授权边界。

## 能力边界

No Re-Ask 是一项行为技能，也是一种提示词层面的缓解措施。它不包含运行时服务，也没有外部依赖；它不是短语黑名单，因为判断依据是范围和状态，而不是禁用某些措辞。

该技能不能保证在每次交互中都被激活，不会清除上下文，也无法控制日志。它不会扩大授权，不会虚构凭证、绕过审批、作出不安全假设或擅自扩大范围。如果确实缺少实质性事实，正确做法仍然是提出一次聚焦的澄清。

## 行为评测

验证被明确分成三层。每次提交运行的确定性 CI 只验证技能包、fixture、harness 和评分器机制，不接收模型凭证，也不调用模型。手动触发的模型冒烟评测通过固定的可信 adapter 执行公开的四条件调度，并将产物标记为 `pilot_no_efficacy_claim`。正式发布评测还必须预注册 host 和模型快照，进行重复运行，使用未公开 holdout、独立盲审、routing 覆盖率和按提示聚类的置信区间。

评分器分别报告 `continuity_pass`、`task_pass` 和 `boundary_pass`，并另外报告三者同时通过的联合结果。这样，减少重复询问就不能掩盖漏做任务或不安全的持续执行。Routing 只能来自独立 host trace，不能从答案措辞反推。

请先遵循本地的 [`evals/evaluation-protocol.md`](evals/evaluation-protocol.md)，再使用以下命令对准备好的输出和判定结果评分：

```sh
python3 -I evals/score_eval.py \
  --manifest artifacts/run-manifest.json \
  --schedule artifacts/evaluation-schedule.jsonl \
  --prompts evals/evaluation-prompts.jsonl \
  --oracle evals/evaluation-oracle.jsonl \
  --outputs artifacts/evaluation-outputs.jsonl \
  --judgments artifacts/evaluation-judgments.jsonl \
  --routing-trace artifacts/evaluation-routing.jsonl \
  --report artifacts/evaluation-report.json
```

这些检查验证评测结构和评分机制。持续集成通过不能衡量行为效果，pilot 也不是有效率百分比；本文档并未声称该技能已被证明有效。

## 仓库结构

技能运行目录仅包含：

- `no-reask/SKILL.md` — 行为指令和判断边界。
- `no-reask/agents/openai.yaml` — 面向代理的展示元数据和默认提示。

开发与评测文件位于技能运行目录之外：

- `evals/` — 冻结的评测材料、协议和确定性评分器。
- `tests/` — 自动化仓库契约检查。
- `.github/workflows/test.yml` — 持续集成工作流。

## 开发验证

请在仓库根目录运行完整的本地测试套件：

```sh
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

## 反馈

若要反馈行为偏差，请提供原始请求、实际输出和预期输出，并说明技能是被显式调用还是被隐式发现。提交前，请移除凭证以及私密或内部信息。
