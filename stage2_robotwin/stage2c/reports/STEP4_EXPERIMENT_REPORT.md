# R22-P19 Step4 / Stage 2C 实验报告

日期：2026-08-14

任务：RoboTwin `handover_block`

证据边界：privileged simulator oracle，`accepted=false`

当前闭环状态：448/448 `COMPLETE`

最终机制判定：`RESPONSIBILITY_MECHANISM_NOT_SUPPORTED`

后续 ACT gate：`BLOCK`

## 实验契约

本阶段验证三个问题：自然 expert 交接中的 responsibility 是否稳定；去掉固定
ridge 后的 effect-nullspace operator 是否真正转移 responsibility；在消除 PhysX
warm-start 污染并校准 stress 后，正确 responsibility 是否优于错误/打乱责任与仅守恒、
仅 release guard 等 controls。

冻结限制如下：

- 不训练 ACT；
- 不训练 deployable responsibility estimator；
- 不使用 pi0.5；
- 不创建 PAI job；
- 不把 simulator oracle 称为可部署；
- episode 是唯一统计推断单位，branch state 不是独立样本；
- 因用户明确要求完成全部实验，下游 stress 和 448-cell closed-loop matrix 在前置
  gate 未通过时仍继续执行，但所有 ineligible / negative lineage 必须保留。

正式 held-out seeds 为 `2,3,5,6,7,8,9,10`。RoboTwin commit 为
`266f3aadf505a4f7fe9af0faa41a20f5f47cd123`，XPolicyLab gitlink 为
`c37109c500be67d0dea6b36bf7337bbd26e763cd`。

## Stage 2C-0：Fresh-Prefix Replay Noise Audit

### DONE

完成 100/100 个独立进程单元：5 seeds × 2 conditions × 2 null methods ×
5 replicas。每个单元均从 episode 起点 reset 和重放同一 expert tape，到 E2 后进入
方法段；oracle branch 使用单独 SAPIEN scene，不再把 branch state restore 回主 scene。

### KEY RESULT

Fresh-prefix 的六项 exact-null floor 全为 0：每项 within-method 有 200 个配对差值，
B0-vs-operator-null 有 50 个配对差值，median/P95/max 均为 0。因此后续 3×P95
effect gate 也为 0，replay substrate 可用于性能比较，operator 结论不暂停。

旧 Stage 2B sequential snapshot replay 的非零 P95 为：

| 指标 | 旧 P95 | fresh-prefix P95 |
| --- | ---: | ---: |
| peak object angular velocity | 1.215343 | 0 |
| peak object linear jerk | 5.766071 | 0 |
| contact-masked slip (m) | 0.001290693 | 0 |
| min object height (m) | 0.000183657 | 0 |

### LIMITATION

零噪声只证明 replay 对完全相同动作可复现，不验证 responsibility 信号或 operator。

### NEXT

用 metric-specific 3×P95 floor 审计 local 与 closed-loop 的真实方法效应。

## Stage 2C-1：Natural Responsibility / Hidden Authority

### DONE

完成 90/90 个 profile 单元：calibration seeds `0,1`，held-out seeds
`2,3,5,6,7,8,9,10`，每 seed 包含 NATURAL 及四个 gamma 下的左右 hidden-authority
配对。配对起点、E2 prefix 和 high-level expert tape 全部逐 seed 一致，hidden profile
在 E2 前不可观察。选中的非极端候选为 `gamma=0.8`。

### KEY RESULT

决策为 `RESPONSIBILITY_UNSTABLE`：

| 指标 | 结果 |
| --- | ---: |
| held-out 预期方向 accuracy | 0.316667，95% CI [0.241667, 0.400000] |
| 反向方向 accuracy | 0.683333，95% CI [0.600000, 0.758333] |
| valid-pair rate | 0.882353 |
| H5/H10/H20 sign consistency | 0.671875 |
| adjacent share delta median / P95 | 0.062234 / 0.941307 |
| left-right swapped accuracy | 0.683333 |
| episode shuffle accuracy | 0.384042 |
| temporal circular shift accuracy | 0.441176 |

简单 baselines 的 hidden-authority accuracy 为：action magnitude 0.033333、contact
impulse 0.483333、inverse distance 0.483333、phase 0、fixed 50/50 0。责任 mismatch
虽被统计为 risk-predictive，但相关方向很弱且不一致：angular velocity 0.102806、jerk
-0.188305、slip -0.184652、release-contact risk 0。

### LIMITATION

SoftExpertAuthorityProfile 不是“把一只手按 gamma 纯衰减”。代码实际在
`e_parallel` 上插值 expert target 与 object-follower target；直接 command audit 中，
绝对平行动作真正变小的比例仅 0.617647，follower 绝对幅值大于 expert 的比例为
0.485294，符号保持率 0.941176。因此 profile 的反向结果来自 follower 几何与 expert
命令的相对关系，不能解释成标签写反，也不能当成自然 responsibility 的正证据。

### NEXT

仅把此信号作为 privileged diagnostic，必须依赖 local causal transfer 和 closed-loop
wrong-responsibility controls 才能判断机制。

## Stage 2C-2：Eta Calibration 与 Local Operator Gate

### DONE

先在 calibration seeds `0,1` 的 clean/hidden profiles 上比较
`eta=0.25/0.5/0.75/1.0`，4/4 单元完成；所有候选满足数值可行条件。按预注册规则
“在 correction 5%–20% 的候选中选择最接近 12.5%，相同时取较小 eta”冻结
`eta=0.25`。随后在 5 个 held-out seeds × clean/hidden profiles 上完成 10/10
local-gate 单元，共分析 1,800 条 method-state-horizon rows。

### KEY RESULT

决策为 `RESPONSIBILITY_NOT_CAUSAL`：

| Gate 指标 | 结果 | Pass |
| --- | ---: | --- |
| median correction ratio | 0.173306 | yes |
| active states >5% correction | 0.85 | yes |
| predicted effect error P95 | 约 2.6e-16 | yes |
| realized total-effect deviation | <0.1% 量级 | yes |
| correct target movement median | 0 | no（要求 >=0.15） |
| swapped target movement median | 0 | no（未反向） |
| conservation-only specificity | 未通过 | no |
| contact / support height | 未明显下降 | yes |

正确算子的 200 个主审计 rows 中，solver status 为：54 次
`NULLSPACE_APPLIED`、126 次 `NULLSPACE_CLIPPED`、20 次
`DEGENERATE_GAIN_BASE_FALLBACK`；安全约束记录 126 次 relative-trust clipping 和
20 次 degenerate-gain fallback。angular delta 中位数为 0.000738，slip delta 中位数为
4.668e-7，确实超过 exact-zero null floor，但没有把 realized contribution 朝正确责任
目标移动。

### LIMITATION

新算子已经摆脱 near-null：它沿 `[b_R,-b_L]` 移动并用 relative trust region 限幅，
而不是用绝对 ridge 压回 base；然而“动作改得动、总 effect 守恒”不等于“正确责任导致
正确贡献转移”。由于 1D 没有通过 responsibility transfer，计划中的 conditional 4D
physics gate 未触发；4D 实现与单测保留，但没有把未触发的代码存在称为实验结果。

### NEXT

按用户的显式 override 继续完整 stress 与 closed-loop falsification；结论必须保留此前
negative gate。

## Stage 2C-3：Stress Calibration

### DONE

完成 96/96 个 calibration 单元：24 个候选（含 clean）、23 个非 clean 候选，
calibration seeds `0,1`，C0/C13 两方法。所有预注册单因素候选及少量两因素候选均被
实际执行。`donor_release_advance_steps` 按 250 Hz tape/physics step 计，每步 4 ms。

### KEY RESULT

决策为 `DIAGNOSTIC_STRESSES_FROZEN_WITH_ELIGIBILITY_FAILURE`。没有候选满足
“Base success 30%–80%”或“disturbance >=2× clean 且可改善”的正式资格；为完成用户
要求的下游矩阵，冻结三项 diagnostic fallback，且显式标为 ineligible：

| Stress | 冻结值 | Base success | max disturbance / clean | improvable | eligible |
| --- | --- | ---: | ---: | --- | --- |
| S1 hidden mismatch | gamma=0.8 | 1.0 | 1.551777 | no | no |
| S2 premature release | advance 10 steps = 40 ms | 1.0 | 1.422416 | yes | no |
| S3 contact quality | receiver friction ×0.5 | 1.0 | 1.530215 | yes | no |

### LIMITATION

三项 stress 都没有打开预注册的任务失败空间，后续 closed-loop 只能作为诊断矩阵，
不能冒充在 qualified stress 上的正/负性能证明。

### NEXT

保持冻结值不变，在 8 个 held-out episodes 上执行 14-method fresh-prefix 矩阵。

## Stage 2C-4：Fresh-Prefix Closed-Loop Matrix

### DONE

完成 448/448 个正式单元：8 held-out seeds × 4 conditions × 14 methods。每个单元
均为独立新进程，先从 episode 起点重放同一 tape，再在 E2 后进入方法差异。完整性审计为：

- 448 个唯一 `result.json`，missing=0，extra=0，非有限数=0；
- 32 个 seed × condition 组的全部方法 prefix hash 一致；
- 32 个 oracle budget 组全部相等，C0 的 oracle budget 为 0；
- 416 个含 oracle 的单元全部使用独立 sandbox scene；其余 32 个是无 oracle 的 C0；
- C0 与 C11 在所有报告指标上逐 episode 精确相等；
- 448 个 trace NPZ 均存在于 CPFS 正式运行目录，但不提交 Git；
- 4 个四 worker contention 期间留下的 `BrokenPipeError` 失败产物全部保留并通过
  fresh-process 重跑恢复，recovered=4，unrecovered=0。

14 个方法为 C0 base；C1 phase；C2 distance；C3 force/impulse；C4 conservation-only；
C5 direct responsibility scaling without conservation；C6 instantaneous responsibility；
C7 stateful responsibility；C8 left-right swapped；C9 episode shuffled；C10 time shifted；
C11 operator-null；C12 release guard only；C13 full signed + joint + stateful + conservation + guard。

### KEY RESULT

最终决策为 `RESPONSIBILITY_MECHANISM_NOT_SUPPORTED`，`accepted=false`。所有方法、
所有 condition 的 task success 与 handover completion 都是 1.0，drop、premature release、
receiver takeover failure 都是 0；因此三项 diagnostic stress 仍处于成功率 ceiling，不能
用 success 判断方法优劣。

下表给出 C0/C13 的 episode mean。angular、jerk、slip 均为越低越好；括号中的
`C13>C0` 是预注册的多指标 episode-level 判定，而非某个单指标是否下降。

| condition | C0/C13 success | angular C0 → C13 | jerk C0 → C13 | slip C0 → C13 | C13>C0 |
| --- | ---: | ---: | ---: | ---: | --- |
| clean | 1/1 | 2.411924 → 2.524117 | 169.987089 → 169.766140 | 0.0878581 → 0.0878243 | no |
| S1 hidden mismatch | 1/1 | 2.536190 → 3.226541 | 168.609793 → 185.061146 | 0.0879483 → 0.0915880 | no |
| S2 premature release | 1/1 | 2.389782 → 2.110734 | 170.778034 → 171.042795 | 0.0878432 → 0.0880065 | no |
| S3 contact quality | 1/1 | 2.713045 → 2.717314 | 167.450535 → 167.516844 | 0.0882122 → 0.0884087 | no |

paired bootstrap 中“benefit > 0”表示方法改善：

- clean：C13 的 slip benefit 为 +3.3737e-5，95% CI
  [5.7067e-6, 6.6851e-5]，但 angular benefit 为 -0.112193，jerk CI 跨 0，未形成
  多指标改善；
- S1：angular/jerk/slip mean benefit 分别为 -0.690351/-16.451353/-0.003640，
  三项方向都不利；
- S2：angular benefit +0.279047，95% CI [0.068100, 0.557954]，但 jerk benefit
  -0.264761，95% CI [-0.584538, -0.031000]，是明确 trade-off；slip 未改善；
- S3：angular/jerk/slip benefit 为 -0.004269/-0.066309/-0.000196，三项 CI 均未形成
  合格改善。

关键 mechanism controls 全部为 negative：

| 判据 | clean | S1 | S2 | S3 | 正式 stress 计数 |
| --- | --- | --- | --- | --- | ---: |
| C6 correct > C8 swapped | no | no | no | no | 0/3 |
| C6 correct > C9 shuffled | no | no | no | no | 0/3 |
| C7 stateful > C10 time-shifted | no | no | no | no | 0/3 |
| C13 full > C4 conservation-only | no | no | no | no | 0/3 |
| C13 > C0 | no | no | no | no | 0/3 |

effect 超过 exact-zero null floor 的 stress 只有 1/3，要求为至少 2/3。clean success
degradation=0 pp，矩阵完整、fresh-null substrate 与 oracle-budget gate 通过；natural
signal、local causal transfer、wrong-responsibility specificity、full-vs-conservation 和
stress improvement 均未通过。

C13 共记录 1,532 次 operator refresh：941 次
`DEGENERATE_GAIN_BASE_FALLBACK`、75 次 contact-retention + degenerate fallback、
186 次 `NULLSPACE_APPLIED`、330 次 `NULLSPACE_CLIPPED`。全矩阵 episode-median correction
的中位数为 0，但 >5% correction 的平均 active rate 为 0.312573；release guard 在
13,440 个 donor-open request steps 中阻断 698 次。C5 则有 0.881341 的全矩阵
episode-median correction，证明其确实强改动作，但它不守恒总 task effect。

计算成本为 159,328 个 oracle branches、796,640 个模拟 oracle physics steps；448 个
单元累计 replay wall time 34,913.07 s、estimator time 517.00 s、solver time 239.53 s。
所有详细 per-seed、paired bootstrap CI、null-normalized audit、operator status 和 cost
均保存在 `results/CLOSED_LOOP_DECISION.json`。

### LIMITATION

三项 stress 都未达到预注册 eligibility，且 8 个 episode 的 task success 全部封顶；因此
本矩阵是 privileged-oracle diagnostic falsification，而不是合格 failure-space 上的性能
benchmark。episode 才是推断单位，不能把 1,532 个 refresh 或 branch points 当作独立 n。
本结果只覆盖 RoboTwin `handover_block`，不支持 deployability、ACT compatibility、其他任务
或真实机器人结论。

### NEXT

根据 follow-up contract，ACT、deployable responsibility estimator、Diffusion Policy、
pi0.5/TwinVLA 与额外 RoboTwin tasks 全部保持 `BLOCK`。后续若继续，应先修改原假设或获得
新的、预注册的验证计划；本报告不生成新 idea，也不把单指标下降解释为机制成立。

## 代码机理反解（不生成新 idea）

### Replay floor 为什么从非零变成精确零

Stage 2B 把显式 rigid/articulation state restore 到同一个长期 scene，但 SAPIEN 不暴露
PhysX warm-start cache，oracle branch 因而会改变主 scene 隐含 solver history。Stage 2C
让 oracle 在第二个 SAPIEN scene 中运行，只把主 scene 的显式状态单向复制进 sandbox，
不把任何 state restore 回主 scene；因此完全相同动作不会再受到 oracle branch 污染。

### 旧 ridge 为什么 near-null，新算子为什么 effectful 但不 causal

旧算子用固定 `ridge_lambda=0.05` 约束动作偏离，而 contribution residual 的尺度由很小的
物理 gain 决定，绝对正则项支配目标，解自然贴近 base。新算子直接使用 gain 的精确零空间
`n=[b_R,-b_L]`，再用相对 trust region 与 action/contact/support/effect constraints 限幅，
因此产生 17% 量级修正并保持总 effect。然而 local branch 中 correct、swapped 和
conservation-only 的 realized responsibility movement 无区分，说明局部 gain × parallel
action 的 1D contribution proxy 没有提供可被该动作方向因果控制的 responsibility 目标。

### Closed-loop 提升或下降应该如何归因

- C5 直接执行 `base_action * responsibility`，不补偿总 task effect；它带来的 success、
  jerk 或 slip 变化属于总命令幅值变化，不能证明 responsibility-preserving transfer。
- C4 用固定 50/50 target 走同一个守恒 operator，是 generic conservation/smoothing control；
  C13 若不胜 C4，增益可由守恒本身解释。
- C8/C9/C10 分别是 swapped、episode-shuffled、time-shifted responsibility；正确 C6/C7
  必须胜过这些 controls，才能把差异归因到责任方向或时间结构。
- C12 只启用 release guard；C13 的 donor-release 变化必须对照 C12，不能把 guard 效应
  归入 signed/stateful routing。
- C13 在 contact loss、support-height 下降或 gain product 退化时回退 base，在修正过大时
  被 relative trust region 裁剪；最终报告必须同时给出 applied/clipped/fallback 与 guard
  counts，不能只看汇总 task 指标。

实际矩阵把这些替代解释区分开了。C5 在 S3 显著降低 angular（benefit +0.384440，
95% CI [0.048332, 0.767212]），却显著恶化 jerk 与 slip；其 correction 中位数高达
0.881341，所以这是降低总命令/改变 task effect 的幅值 trade-off，不是责任守恒转移。
C12 在 S1 单独改善 jerk（benefit +4.069510，95% CI [0.001438, 12.166032]），同时 angular
和 slip 方向不利，说明 release guard 本身足以改变轨迹稳定性。C13 在 S2 改善 angular
但恶化 jerk，且 correct、swapped、shuffled、time-shifted controls 均无 specificity；因此
该变化更符合守恒修正、fallback/clipping 与 guard 对轨迹的共同扰动，而非正确责任方向的
因果收益。

## 最终结论

Stage 2C 已按用户 override 完成全部 A/B/C/stress/448-cell 实验，但三个必要链条同时失败：

1. natural/hidden-authority responsibility 为 `RESPONSIBILITY_UNSTABLE`；
2. 1D operator 数值 effectful 且守恒，却为 `RESPONSIBILITY_NOT_CAUSAL`；
3. closed loop 中 correct responsibility 与 wrong/shuffled controls 无区分，full 也不胜
   conservation-only，三项 stress 改善为 0/3。

因此最终机制码是 `RESPONSIBILITY_MECHANISM_NOT_SUPPORTED`，`accepted=false`，ACT gate
为 `BLOCK`，PAI jobs=0。这里的结论是“当前实现与当前任务证据不支持责任路由机制”，
不是证明所有责任建模永远无效；也不把 simulator oracle 称为 deployable。
