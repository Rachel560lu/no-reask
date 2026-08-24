# Background: the question that should not have been asked again

**English** · [中文](#中文)

No Re-Ask began with a small interruption that is funny once and exhausting by
the twentieth time:

> I found the remaining work. The next step is clear. Would you like me to
> continue?

The user had already answered that question by asking for the work.

## A real version of the story

In August 2026, Reddit user
[u/BigBootyBear](https://www.reddit.com/r/webdev/comments/1vrs9cw/is_agentic_ai_making_you_procrastinate/)
described an awkward rhythm with coding agents: by the time the human starts
another activity, the agent asks for approval or asks what comes next. When the
human checks back, the agent may have spent the last ten minutes waiting for an
answer it did not materially need.

The comments supplied an unusually good product description. One developer
called the approval loop a strange combination of **"babysitting and
rubber-stamping."** Another said that approving even an `ls` command had become
a time sink.

That is the human problem behind No Re-Ask. The agent looks autonomous while it
is moving, but hands the steering wheel back at every conversational seam. The
human does not get an assistant; they get a very polite elevator that stops at
every floor to ask whether “up” still means up.

The Reddit post is evidence that this interaction is painful. It is not evidence
that every approval request is unnecessary, and it is not an efficacy claim for
this Skill.

## The line No Re-Ask does not cross

**No Re-Ask does not bypass security approval.** It addresses a conversational
re-ask after the user has already authorized a clear next action. It does not
suppress, replace, or weaken a host, tool, operating-system, or organizational
permission gate.

Continue without re-asking only when the next action is:

- already requested by the user;
- clearly inside the stated scope;
- feasible with the authority and information already available; and
- reversible.

Stop and ask one focused material question when the next action is destructive
or difficult to reverse, outside scope, externally consequential, dependent on
new credentials or authority, or blocked by a genuinely missing choice or
safety fact.

This distinction matters because repetitive system approvals create a related
but broader problem usually called approval fatigue. Anthropic has reported
that users approve the large majority of Claude Code permission prompts and has
introduced risk-based auto mode to reduce habitual clicking. That is a runtime
permission-system problem. No Re-Ask is narrower: it preserves the authorization
already present in the conversation while respecting every runtime gate. See
[Anthropic's auto mode explanation](https://claude.com/blog/auto-mode-default-in-claude-code)
for that adjacent problem.

## The rule in one sentence

If the user has already asked for it and nothing material has changed, finish
it. If the next action needs new authority, carries new risk, or requires a real
choice, ask.

---

## 中文

No Re-Ask 的起点，是一种第一次看着礼貌、第二十次只剩疲惫的小插曲：

> 我已经找到剩余工作，下一步也很明确。你希望我继续吗？

用户在提出任务时，其实已经回答过这个问题了。

### 一个真实版本

2026 年 8 月，Reddit 用户
[u/BigBootyBear](https://www.reddit.com/r/webdev/comments/1vrs9cw/is_agentic_ai_making_you_procrastinate/)
描述了与 Coding Agent 相处时的一种尴尬节奏：人刚准备做点别的，Agent
就请求批准，或者询问下一步是什么；等人回来查看时，它可能已经原地等了十分钟，
等待一个并非实质必要的回答。

评论区给出了一个意外准确的产品描述：这种循环把写代码变成了
**“babysitting and rubber-stamping”**，也就是一边照看 Agent，一边机械盖章。
还有开发者提到，连 `ls` 命令都要批准，也会变成一种全新的时间消耗。

这就是 No Re-Ask 背后的人类问题。Agent 工作时看起来很自主，却在每个对话接缝
把方向盘交还给用户。你得到的不是助手，而是一部过分礼貌的电梯：每到一层，
都要再问一次“向上还是向上吗？”

这篇 Reddit 帖子证明这种交互确实令人困扰，但它不能证明所有审批都是多余的，
也不是本 Skill 有效性的证据。

### No Re-Ask 不越过的线

**No Re-Ask 不跳过安全审批。**它处理的是用户已经授权明确下一步之后，Agent
在聊天层面的重复询问；它不会压过、替代或削弱宿主、工具、操作系统或组织设置的
权限门槛。

只有当下一步同时满足以下条件时，Agent 才应该不再重复询问而直接继续：

- 用户已经明确要求这项工作；
- 行动仍然位于声明的范围内；
- 现有信息与权限足以完成；
- 行动可逆。

如果下一步具有破坏性或难以恢复、超出范围、会对外产生重要影响、需要新的凭证或
授权，或者确实缺少关键选择或安全事实，Agent 应该停下来，只提出一个聚焦的
实质性问题。

这个区别很重要，因为高频系统审批还会产生一个相关但更广泛的问题：approval
fatigue，也就是审批疲劳。Anthropic 曾披露，用户会批准绝大多数 Claude Code
权限提示，因此推出了基于风险判断的 auto mode，以减少习惯性点击。那是运行时
权限系统的问题。No Re-Ask 的范围更窄：它只延续对话中已经存在的授权，同时尊重
所有运行时门槛。相关背景可参见
[Anthropic 对 auto mode 的说明](https://claude.com/blog/auto-mode-default-in-claude-code)。

### 一句话规则

用户已经要求、且实质条件没有变化，就完成它；下一步需要新授权、引入新风险或
必须由用户作出真实选择，就询问。
