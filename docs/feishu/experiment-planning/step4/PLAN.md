---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/Jk1UwYrvyiQVphkxxuacHd1Cn5d
wiki_node_token: Jk1UwYrvyiQVphkxxuacHd1Cn5d
document_token: ZRY6dVxhfogbVJxov4EcxxaonLc
revision_id: 10
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: b1d629c2b1f8ce3bcf65f6316f54fd73d0120b3bd5855f53cbcde581ff1d7693
---

<title>step4</title>

继续项目：

[https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering)

## 任务名称：

# R22-P19 Stage 2C —

Natural Responsibility Continuity,

Effectful Oracle Transfer,

and Noise-Calibrated Closed-Loop Validation

最高目标：

修复 Stage 2B 的三个核心问题，并重新检验原始 idea：

## 1. Stage 2B-I 的正信号来自人为 one-driver / follower profile，

尚未证明自然 expert 双臂交接中的 responsibility 可用；

## 2. Stage 2B-II 的固定 ridge_lambda=0.05

使 responsibility operator 几乎不修改动作，

因此 operator 没有接受有效检验；

## 3. snapshot restore 未恢复 PhysX warm-start cache，

B0/B9 完全相同动作仍存在明显差异，

且 stress 条件全部成功，缺少失败空间。

本阶段仍使用：

- RoboTwin handover_block
- expert low-level tape
- simulator oracle responsibility

### 禁止：

- 训练 ACT
- 训练 responsibility estimator
- 使用 π0.5
- 创建 PAI job
- 将 simulator oracle 称为 deployable
- 把单个局部指标变化称为 idea 成功

accepted=false。

## 0. 冻结与目录

读取并保留现有 Stage 2 / Stage 2B 全部结果与失败 lineage。

建立 branch：

stage2c-natural-effectful-transfer-v1

### 新增：

stage2_robotwin/stage2c/

configs/

replay/

intervention/

responsibility/

operator/

baselines/

scripts/

tests/

results/

reports/

### 只做必要 provenance：

- repo commit
- RoboTwin commit
- runtime versions
- config hash
- seeds
- artifact checks

不要扩建大型形式化审计系统。

## 1. Stage 2C-0：Fresh-Prefix Replay Noise Audit

目标：

消除或量化 snapshot restore 未恢复 PhysX warm-start cache 的问题。

不得继续让多个方法从同一个长期复用的 task 实例中顺序 restore。

每个：

seed × condition × method × replicate

必须：

## 1. 启动独立新进程；

## 2. reset 同一 RoboTwin seed；

## 3. 使用同一 expert tape 从 episode 开始重放；

## 4. 自然建立 PhysX solver history；

## 5. 到 E2 后才进入方法差异；

## 6. 运行完成后销毁进程。

先只运行 exact-null：

- 5 seeds
- clean + 1 stress
- 每个 seed/condition 运行 5 个完全相同的 B0 replicas
- 再运行 5 个 operator-null replicas

计算每项指标的 null replay floor：

- median absolute pair difference
- P95 absolute pair difference
- max difference

### 比较：

- old snapshot replay floor
- fresh-prefix replay floor

### 要求：

- 后续方法效果必须超过对应 P95 null floor 的 3 倍；
- 若 fresh-prefix 仍存在大噪声，暂停 operator 性能结论，

继续修复 replay substrate；

- 不允许仅靠 method-order rotation 代替 noise audit。

### 输出：

reports/REPLAY_NOISE_REPORT.md

reports/REPLAY_NOISE_DECISION.json

## 2. Stage 2C-1：Natural-Action Hidden Authority Profiles

Stage 2B-I 的 one-driver/follower profile 保留为 instrumentation sanity check，

但不再作为自然责任的主证据。

实现 SoftExpertAuthorityProfile。

左右臂都继续执行原始 expert command。

对 soft arm，只在 e_parallel 上混合：

x_soft_parallel =

gamma \* x_expert_parallel

\+ (1-gamma) \* x_object_follower_parallel

### 候选：

gamma = 0.8 / 0.6 / 0.4 / 0.2

其他方向：

- e_perp：expert target
- e_vertical：expert target
- rotation：expert target
- gripper：expert command

### 构造：

LEFT_HIDDEN_AUTHORITY：

- 左 full expert
- 右 soft expert

RIGHT_HIDDEN_AUTHORITY：

- 右 full expert
- 左 soft expert

NATURAL：

- 左右均 full expert

### 要求：

- paired profile 起点 object/TCP/contact/phase 完全相同；
- high-level expert action 完全相同；
- 只有低层 hidden authority 不同；
- force/distance/phase 在 profile assignment 前不可观察差异。

Calibration seeds：

0, 1

Held-out seeds：

2, 3, 5, 6, 7, 8, 9, 10

若某 seed expert 失败，保留失败并使用下一个预先排序 seed补足，

不得按结果挑选。

Signal window：

E4-250 到 min(E5,E4+150)

stride 25

H=5/10/20

分别报告：

A. Hidden-authority responsibility accuracy

B. NATURAL responsibility phase curve

C. H5/H10/H20 sign consistency

D. adjacent refresh stability

E. responsibility mismatch 对 jerk/slip/release risk 的预测能力

F. force/distance/phase/action-magnitude baselines

G. left-right swap

H. episode shuffle

I. temporal circular shift

不得将 invalid authority pair 计入 accuracy，

但必须报告全部 pair 的 valid rate。

### 输出：

reports/NATURAL_RESPONSIBILITY_REPORT.md

reports/NATURAL_RESPONSIBILITY_DECISION.json

### Decision：

NATURAL_RESPONSIBILITY_SUPPORTED

HIDDEN_AUTHORITY_ONLY

RESPONSIBILITY_UNSTABLE

SIGNAL_NOT_SUPPORTED

## 3. Stage 2C-2：Effect-Nullspace Transfer

弃用固定 ridge_lambda=0.05 的主算子。

旧算子保留为 baseline，不删除。

第一版实现：

EffectNullspaceTransfer1D

局部效果：

d0 = b_L \* a_L_base + b_R \* a_R_base

零空间方向：

n = [b_R, -b_L]

候选动作：

a_new = a_base + eta \* alpha_star \* n

其中 alpha_star 使左右贡献朝 responsibility target 移动，

同时总效果在局部模型中保持不变。

eta candidates：

0.25 / 0.5 / 0.75 / 1.0

### 使用：

- relative trust region
- action bounds
- contact retention
- support-height constraint
- effect error constraint

不要用一个绝对 ridge 数值再次压死算子。

### 保存：

- base contribution
- target contribution
- routed contribution
- predicted total effect
- realized total effect
- action correction ratio
- nullspace residual
- safety clipping

## 4. Signed / Joint / Stateful Responsibility

不要再直接执行：

max(rho, 0)

显式保存：

- productive_left
- productive_right
- harmful_left
- harmful_right
- rho_joint

### 模式：

LEFT_DOMINANT

RIGHT_DOMINANT

JOINT_SUPPORT

CONFLICT

CONFLICT：

削弱 harmful arm 的反向 task-effect component，

由另一只手补偿总效果。

JOINT_SUPPORT：

保留 common/shared component，

只修改 differential/conflicting component；

不得简单返回 0.5/0.5 并完整 bypass。

增加 stateful responsibility：

rho_control_t =

Project(

(1-beta) \* rho_control_t-1

\+ beta \* rho_oracle_t

)

并限制最大责任变化率。

### 比较：

- instantaneous responsibility
- stateful responsibility
- phase-only smooth blending

## 5. Stage 2C-2 Local Operator Gate

不要先跑完整 closed loop。

从至少：

- 5 seeds
- 每个 seed 8–12 个 E4-relative branch states
- clean + hidden-authority profile

运行短时 H=10/20 local rollouts：

L0 Base

L1 Old ridge operator

L2 Conservation only

L3 Direct scale no conservation

L4 Correct nullspace responsibility

L5 Left-right swapped responsibility

L6 Episode-shuffled responsibility

L7 Time-shifted responsibility

L8 Stateful nullspace responsibility

### 进入完整 closed loop 前必须满足：

## 1. median action correction / median base action

在 5%–20% 区间；

## 2. 至少 30% active states 的 correction

超过 5% base action；

## 3. realized intervention effect

超过 fresh-prefix null P95 floor 的 3 倍；

## 4. predicted total-effect error <5%；

## 5. realized total-effect deviation from base <10%；

## 6. correct responsibility 使 realized contribution

朝目标责任移动至少 0.15；

## 7. left-right swap 使移动方向反转；

## 8. conservation only 不产生相同 responsibility shift；

## 9. contact retention / object height 不明显下降。

如果 1D operator 能转移 responsibility，

但无法影响 angular/slip metrics，

再实现 4D task-effect operator：

[

parallel translation,

lateral translation,

vertical support,

yaw rotation

]

不要直接上完整 14D joint QP。

### 输出：

reports/LOCAL_OPERATOR_GATE_REPORT.md

reports/LOCAL_OPERATOR_GATE_DECISION.json

### Decision：

EFFECTFUL_OPERATOR_READY

ONE_DIMENSION_INSUFFICIENT_EXTEND_4D

OPERATOR_STILL_NEAR_NULL

OPERATOR_UNSAFE

RESPONSIBILITY_NOT_CAUSAL

## 6. Stage 2C-3：Stress Calibration

只有 Local Operator Gate 通过后继续。

在 calibration seeds 上搜索：

receiver_gain:

0.7 / 0.55 / 0.4

receiver_delay_steps:

4 / 8 / 12

receiver_friction:

0.7 / 0.5 / 0.3

donor_release_advance:

10 / 20 / 30 physics/control steps，

按实际 command 语义记录单位

receiver_grasp_offset:

5 / 10 / 15 mm

object_COM_shift:

10 / 20 / 30 mm

hidden_authority_mismatch:

soft gamma 0.8 / 0.6 / 0.4

可测试少量两因素组合，但不进行大规模网格搜索。

冻结三类 stress：

S1 Hidden authority mismatch

S2 Premature release risk

S3 Contact quality degradation

要求每项满足至少一个：

- Base success 30%–80%

或

- Base disturbance ≥2× clean

且存在可改善空间。

不得再次使用全部 100% success 的弱 stress 进入正式矩阵。

### 输出：

reports/STRESS_CALIBRATION_REPORT.md

configs/frozen_stage2c_stress.yaml

## 7. Stage 2C-4：Fresh-Prefix Closed-Loop Matrix

Held-out seeds：

至少 8，优先 10。

每个方法都在独立新进程中：

reset → replay prefix → method execution。

Methods：

C0 Base expert

C1 Linear phase blending

C2 Distance routing

C3 Force/impulse routing

C4 Conservation only

C5 Direct responsibility scaling, no conservation

C6 Instantaneous responsibility + nullspace transfer

C7 Stateful responsibility + nullspace transfer

C8 Left-right swapped responsibility

C9 Episode-shuffled responsibility

C10 Time-shifted responsibility

C11 Operator-null

C12 Release guard only

C13 Full signed + joint + stateful + conservation + guard

### 所有方法使用：

- same seed
- same expert tape
- same stress
- same prefix history
- same control rate
- same oracle refresh budget
- same simulator branch budget where applicable

## 8. Metrics

Task：

- success
- handover completion
- drop
- premature release
- receiver takeover failure

Stability：

- peak angular velocity
- peak linear jerk
- contact-masked slip
- pose deviation
- min height
- donor residual influence

Mechanism：

- natural responsibility horizon consistency
- hidden-authority swap accuracy
- action correction ratio
- predicted effect conservation
- realized effect conservation
- responsibility-target realization
- harmful contribution suppression
- joint-mode occupancy
- responsibility total variation
- routing outside E2-E5
- method effect / null replay floor

Cost：

- oracle branch count
- simulated physics steps
- solver time
- total replay time

Statistics：

- episode is the only inference unit
- paired bootstrap 95% CI
- report each seed
- report null-floor normalized effect size
- branch points are not independent n

## 9. Mechanism Criteria

### ORACLE_OPERATOR_SUPPORTED：

- Natural responsibility is stable or hidden-authority-valid;
- operator is not near-null;
- correct responsibility beats swapped and shuffled;
- full beats conservation only;
- at least two stress conditions improve;
- clean degradation ≤3 percentage points;
- effect exceeds null floor.

### SIGNAL_VALID_OPERATOR_WEAK：

- responsibility useful;
- operator effectful but no stable benefit.

### HIDDEN_AUTHORITY_ONLY：

- hidden profiles work;
- natural expert responsibility does not.

### CONSERVATION_ONLY_EXPLAINS_GAIN：

- full does not beat conservation only.

### RESPONSIBILITY_MECHANISM_NOT_SUPPORTED：

- shuffled/wrong responsibility matches correct responsibility.

accepted remains false in every Stage 2C outcome.

## 10. Follow-up Gate

Only after ORACLE_OPERATOR_SUPPORTED:

## 1. train ACT baseline;

## 2. test ACT + oracle responsibility;

## 3. train deployable responsibility estimator;

## 4. add Diffusion Policy;

## 5. later test pi0.5/TwinVLA.

Do not start ACT merely because Stage 2B-I signal was positive.

## 11. Additional Control Tasks

Only after handover_block Oracle Operator is supported:

- lift_pot:

joint responsibility should remain high;

method must not force single-arm transfer.

- pick_dual_bottles:

shared-object router should remain off.

- handover_mic:

geometry generalization.

These are not prerequisites for the initial Stage 2C operator gate.

## 12. Deliverables

stage2_robotwin/stage2c/

configs/

replay/

fresh_prefix_runner.py

null_floor.py

intervention/

soft_expert_authority.py

responsibility/

natural_responsibility.py

signed_joint_state.py

temporal_filter.py

operator/

effect_nullspace_transfer_1d.py

effect_nullspace_transfer_4d.py

conflict_mode.py

joint_shared_differential.py

baselines/

scripts/

run_replay_noise_audit.py

run_natural_responsibility.py

run_local_operator_gate.py

calibrate_stress.py

run_closed_loop_matrix.py

analyze_stage2c.py

tests/

results/

reports/

REPLAY_NOISE_REPORT.md

NATURAL_RESPONSIBILITY_REPORT.md

LOCAL_OPERATOR_GATE_REPORT.md

STRESS_CALIBRATION_REPORT.md

CLOSED_LOOP_REPORT.md

CURRENT_STAGE2C_DECISION.json

## 13. 第一项立即执行

### 优先顺序：

A. Fresh-prefix null replay audit

B. Natural-action hidden authority profiles

C. 1D nullspace local operator gate

D. 只有 A/B/C 都可解释后，才做 stress calibration 和 closed loop

### 每个子阶段只汇报：

DONE

KEY RESULT

LIMITATION

NEXT

不要在前置 gate 未完成时启动完整矩阵。

不要扩建不必要的审计基础设施。

保留所有失败 lineage。
