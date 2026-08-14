# Step5 实验报告：R22-P19 V2 / Stage 2D

## 结论摘要

Stage 2D 没有推翻 Stage 2C 的负结论，也尚不支持完整 V2。解析分配器通过了
字面 gate，但两名独立 reviewer 均限定它只是一项 perfect-model target-following
sanity check。真实 RoboTwin active task 已建立并通过 10/10 expert smoke；然而
capacity calibration 没有任何合格 stress，且 calibration split 上组合 capacity
AUROC=0.478，低于 phase=0.906。按用户要求，local 与 320-cell closed-loop 诊断即使
在 gate 失败后仍全部执行，但不具备升级资格。

最终判定为 **`ORACLE_V2_NOT_SUPPORTED`**，机制判定
`TAKEOVER_CAPACITY_V2_NOT_SUPPORTED`，policy gate 为 `BLOCK`。全部下游实验已经
执行完毕；局部 proxy 改善不能覆盖 `NO_ELIGIBLE_STRESS`、`LOCAL_NO_GO` 和闭环退化。

## 1. 执行与资源合同

- 基线 commit：`e31e1ddc78e8ffa22c5dba51d2988151ec7f755f`
- branch：`stage2d-takeover-capacity-v2`
- 运行机：dev14；RoboTwin `266f3aad...`；SAPIEN `3.0.0b1`
- 最多使用 GPU1/GPU2 两张 A800；不终止已有作业
- CPU 完成 analytic；GPU 仅供实际 SAPIEN renderer/physics
- PAI 作业：0；ACT/π0.5/Diffusion/learned estimator：均未训练
- CPFS 保存原始日志；Git 仅保存紧凑 JSON、代码、测试和报告

## 2. Stage 2D-A：解析 4D 分配器

256 fixed seeds、A0--A7 全部完成。A4 correct target 的 contribution MAE=0.013723、
net error=0.001347、feasible=100%；A5 swapped MAE=0.603740，A6 random=0.338311。
A7 把 internal proxy 从 A4 的 0.018867 降为 0.010580，但 MAE 增至 0.015256。

字面 analytic gate 全通过；解释性决策为 `PARTIAL_ANALYTIC_ALLOCATOR_GO`。原因：
target 与评价指标同构、A0/A1 退化相同、模型增益完全已知、没有接触动力学。

## 3. 双 reviewer novelty 审查

- Reviewer 1：`BLOCK_FULL_V2_NOVELTY_INTERPRETATION / PARTIAL_MECHANISM_DISTINCT`
- Reviewer 2：`MECHANISM_IDENTIFIABILITY_NOT_ESTABLISHED`

两者一致认为当前最多证明“外生 desired target 不等于 self-target current，且
分配器能跟随”，不能证明 capacity target 来源正确、闭环接管、contact safety、
deployability 或 N3 novelty。

## 4. Active Handover Task

原始 handover overlap 的 moving fraction=17.5%、mean speed=1.44 mm/s，未通过
active gate。代码加入边界归零的 15 mm 双臂连续正弦参考后：10/10 active valid、
10/10 task success、moving fraction=81.24%、speed=5.77 mm/s、dual contact=95.25%。

提升机理是两臂共享同一世界坐标位移并在 overlap 两端返回原 expert tape，不是
阈值重定义。

## 5. Donor-fade Takeover Capacity

每个状态在独立 oracle scene 中运行 fade=1/0.75/0.5/0.25/0；gripper held，main
scene 从不 restore。horizon=50 的 clean+16 stress 共 146 个状态全部 capable，
AUROC 不可定义。horizon=200 的最强 7 个条件仅 1/70 failure：capacity AUROC=0.478，
translation=0.804，support=0.848，phase=0.906。

held-out 125 状态只有 2 negatives；组合 AUROC 虽为 1.0，但不能覆盖 calibration
失败和无 eligible stress。Brier=0.0287、ECE=0.1173。

## 6. Stress Calibration

完整扫描 gain、delay、friction、COM shift 与 reference acceleration 后，eligible
stress 数量为 0。后续三个条件只作为 `INELIGIBLE_STRESS_OVERRIDE`：

- T1 receiver gain=0.4
- T2 active amplitude=25 mm
- T3 COM shift=30 mm

## 7. Local causal gate

5 seeds × 5 states × L0--L8 × LR/L/R/ZERO 全部完成：225 个 method-state、
900 个 actual SAPIEN branches。L3 correct 的 contribution movement=-0.206788，
但 target MAE=0.161462、net error=0.251339、actual joint-action modification
ratio=0.791057，且 correct 未优于 shuffled/time-shifted。contact=1.0、internal
proxy=9.82e-06 只证明局部约束项可小，并不建立 target specificity。判定：
`LOCAL_NO_GO`。

## 8. Closed-loop C0--C15

320/320 fresh-process cells 完成，运行失败 0。C13 full 相对 C0/C12 的 success
差值在 clean/T1/T2/T3 分别为 -80/-60/-80/-80 pp。C8 correct 相对
swapped/shuffled/time-shifted 在四个条件中全部为 0 pp。C13 把 internal proxy
从约 0.245 降到 0.124--0.128，但 success 只有 1/5、2/5、1/5、1/5。

C5 actual-current trace 已对 20/20 condition-seed cells 独立重跑，0 运行失败，
四个条件均 5/5 success；其 clean/T1/T2/T3 trajectory RMSE 分别为
0.00401/0.01140/0.00466/0.00408 m。

首个 C13 smoke 揭示并由正式矩阵复现的机理是：capacity 只有 5 个稀疏节点，
desired state 从 0.1 起、每次 slew=0.08，receiver target 均值 0.329；0.5 release
guard 导致 420/420 donor-open 被阻断。完整机制改善 internal proxy，却错过释放时序，
因此轨迹误差和失败率上升。

## 9. 机理反解

详见 `MECHANISM_REVERSE_EXPLANATION.md`。所有提升/降低均追溯到具体 objective、
state update、reference adapter、capacity channel 或 release guard；未生成新 idea。

## 10. 证据边界

这是 privileged simulator-oracle 机制审计。没有 learned policy、PAI training、
deployable estimator、真实机器人或跨任务结果。commanded share 不称为 actual
contribution；只有 local four-branch audit 可作 actual contribution 证据。

## 11. 最终判定

- analytic：`PARTIAL_ANALYTIC_ALLOCATOR_GO`（仅 target-following sanity check）
- novelty：两名 reviewer 均阻断完整 V2/identifiability 解释
- capacity：`NO_ELIGIBLE_STRESS`
- local：`LOCAL_NO_GO`
- closed loop：full 退化、correct target 无 specificity
- final：`ORACLE_V2_NOT_SUPPORTED`；ACT/PAI/learned estimator 继续 `BLOCK`
