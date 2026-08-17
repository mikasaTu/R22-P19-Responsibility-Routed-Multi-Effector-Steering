# R22-P19B Stage3A：Hybrid Takeover Mode Upper-Bound and Identifiability Pilot

你是一名严格、怀疑主义导向的机器人学习研究工程师。你的任务不是继续美化旧的 R22-P19 结果，而是在现有负结果基础上，实施一个新的、可证伪的 Stage3A 实验。

仓库：

`https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering`

当前历史结论：

* Stage2C：自然 responsibility 不稳定，正确 responsibility 没有造成实际 contribution transfer；
* Stage2D：完整 V2 不受支持，真实 closed-loop 没有使用同一个注册 4D allocator；
* Stage2E：command-space motion/support/rotation withdrawal 没有改变对应物理 contact effect，gripper opening 则会同时破坏全部 contact-wrench channels；
* 当前旧机制必须保持 `accepted=false`，不能被新实验改写为 positive。

本阶段的新 proposal 名称：

`R22-P19B Counterfactual Takeover-Feasibility Routed Hybrid Multi-Effector Steering`

本阶段只验证：

1. 是否存在可改善 handover outcome 的离散 mode candidate set；
2. 有限 horizon 的反事实后果是否能够预测完整未来 takeover success。

本阶段禁止：

* 训练 ACT；
* 训练 π0.5；
* 训练 Diffusion Policy；
* 训练视觉 VLA；
* 训练 responsibility-share estimator；
* 使用连续 `rho_left/rho_right` 作为 steering target；
* 使用旧的 1D nullspace transfer 作为 proposed；
* 使用手工 `effect4` Jacobian edit 作为 proposed；
* 宣称 deployability；
* 创建 PAI job；
* 修改或删除 Stage2 历史负结果；
* 在 formal branch cell 中使用 snapshot restore；
* 在实验失败时伪造结果或降低预注册阈值。

## 0. 仓库和分支

1. 审核当前 `main`。

2. 新建工作分支：

   `stage3-hybrid-takeover-routing`

3. 历史目录保持只读：

   * `docs/`
   * `evidence/`
   * `r22p19_libero/`
   * `stage2_robotwin/stage2b/`
   * `stage2_robotwin/stage2c/`
   * `stage2_robotwin/stage2d/`
   * `stage2_robotwin/stage2e/`

4. 新建：

```text
stage3_hybrid/
  preregistration/
  modes/
  replay/
  outcomes/
  calibration/
  ranker/
  scripts/
  tests/
  results/
  reports/
```

5. 继续使用冻结 runtime：

* RoboTwin commit：`266f3aadf505a4f7fe9af0faa41a20f5f47cd123`
* planner：`mplib_screw`
* SAPIEN/RoboTwin runtime 沿用 Stage2D/2E
* 最多使用 2 张空闲 GPU
* 不终止其他用户或已有作业
* 原始大文件保存在 CPFS，Git 只提交紧凑结果、配置、代码、测试和报告

如果 runtime 不可用，完成代码、单元测试和 preflight，并输出 `BLOCKED_RUNTIME`；不得声称物理实验已完成。

## 1. 冻结新 hypothesis

在任何 mode outcome 结果产生前，创建：

```text
stage3_hybrid/preregistration/HYPOTHESIS.md
stage3_hybrid/preregistration/EXPERIMENT_CONTRACT.yaml
stage3_hybrid/preregistration/MODE_CONTRACT.yaml
```

冻结核心命题：

> 在相同 handover 状态下，不同 donor release role-transition modes 会产生不同的完整未来 outcome。若该候选空间存在可改善上界，则有限 horizon 的反事实物理后果可以用于选择更可能安全完成 handover 的 mode。

明确写出：

* full-future oracle 只是 candidate-set upper bound；
* bounded-horizon ranker 才是 Stage3A 的非平凡信号验证；
* 不再把 current contribution、takeover capacity、desired mode 和 commanded action 混为同一变量；
* `accepted=false`；
* Stage2 历史结论不被覆盖。

## 2. 决策点

每个 episode 只使用一个正式决策点：

```python
t_anchor = max(E3 + 25, E4 - 100)
```

250 Hz 下，`E4-100` 约为原 donor release 前 0.4 秒。

必须记录：

* `E3`
* `E4`
* `t_anchor`
* prefix hash
* receiver command hash
* donor base command hash
* mode-modified donor command hash

episode 是唯一统计推断单位，不能把相邻 physics step 当独立样本。

## 3. 实现 mode candidate library

实现以下 6 个 mode：

### M0_BASE

完全使用原 expert tape。

### M1_EARLY_100

从 `E4-100` 开始，将 donor 的 post-E4 release/retract arm+gripper subchunk 提前执行。

### M2_EARLY_50

从 `E4-50` 开始执行 donor 的 post-E4 release/retract subchunk。

### M3_DELAY_50

在原 E4 之后保持 donor 的 pre-release arm target、velocity target 和 gripper closure 50 physics steps，然后恢复 time-shifted donor post-E4 subchunk。

### M4_DELAY_100

同上，延迟 100 physics steps。

### M5_ABORT_HOLD

donor 保持 pre-release arm pose、velocity target 和 gripper closure，直到 episode timeout 或预注册的 abort horizon。

关键实现合同：

* 不能只 time-shift gripper，必须同时 time-shift donor release/retract arm subchunk；
* receiver command 在所有 mode 中 byte-identical；
* 不修改 receiver gain、receiver target 或 receiver gripper；
* 不使用 Jacobian residual；
* 不使用 stiffness/wrench channel withdrawal；
* 不使用 responsibility share；
* 每个 mode 的实际 command path 必须通过 runtime receipt 验证；
* M0 必须与未修改 expert replay 完全一致。

创建至少以下文件：

```text
stage3_hybrid/modes/donor_release_timewarp.py
stage3_hybrid/modes/candidate_library.py
stage3_hybrid/tests/test_modes.py
```

## 4. Fresh-process branch runner

创建：

```text
stage3_hybrid/replay/fresh_process_mode_runner.py
stage3_hybrid/scripts/run_mode_cell.py
```

每个：

```text
seed × condition × mode × repeat
```

必须：

* 使用独立进程；
* 创建 fresh RoboTwin scene；
* 从 episode 起点 replay；
* 不使用 snapshot restore；
* method difference 只从 `t_anchor` 开始；
* launch order 随机化；
* repeat=2；
* 保存完整运行 receipt；
* 保存 prefix hash；
* 保存 receiver command hash；
* 保存 donor command modification summary；
* 保存 failure traceback；
* 不覆盖正式结果目录。

同一个 `seed × condition` 下所有 mode 的 prefix hash 必须一致。

## 5. 完整未来 outcome 标签

每个 mode branch 必须运行到 episode 结束，保存：

```text
eventual_task_success
handover_complete
receiver_only_retention
drop
takeover_failure
donor_final_contact
receiver_final_contact
donor_residual_contact_duration
receiver_takeover_delay
min_object_height
trajectory_rmse
peak_linear_jerk
peak_angular_velocity
contact_masked_slip
action_deviation_from_base
release_time
```

定义 `takeover_success` 时，至少要求：

* donor 实际失去接触；
* receiver 保持接触达到预注册持续时间；
* 无 drop；
* object height 不低于预注册阈值；
* 最终 task success。

不要把这些完整未来结果作为 bounded-horizon predictor 的输入。

创建：

```text
stage3_hybrid/outcomes/takeover_label.py
stage3_hybrid/outcomes/disturbance_metrics.py
```

## 6. Calibration stress 搜索

使用：

```text
calibration seeds: [0, 1]
held-out seeds: [2, 3, 5, 6, 7, 8, 9, 10]
```

先执行单因素 coarse search：

```text
receiver_gain: [1.0, 0.7, 0.5, 0.35]
receiver_delay_steps: [0, 4, 8, 12]
receiver_friction_scale: [1.0, 0.7, 0.5, 0.3]
object_com_shift_mm: [0, 15, 30]
receiver_grasp_offset_mm: [0, 5, 10]
```

如果无 eligible 单因素，最多执行 6 个冻结后的两因素组合。禁止无上限搜索或根据 held-out 结果调 stress。

每个 stress 的 eligibility 必须同时满足：

```text
0.30 <= base_success <= 0.80
candidate_disagreement_rate >= 0.30
full_oracle_success - base_success >= 0.15
full_oracle_success >= 0.60
```

其中 candidate disagreement 定义为：

* 同一个 episode 内至少一个 mode 成功、一个 mode 失败；或
* 所有 mode success 相同，但主要 disturbance 的 mode spread 超过预注册阈值。

至少冻结 2 个 eligible stress。

若没有，输出：

```text
NO_INFORMATIVE_FAILURE_SPACE
```

并停止 held-out formal matrix。可以完成必要诊断，但不能继续训练 ranker。

创建：

```text
stage3_hybrid/calibration/search_informative_stress.py
stage3_hybrid/reports/STRESS_CALIBRATION_REPORT.md
stage3_hybrid/reports/STRESS_CALIBRATION_DECISION.json
```

## 7. Stage3A-1：Full-future oracle upper bound

对每个 `episode × condition` 的 6 个完整 mode outcome，按以下字典序选择最佳：

1. task success；
2. no drop；
3. no takeover failure；
4. lower disturbance；
5. lower action deviation。

输出：

* base success；
* best-of-K oracle success；
* worst-mode success；
* candidate disagreement；
* oracle gain；
* oracle regret；
* 各 mode 被选择频率；
* episode-level paired bootstrap CI。

full-future oracle 必须明确标为：

```text
PRIVILEGED_CANDIDATE_SET_UPPER_BOUND
```

不得称为可部署方法。

Stage3A-1 GO 条件：

```text
eligible_stress_count >= 2
heldout_candidate_disagreement_rate >= 0.30
oracle_success_gain >= 0.15
```

或者在 success 相同的情况下：

```text
primary_disturbance_reduction >= 0.20
paired_CI_excludes_zero
no_success_degradation
```

失败则输出：

```text
MODE_LIBRARY_NO_GO
```

并禁止 Stage3A-2。

## 8. Stage3A-2：Bounded-horizon consequence ranker

只有 Stage3A-1 GO 后执行。

为每个 candidate 额外运行或提取固定短 horizon：

```text
H = [50, 100, 200] physics steps
```

只使用短期 feature：

```text
mode_id
release_offset
receiver_contact_fraction
donor_contact_fraction
receiver_final_contact_at_H
donor_final_contact_at_H
min_object_height_at_H
object_pose_error_at_H
peak_linear_velocity_at_H
peak_angular_velocity_at_H
slip_at_H
task_progress_at_H
contact_transfer_progress_at_H
```

使用 calibration episodes 拟合一个简单透明的 candidate-conditioned ranker：

* 首选 logistic regression；
* 可增加小型 MLP 作为 secondary；
* 不使用 RGB；
* 不使用大模型；
* 不允许同一 episode 的不同 branches 跨 train/test；
* 不根据 held-out 结果选择特征或阈值。

预测：

```text
P(eventual_takeover_success | short_horizon_outcome, mode)
```

评价：

```text
pairwise_ranking_accuracy
top1_mode_accuracy
selected_mode_success
oracle_regret
AUROC
Brier
ECE
correct_vs_episode_shuffled
correct_vs_time_shifted
correct_vs_inverted
```

Stage3A-2 GO 条件：

```text
pairwise_ranking_accuracy >= 0.70
recovered_oracle_gain_fraction >= 0.70
selected_success_gain_over_base >= 0.10
correct_beats_shuffled == true
correct_beats_time_shifted == true
clean_success_drop <= 0.03
eligible_stresses_passed >= 2
```

否则输出：

```text
SHORT_HORIZON_SIGNAL_WEAK
```

通过则输出：

```text
HYBRID_ROUTING_SIGNAL_GO
```

注意：即使通过，本阶段仍然 `accepted=false`，也不直接训练 ACT、π0.5 或视觉 critic。

## 9. 必须包含的 baselines

正式分析至少包含：

```text
B0_BASE
B1_FIXED_ORIGINAL_RELEASE
B2_RECEIVER_CONTACT_HEURISTIC
B3_FORCE_IMPULSE_HEURISTIC
B4_LINEAR_PHASE_RULE
B5_RANDOM_MODE
B6_FULL_FUTURE_ORACLE
B7_BOUNDED_HORIZON_CORRECT
B8_EPISODE_SHUFFLED
B9_TIME_SHIFTED
B10_INVERTED_RANKING
B11_ORACLE_NULL_ALWAYS_BASE
```

所有方法：

* 使用相同候选库；
* 使用相同 branch budget；
* 使用相同 held-out episodes；
* 使用相同 observation 和 prefix；
* 不允许 correct method 获得额外 mode；
* 不允许 wrong controls 使用更少计算预算。

## 10. 测试要求

至少实现并通过：

```text
test_mode_timewarp_preserves_receiver_commands
test_base_mode_is_exact_noop
test_delayed_release_shifts_arm_and_gripper_together
test_prefix_hash_matches_across_modes
test_fresh_process_contract
test_no_snapshot_restore_in_formal_runner
test_outcome_label_independent_of_short_horizon_features
test_episode_split_has_no_leakage
test_full_oracle_lexicographic_selection
test_shuffled_control_changes_episode_mapping
test_analysis_fails_closed_on_missing_cells
test_decision_gate_fails_closed
```

更新统一测试入口，使 Stage2 和 Stage3 tests 都可被显式运行。不要依赖当前 `pyproject.toml` 只发现部分 Stage2 tests 的默认行为。

## 11. 结果与报告

提交以下紧凑交付物：

```text
stage3_hybrid/results/PROVENANCE.json
stage3_hybrid/results/launch_manifest.json
stage3_hybrid/results/stress_calibration.json
stage3_hybrid/results/full_oracle_metrics.json
stage3_hybrid/results/bounded_ranker_metrics.json
stage3_hybrid/reports/STAGE3A_EXPERIMENT_REPORT.md
stage3_hybrid/reports/MECHANISM_EXPLANATION.md
stage3_hybrid/reports/CURRENT_STAGE3A_DECISION.json
stage3_hybrid/reports/STAGE3A_TEST_RESULTS.md
stage3_hybrid/SHA256SUMS
```

报告必须区分：

* DONE；
* KEY RESULT；
* WHAT ACTUALLY EXECUTED；
* LIMITATION；
* MECHANISM EXPLANATION；
* GO/NO-GO；
* NEXT。

报告开头必须给出人话结论，并明确：

* full oracle 只是 upper bound；
* bounded-horizon ranker 是否真正有效；
* stress 是否合格；
* correct 是否优于 shuffled/time-shifted；
* 是否允许进入 Stage3B；
* PAI job 数量；
* ACT/π0.5/VLA 是否训练；
* `accepted=false`。

## 12. 最终决策词表

最终只允许输出以下之一：

```text
BLOCKED_RUNTIME
NO_INFORMATIVE_FAILURE_SPACE
MODE_LIBRARY_NO_GO
ORACLE_UPPER_BOUND_GO_SHORT_HORIZON_PENDING
SHORT_HORIZON_SIGNAL_WEAK
HYBRID_ROUTING_SIGNAL_GO
```

不得创造模糊的 positive wording。

## 13. 执行原则

* 先冻结合同，再运行结果；
* 先做 calibration，再冻结 stress；
* calibration 与 held-out 严格分离；
* episode 是统计单位；
* 所有负结果保留；
* 不因 gate 失败而降低阈值；
* gate 失败后可以完成最小机理诊断，但不能启动更大的下游训练；
* 不把代码存在称为实验执行；
* 不把 command change 称为 physical effect；
* 不把 full-future oracle 称为 deployable；
* 不把候选选择上界称为 learned-policy improvement；
* 不覆盖 Stage2 的负结论。
