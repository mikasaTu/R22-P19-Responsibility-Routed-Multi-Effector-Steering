---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/XRB7wg9pKin6rvk9WsYciEf6npe
wiki_node_token: XRB7wg9pKin6rvk9WsYciEf6npe
document_token: QO3MdVLoOoFaDuxgUlScVVo4ngB
revision_id: 2
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: 5220ccfe728fee04fffbe712964f81ba7be65ec6d1a3ec63c2c4ec941b2cefc8
---

<title>实验报告</title>

# R22-P19 Phase-1：LIBERO Oracle Responsibility 初步验证

**结论：**LIBERO 窄化 substrate 验证结果为 **LIBERO_SUBSTRATE_NO_GO**。9 项预注册 gate 中 7 项通过、2 项失败，因此未进入 ACT，也未创建 PAI 训练或推理任务。

**证据状态：**本报告只包含 LIBERO 成功专家示范与 simulator privileged oracle counterfactual 证据；ACT oracle evidence 未产生；deployable responsibility learned=false；π0.5 used=false；real/video world model used=false；VLA generality proven=false；original bimanual Signal GO=not_tested；accepted=false。

## 1. 验证问题与 benchmark 替换

原始 R22-P19 假设要求在双臂交接中，用同一快照的 FULL/L/R/ZERO 反事实分支恢复随阶段和控制权限变化的因果责任，再通过 authority swap 排除固定身份捷径。标准 LIBERO 只有一只 Panda 机械臂，不能检验左臂到右臂的真实责任迁移。因此本实验只检验更窄的必要条件，不把结果外推为双臂或多执行器证据。

- **主任务：**`libero_goal/put_the_bowl_on_the_plate`，选取 demo 0–29，共 30 条成功专家轨迹。
- **gate-off 对照：**`libero_goal/push_the_plate_to_the_front_of_the_stove`，选取 demo 30–49，共 20 条成功专家轨迹。
- **主 action groups：**A=arm pose 维度 0–5，B=gripper 维度 6。
- **窄化 authority stress：**x translation 与 y translation 两个坐标子空间，gain 从 (1.30, 0.70) 交换为 (0.70, 1.30)。它只验证 gain-sensitive attribution，不等价于双臂 authority swap。
- **分支：**AB/FULL、A/ARM、B/GRIPPER、ZERO；从同一 simulator 快照运行 H=5 和 H=10，branch stride=5，控制频率 20 Hz。

Shapley-like attribution 使用：

$$\phi_A=\frac{1}{2}[(y_A-y_0)+(y_{AB}-y_B)]$$

$$\phi_B=\frac{1}{2}[(y_B-y_0)+(y_{AB}-y_A)]$$

$$s=y_{AB}-y_A-y_B+y_0$$

## 2. 冻结配置与运行来源

- **实验代码：**`codex/r22p19-libero-phase1`，commit `24d7cf3df4969275385ba977462c47e326211ae8`，远端 ref 已回读一致。
- **LIBERO：**official commit `8f1084e3132a39270c3a13ebe37270a43ece2a01`，运行时 source tree clean。
- **运行主机：**`dsw-925252-7796557db6-j84nn`；Python 3.8.13；UID:GID=`2254:2254`。
- **主数据 SHA256：**`e69528b0cf10dfc59b20698e12ec2affc03f3887309034d3eb74cac3ec929406`。
- **对照数据 SHA256：**`36b4e1bced49d2f4ff6b2fce6b1596a63978e14199e2513cd0df71e127bf47a6`。
- **冻结配置 SHA256：**`c4d062b5a20db940ec086ba47a2e89346dc509695d7138e8733b9d80682e910a`。
- **完整运行：**`signal-v1-20260813`，开始 2026-08-13 01:15:04 CST，完成 2026-08-13 01:33:18 CST。

## 3. 开发机 CPU smoke 与确定性边界

- dev14 实际 LIBERO Python 环境纯函数测试 3/3 通过。
- `smoke-v5-20260813`：重复快照恢复最大误差 0；相同 normalized hidden-state contract 的重复分支最终 flat-state 最大误差 0；单条轨迹 P1–P6 有序事件链通过。
- 完整运行在 3 条 demo、每条 3 个时间点复核：重复恢复与重复分支均 9/9 通过，误差 0。
- 本次 smoke/Oracle 审计为 CPU simulator 验证，无 GPU 训练、无策略推理。

**透明限制：**LIBERO HDF5 flat state 不保存 Python 侧 OSC controller buffers 与 `PandaGripper.current_action`，所以 `state[t]+action[t]` 不能唯一重构专家的 `state[t+1]`。首次 smoke 在任何 responsibility 结果产生前暴露了这一点。随后冻结统一分支干预：恢复每条 demo 的 MuJoCo state 与 model body poses；OSC anchor 到恢复后的 robot state；gripper target 设为恢复后的 finger qpos，以保持当前闭合度。精确 next-state replay 保留为非 gate 诊断；相同干预下的重复分支一致性才是确定性 gate。

## 4. 事件与人工数值审计

- P0 approach；P1 首次 gripper-object contact；P2 持续接触并 lift；P3 planar transport；P4 首次 opening command；P5 实际 contact loss；P6 release 后目标支撑或 success。
- 30/30 主任务 demo 得到有序 P1–P6，valid fraction=1.0000，门槛为 ≥0.80。
- 人工数值 trace audit 覆盖 demo 0–9，共 10/10 通过。逐事件核对 object z、gripper action、单/双指接触、target contact 与 reward；P6 被定义为 P5 后仍有 target support，避免把“先碰盘、后松手”误判为顺序错误。

## 5. 完整 Oracle 结果

主任务共 698 个 branch points（H=5：369；H=10：329），对应 2,792 次四分支 rollout。gate-off 对照 414 个 branch points。authority stress 有 225 个预注册 eligible transport 快照，对应 1,800 次 gain-swap 分支 rollout。

### 通过的 7 项 gate

- **事件有效率：**1.0000 ≥ 0.80，PASS。
- **phase AUC：**0.838872 ≥ 0.75，PASS。population 为 grasp_close 138 点、transport 471 点。
- **shuffle control：**200 次、seed 2219，AUC p95=0.549756 ≤ 0.60，PASS。
- **phase shift：**arm share 的 transport mean=0.859122，grasp_close mean=0.555955，差值 0.303167 ≥ 0.15，PASS。
- **Shapley conservation：**1,112 个主任务+对照点的 relative error 最大值 `3.0990e-14` ≤ 0.10，PASS。
- **authority eligible count：**225 ≥ 20，PASS。
- **authority swap response：**210/225 双方向响应正确，accuracy=0.933333 ≥ 0.80，PASS；x 单独 0.977778，y 单独 0.955556。

### 失败的 2 项 gate

- **超过 action-magnitude baseline：**responsibility phase AUC=0.838872；简单 arm-action-magnitude baseline 的最佳方向 AUC=0.793547；增益仅 0.045324，低于预注册 0.05，FAIL。说明 phase signal 很强，但尚不能充分排除“动作幅度本身”解释。
- **gate-off specificity：**push-task 中 gripper activation 为 47/414=0.113527，高于允许的 0.05，FAIL。说明当前 attribution 在本应由 arm push 主导的对照任务上仍有过度激活。

## 6. 判定与 ACT/PAI 阶段

**正式判定：LIBERO_SUBSTRATE_NO_GO。**本实验支持“counterfactual machinery 能恢复明显的 phase dependence、精确 conservation 与 gain-sensitive response”，但没有通过相对简单 baseline 的增益门槛，也没有通过 gate-off specificity。

- **ACT/PAI：**`SKIPPED_BY_PREREGISTERED_SIGNAL_GATE`。
- **PAI job created：**false；job_id=null。
- **training started：**false；**inference started：**false。
- **cleanup target count：**0；没有本实验的旧 PAI service 需要删除。
- 这是科学门控停止，不是 PAI 基础设施失败。若 Signal gate 通过，训练与推理才会按约定进入 PAI，并使用完整状态 checkpoint/autoresume；本次未满足启动条件。

## 7. 证据产物与完整性

- **持久化目录：**`/mnt/cpfs/zbl-cpfs-new/USERS/leon/logs/r22p19_libero_phase1/signal-v1-20260813`
- **关键文件：**`manifest.json`、`frozen_config.json`、`determinism.json`、`event_audits.jsonl`、`manual_event_audit.json`、`expert_traces.jsonl`、`primary_responsibility.jsonl`、`authority_swap.jsonl`、`control_responsibility.jsonl`、`metrics.json`、`decision.json`、`EVALUATION_COMPLETE.json`、`VERIFICATION.json`、`ACT_PAI_SKIPPED.json`。
- **metrics.json SHA256：**`693da04b14d6bbebe757ad769a7aef6fcaf7a13336d0f94dab1a93b223864dff`。
- **decision.json SHA256：**`06b90e08ede5645dfd88fd2fd0d195a5f933b0e6f94b7f94179e8fb36f696507`。
- **EVALUATION_COMPLETE.json SHA256：**`3b33c5de8ae1b522a9c323ea47420e802cdbed3538e2e8d7936c28fd8787f3ad`。
- 独立回读：10/10 手工数值事件审计通过；9 项 gate 重新统计为 7 PASS / 2 FAIL；所有关键 JSON/JSONL 的大小与 SHA256 已写入 `VERIFICATION.json`。

## 8. 建议的下一步

1. 先修正 oracle score 的 specificity：把纯 finger joint response 与 object-level causal motion 解耦，并在 push gate-off 上把 activation 从 0.1135 降到 ≤0.05。
2. 加入 matched-action-magnitude 或 residualized baseline，使 phase AUC 的增益稳健超过 0.05；不得直接降低预注册门槛。
3. 修正后使用全新 run_id 重复同一 30+20 demo gate；只有 9/9 全通过才启动 PAI ACT。
4. 即便 LIBERO substrate 通过，仍需回到真正双臂环境执行左右权限交换，才能回答原始 R22-P19 的核心命题。

**最终状态：**accepted=false；LIBERO substrate=NO_GO；ACT/PAI=skipped；original bimanual Signal GO=not_tested。
