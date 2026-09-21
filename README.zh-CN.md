# Consensus

[English](README.md) · [详细使用说明](docs/USAGE.md) · [协议说明](docs/PROTOCOL.md)

让 Agent 先独立回答，再互相讨论，最后返回可以检查的共识和分歧。

Consensus 是一个 Codex Desktop 插件，原本在本地以 **Discuss** 为名开发。
当前为实验性的 `0.1.0` 开源版本，是社区项目，与 OpenAI、Anthropic 没有官方隶属关系。

## 能做什么

- **本地双 Agent**：同一台电脑上的 Codex CLI 和 Claude Code CLI 分别独立回答，
  然后自动交换观点并讨论。默认最多 10 轮，由当前 Codex Desktop 任务总结。
- **GitHub 多 Agent**：你和同事各自在自己的 Codex Desktop 中发起或加入讨论，
  GitHub Issue 保存任务、回答和讨论。支持 2–8 个参与者，按顺序发言。
  每次“继续讨论”最多发布一个讨论回合中的发言，不需要常驻服务。

共识必须针对同一段确定的结论文本，所有参与者都要明确接受。
达到轮数上限仍未一致时，保留各方结论和未解决的问题。
**共识不等于正确**：多个 Agent 可能有相同的知识盲点，最终仍需检查证据。

## 安装

在支持插件 marketplace 的 Codex CLI 中运行：

```bash
codex plugin marketplace add sufferfml/consensus
codex plugin add consensus@consensus
```

然后在 Codex Desktop 中**新建任务**，在插件选择器中引用 `consensus`，再发送问题。
无需提前打开 Claude Code 的交互终端。

## 本地模式

安装 Python 3.10+，确保 `codex` 和 `claude` 在 PATH 上且完成认证。
引用插件后输入：

> 请让 Codex 和 Claude 独立分析下面的方案，再互相讨论，最多 10 轮。
> 返回共识结论、未解决的分歧以及讨论终结原因。方案是：……

Claude 使用你已有的用户级网关、认证与模型设置。
如果要为辩手单独选模型，可设置 `DUAL_AGENT_CODEX_MODEL` 和
`DUAL_AGENT_CLAUDE_MODEL`，但环境变量必须对启动插件的进程可见。
从 Dock 打开的桌面程序不一定继承终端里的 `export`。

本地模式经过 macOS、Codex CLI `0.153.0`、Claude Code `2.1.258` 的真实调用验证。
这些是已验证版本，不代表最新版本；Windows 暂未验证。

## 与同事讨论

1. 你引用插件：`在 OWNER/REPO 发起 GitHub 讨论：……`
2. 将返回的 Issue 链接交给同事。
3. 同事在自己的新任务中引用插件：`加入讨论：Issue 链接`。
4. 双方轮流调用：`继续讨论：Issue 链接`。
5. 达成共识或达到轮数上限后，由发起者总结。

双方使用各自的 `gh` 登录和仓库权限。插件不管理 GitHub 权限，也不会自行轮询；
如需自动检查，可以另行设置 Codex 定时任务。

独立阶段采用“先承诺、后公开”：先保存回答并发布其哈希承诺，之后才允许读取
评论并公开答案。其他兼容 Agent 也可以通过 Python helper 参与，但必须遵守
[协议和字段要求](docs/PROTOCOL.md)。这不提供任意 Agent 的自动接入适配器。

## 记录与边界

本地运行产生 `result.json`、`transcript.md`、原始 CLI 响应与结构化回合文件，
路径会显示在运行结果中。GitHub 模式把讨论保存在 Issue 评论，未公开的初始答案
保存在本机 `~/.codex/github-agent-consensus/`。

Codex 使用只读沙箱。Claude 使用 `safe-mode + plan` 并限制可用工具，仍然允许
Bash；“只运行只读命令”有一部分依赖 Agent 遵守协议，并不是操作系统级隔离。
不要把它当作能安全执行任意不可信代码的沙箱。

任务和读取的文件可能发送至配置的模型服务或网关；GitHub 内容对有仓库访问权的
人可见。日志不自动脱敏，不要把真实讨论、凭证或个人 CLI 配置提交到本仓库。
详见 [安全说明](SECURITY.md) 和 [隐私说明](PRIVACY.md)。

## 参与开发

```bash
git clone https://github.com/sufferfml/consensus.git
cd consensus
python3 tools/check.py
```

测试使用模拟 CLI，不调用付费模型、不创建 GitHub Issue。
欢迎用中文或英文提交问题和 PR。详见 [贡献指南](CONTRIBUTING.md)。

以 [MIT 许可证](LICENSE) 开源。
