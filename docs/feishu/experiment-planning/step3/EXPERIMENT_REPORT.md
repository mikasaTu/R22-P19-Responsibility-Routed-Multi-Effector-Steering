---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/LgRywtfpoiCeGlkfYsgc2X3Jnaf
wiki_node_token: LgRywtfpoiCeGlkfYsgc2X3Jnaf
document_token: ESwHd46MCohwINxWVVycwbOQn5D
revision_id: 5
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: c7b66ffdec1ff3d012f1f219e1fa4de7441eda74780e1da7aa4436dcbd89b9e1
---

<title>实验报告</title>

# R22-P19 Stage 2B 实验报告

**日期：**2026-08-14

**任务：**RoboTwin handover_block 双臂交接

**最终判定：**SIGNAL_VALID_OPERATOR_WEAK

**验收标记：**accepted=false

**证据边界：**本报告只覆盖 simulator-privileged contact-aware counterfactual signal 与 simulator oracle 1-D operator pilot；不代表 learned estimator、VLA、可部署闭环、真机或论文级验收。

## 0. 执行摘要

- **Stage 2B-I：MULTISEED_SIGNAL_SUPPORTED。**在 calibration seeds 0、1 上冻结非极端 gamma=0.6 后，5 个 held-out seeds 2、3、5、6、7 的 episode-level valid-pair rate 均为 0.8529–0.8824，均值 0.8706，95% CI [0.8588, 0.8824]；有效 pair 上 oracle orientation accuracy 为 1.0000，95% CI [1.0000, 1.0000]；shuffled orientation control 为 0.5001。
- **Stage 2B-II：SIGNAL_VALID_OPERATOR_WEAK。**5 episodes × 4 conditions × 12 methods 的 240/240 paired replays 全部完成；所有 run 都 success 且无 drop，但 B11 未在 stress 条件下对三项主 disturbance 指标形成一致改善，specificity 未证明。
- **机制结论：**signal 的改善来自 contact-aware follower 去除了 e_parallel 上的刚性运动学对抗；operator 无稳定收益主要因为 ridge 主导使连续修正近乎为零、joint/guard 激活稀疏、stress 未打破 success ceiling，以及 PhysX 未暴露 solver warm-start cache 导致的 replay noise floor。
- **训练边界：**冻结计划明确要求 oracle operator 有稳定正趋势之后才进入 ACT；当前 gate 未通过，所以 ACT 未运行、PAI job 未创建，也未训练 responsibility network、Diffusion Policy 或 pi0.5。

## 1. 冻结问题与实验设计

验证链被拆成两个独立问题：

1. 通过有效的 contact-aware authority intervention，counterfactual causal responsibility 能否跨多个 episode 稳定识别人为指定的物体控制方向？
2. 给定 simulator oracle responsibility，保持基础 expert 总 object effect 的 1-D command transfer 能否降低交接 disturbance，而不改变 expert 的其他动作分量？

本阶段没有先训练 ACT，也没有训练责任估计器。Stage 2B-I 通过后直接使用 simulator oracle 进入 bounded operator pilot。

### 1.1 运行合同

- RoboTwin commit：266f3aadf505a4f7fe9af0faa41a20f5f47cd123。
- XPolicyLab pinned commit：c37109c500be67d0dea6b36bf7337bbd26e763cd。
- planner：mplib_screw；physics/control frequency：250 Hz。
- dev14 bounded simulator run；未创建 PAI job。
- 统计单位为 episode，branch point/replay 不作为独立推断样本；bootstrap 10,000 次，seed 22019。

## 2. Stage 2B-I：Contact-Aware Authority Replication

### 2.1 为什么需要新干预

Stage 2A 普通 direction/null 在 92 个 paired state-horizon 中产生 0 个 intervention-valid authority swap。原因不是 oracle direction 必然错误，而是非主导手仍以刚性位置目标抓住物体，使正确的 driver TCP command 无法转化成 object-driving motion。

### 2.2 实现

控制器不提供 Cartesian anisotropic stiffness；因此按照冻结计划使用 follower-target fallback。建立 object task frame：

- e_parallel：物体朝目标 functional point 的水平投影方向；
- e_vertical：world-up；
- e_perp：水平正交方向；
- rotation、vertical、perp：保持 snapshot target；
- 两个 gripper：保持原 drive target，不通过开爪制造 authority。

driver 沿 e_parallel 接收 4 mm 命令。follower 只在 e_parallel 上跟踪物体位移的 (1-gamma) 部分；这里 gamma 是“保留的 parallel position error ratio”，并非物理刚度值。

### 2.3 Calibration / held-out 分离

- calibration seeds：0、1；held-out seeds：2、3、5、6、7。
- 候选 gamma：0.6、0.4、0.2；0.05 仅作 diagnostic positive control。
- 冻结规则：选择两个 calibration episode 均满足 valid-pair rate 下限的最大非极端 gamma。
- 最终冻结 gamma=0.6；synergy threshold=0.2；held-out 阶段未调参。
- 冻结配置 SHA-256：30e80b4811c17ceafd9c928cd583ac8505ebb764a8cc8f19b57db7917e08a3b1。
- 采样窗口：[E4-250, min(E5, E4+150)]，stride=25；H=5、10；每个 state/profile/horizon 均跑 LR/L/R/ZERO。

### 2.4 Held-out 逐 episode 结果（gamma=0.6）

- seed 2：30/34 valid，rate=0.8824，oracle accuracy=1.0000。
- seed 3：29/34 valid，rate=0.8529，oracle accuracy=1.0000。
- seed 5：29/34 valid，rate=0.8529，oracle accuracy=1.0000。
- seed 6：30/34 valid，rate=0.8824，oracle accuracy=1.0000。
- seed 7：30/34 valid，rate=0.8824，oracle accuracy=1.0000。

**聚合结果：**episode valid-pair rate mean=0.8706，95% CI [0.8588, 0.8824]；oracle accuracy mean=1.0000，95% CI [1.0000, 1.0000]；shuffled orientation=0.5001；所有 episode 的 median responsibility margin=2.0。

gamma=0.6、0.4、0.2、0.05 得到相同的 held-out validity 概要。因此 positive signal 不依赖全臂 0.05 极端诊断。

### 2.5 Stage 2B-I 判定与边界

**判定：MULTISEED_SIGNAL_SUPPORTED。**

但 rho_joint median 数值上接近 0，joint-mode occupancy=0。原因是每个 LEFT/RIGHT profile 只有一个 active driver，LR 与 active singleton 在构造上重合，而另一 singleton 为 neutral。故本结果证明“匹配干预下的 orientation 可重复”，不证明自然未干预责任、interaction synergy 或可部署责任估计器。

## 3. Stage 2B-II：Oracle Closed-Loop Operator

### 3.1 1-D responsibility-conserving operator

operator 只修改 e_parallel 分量；其他平移、旋转和 gripper command 保持 expert，除非 release guard 阻止 donor open。每 25 physics steps 用 simulator central finite difference 估计 b_L、b_R，并求解两个标量动作。目标同时拟合 rho_L、rho_R 分配，并严格保持 b_L\*a_L + b_R\*a_R 等于基础 d_base；ridge lambda=0.05，trust region=0.002 m。

当 abs(rho_joint) 大于冻结 threshold 0.2 时，three-way 版本进入 JOINT_SUPPORT 并保持 base split；release guard 独立检查 receiver stable contact、support responsibility、retention、slip/drop risk。

### 3.2 Paired matrix

- held-out episodes：seeds 2、3、5、6、7。
- conditions：clean、receiver_gain_0p7、receiver_delay_2、receiver_friction_0p7。
- methods：B0–B11，包括 phase、distance、force、direct scaling、conservation-only、two-way、three-way、shuffled、operator-null、release-only 与 full。
- pairing：同一 expert low-level tape、同一 in-memory E2 snapshot、seed、condition、frequency；所有 method 均执行同样的 estimator branch schedule；method order 按 seed/condition 轮换。
- 完整性：240 expected / 240 observed / 240 unique。

### 3.3 Task 与 stress 结果

240/240 runs 全部 success、无 drop、无 premature release。三个 stress 下 B0 success 仍为 1.0，因此计划要求的 40%–80% base-success stress target 未达到；binary task metrics 处于 ceiling，不能证明 operator rescue。

pilot-v2 曾把 donor release 后的自然 separation 计入 slip。该指标被判定无效，run 保留在 INVALID_METRIC lineage 中但不参与推断。最终 pilot-v3 的 slip 只在对应 gripper 仍与 object 接触的 physics steps 计算。

### 3.4 B11 对比结果

以下是三个 stress condition 聚合后的 episode-paired B11-minus-comparator，负数表示 B11 更低；括号内为 95% CI：

- 相对 B0：angular velocity -0.2091 [-0.6718, 0.2537]；linear jerk +0.0616 [-0.8389, 0.8272]；contact-masked slip +0.000104 m [-0.000088, 0.000350]。
- 相对 B5 conservation-only：angular -0.3489 [-0.5979, -0.1000]；jerk -0.6255 [-1.6510, 0.4000]；slip +0.000060 m [-0.000079, 0.000224]。
- 相对 B8 shuffled：angular -0.0670 [-0.5188, 0.3203]；jerk +0.4551 [-0.2329, 1.1131]；slip +0.000076 m [-0.000102, 0.000310]。
- 相对 B9 correct responsibility + operator-null：angular -0.3518 [-0.7271, -0.1269]；jerk -0.1223 [-1.1757, 0.7584]；slip +0.000106 m [-0.000045, 0.000319]。

B11 没有在每个 stress condition 上同时改善 angular velocity、jerk 和 slip；其在所有三项指标上击败全部 phase/distance/force heuristic 的 stress 数为 0/3。因此 operator-positive criterion 与 specificity criterion 均未通过。

### 3.5 守恒、激活和成本

- B11 solver feasible rate 最低值：1.0000。
- B11 最大 mean absolute effect-conservation error：1.24e-21 m。
- B11 median action correction：5.42e-20 m；P95=1.95e-6 m；大于 1 micrometre 的比例为 11.73%。
- B11 JOINT_SUPPORT：75/23,124 logged steps，约 0.324%。
- B11 release guard blocks：25/5,200 open requests，约 0.481%；B10 为 75/5,200。
- 额外计算：89,856 simulator branches，449,280 simulated physics steps；estimator 305.7 s，solver 93.1 s，replay 890.5 s。

## 4. 代码反解：为什么会提升或降低

### 4.1 Signal 为什么从无效变为稳定

TaskFrameFollower 读取 snapshot 后的 object displacement，仅投影到 e_parallel，并将 follower setpoint 沿该轴移动 (1-gamma) 倍；rotation 与其他支撑轴仍回到 snapshot target。这个代码路径精确移除了原先阻止 driver 产生 object motion 的平行刚性约束，同时不打开 gripper。因此 valid-pair rate 的提升与 intervention-validity 改善一致。

### 4.2 Operator 为什么几乎不改变动作

KKT Hessian 的对角项为 b_i² + lambda。B7 日志的 median b_i²=1.863e-4，而 lambda=0.05，比例为 268.36。ridge 因而压倒 responsibility target；在 exact conservation 约束下，最优解几乎返回 base action。这解释了“守恒误差约 1e-21 m、可行率 100%，但闭环无稳定收益”的表面矛盾：代数正确不等于控制有效。

### 4.3 为什么小幅升降不能归因于 routing

B0 与 B9 执行完全相同的 arm/gripper targets 和 oracle branch schedule，但最大 absolute episode difference 仍达到 angular velocity 0.6235、linear jerk 2.3277、slip 0.000610 m。SAPIEN snapshot 不暴露 PhysX solver warm-start cache；虽然已轮换 method order，n=5 仍小。多数 routing effect 与正负交替的 CI 都落在此 empirical replay/hidden-state noise floor 内，因此不能把局部提升或下降解释成责任路由的因果效果。

### 4.4 Three-way 与 release guard 为什么不可辨识

JOINT_SUPPORT 仅占 B11 logged steps 的 0.324%，two-way 与 three-way 在绝大多数步骤执行同样模式。release guard 也只阻止 0.481% 的请求，并且所有 run 都成功、无 drop。因此两项机制既缺少激活量，也缺少失败 headroom，当前 pilot 无法估计其 task-level benefit。

### 4.5 机制总结

signal 正结果由“去除 follower 在 task direction 的刚性 opposition”解释；operator 弱结果由“regularization-dominated near-null map + sparse joint/guard activation + insufficient stress + replay noise”共同解释。这里没有生成新 idea，也不把当前具体实现的失败外推为对原始命题的全面否定。

## 5. 最终多维判定

- signal validity：MULTISEED_SIGNAL_SUPPORTED。
- operator validity：WEAK_NOT_DEMONSTRATED。
- specificity：NOT_DEMONSTRATED。
- policy compatibility：NOT_TESTED。
- deployability：NOT_TESTED_SIMULATOR_ORACLE_ONLY。
- current decision：SIGNAL_VALID_OPERATOR_WEAK。
- accepted：false。

## 6. ACT / PAI 边界

已按 pai-vla-training、pai-spot-autoresume、pai-web-training-orchestrator 的要求核对训练门槛，但本阶段没有创建 PAI job。原因不是资源不足，而是冻结计划明确要求：只有 oracle operator 出现稳定正趋势后才能训练 ACT。当前 operator gate 未通过，故 ACT status=SKIPPED_BY_ORACLE_OPERATOR_GATE，training_authorized_by_current_gate=false。

## 7. 验证与完整性

- dev14 全量 Stage 2 + Stage 2B tests：37 passed in 4.89 s；合并 main 后再次通过。
- held-out signal metrics 独立重算后逐字节一致，SHA-256=4973be4026034a23501236db82c17af60f1c385a32995338785abfd240bf3f30。
- operator metrics 独立重算后逐字节一致，SHA-256=75b2ee06b7210ad5c1770ddf2d24e2a1186e75c1d8a6e0e5416625dd8b0df87d。
- Stage 2B artifact scan：523 JSONL/JSONL.GZ files、596,320 rows；526 NPZ；9 Parquet、42,883 rows；21 MP4、4,130 decoded frames；3 PNG；0 symlink；0 high-confidence secret finding；largest file 2,123,101 bytes。
- expert tape 中 [NaN, NaN] 仅表示“该 physics step 没有新的 gripper command”的序列化哨兵；它们始终成对、只出现在 expert_tapes 的 gripper arrays。真实 replay 使用原始 in-memory None，并未把 NaN 当动作执行；其余扫描数值数组均 finite。

## 8. 失败 lineage 保留

- Stage 2A 普通 direction/null 0 valid swap 与强 0.05 diagnostic lineage 均保留。
- Stage 2B calibration-v1 的 E5 drift 审计保留；正式结论使用分离 E5 drift 与冻结 E4-relative anchors 的 calibration-v2。
- operator pilot-v1 保留；pilot-v2 的 slip 指标错误以 INVALID_METRIC 标记并排除；正式推断使用 pilot-v3-contact-slip。

## 9. GitHub 交付

代码、配置、tests、raw branches/traces、operator logs、raw replays、videos、plots、machine-readable decisions、审计与复现实验报告已纳入 main。

**目标仓库：**[mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering)

**最终提交：**8b63ef5ef47037ab31c7c1e60e4da0df174fb04a

**主要报告：**

- [SIGNAL_REPLICATION_REPORT.md](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2b/reports/SIGNAL_REPLICATION_REPORT.md)
- [ORACLE_OPERATOR_REPORT.md](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2b/reports/ORACLE_OPERATOR_REPORT.md)
- [MECHANISM_REVERSE_EXPLANATION.md](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2b/reports/MECHANISM_REVERSE_EXPLANATION.md)
- [CURRENT_STAGE2B_DECISION.json](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2b/reports/CURRENT_STAGE2B_DECISION.json)
- [STAGE2B_TEST_RESULTS.md](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2b/reports/STAGE2B_TEST_RESULTS.md)

## 10. 结论

第一段因果链获得了限定性支持：在不依赖 gamma=0.05 的 contact-aware matched intervention 下，counterfactual orientation 在 5 个 held-out handover episodes 中稳定复现。第二段因果链没有得到支持：当前 simulator-oracle 1-D conserved operator 在完整 240-run pilot 中没有形成一致 control improvement 或 specificity。科学上正确的停点是 SIGNAL_VALID_OPERATOR_WEAK，并按计划不进入 ACT/PAI 训练。
