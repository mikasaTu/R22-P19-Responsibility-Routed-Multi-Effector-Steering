---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/Rfy7wq6Tsi3pppkvqxFcjvPRnmf
wiki_node_token: Rfy7wq6Tsi3pppkvqxFcjvPRnmf
document_token: RT2rdhZESoWN7jx6XiVcg8qon8g
revision_id: 7
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: b4393dadfd0da2f85fecd8e775ebd92d3ce180b6f34e7715b65c649412e786a8
---

<title>step3</title>

继续验证项目：

[https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering)

任务名称：

R22-P19 Stage 2B —  
Multi-Seed Contact-Aware Responsibility Replication  
and Oracle Closed-Loop Steering

最高目标：

验证原始 R22-P19 的完整因果链：

1. 在真正双臂交接中，counterfactual causal responsibility  
是否能在多个 episode 中稳定识别实际物体控制权；
2. 使用 simulator oracle responsibility 进行  
responsibility-conserving command transfer 后，  
是否能降低交接扰动、滑移、提前释放和掉落，  
同时保持基础 expert 原本想产生的物体运动效果。

这不是 ACT、π0.5 或 learned-estimator 阶段。  
优先隔离 signal 与 operator 本身。

# ==================================================  
0. 当前冻结事实

开始前读取并核验仓库最新 main。

当前已知结果：

- RoboTwin handover_block 真双臂 smoke 已完成；
- 10 条成功 expert episode 的 E0–E6、视频和 snapshot replay 已通过；
- 普通 direction/null 在 92 个 paired state-horizon 中产生 0 个  
intervention-valid authority swap；
- 强 diagnostic：  
non-dominant compliance scale = 0.05，  
在一个 episode 的窄 release 窗口中产生 21 个 valid pairs；
- 对这 21 个 valid pairs，oracle direction 为 21/21；
- 该结果仅来自 1 个 episode，不能视为正式 signal；
- operator_status=NOT_TESTED；
- ACT_STATUS=NOT_STARTED；
- accepted=false。

不要删除或改写已有 evidence。

建立新 branch：

stage2b-contact-aware-oracle-operator-v1

新增目录：

stage2_robotwin/stage2b/  
configs/  
intervention/  
operator/  
baselines/  
scripts/  
tests/  
results/  
reports/

==================================================

1. 科学目标分解  
==================================================

Stage 2B-I：  
多 seed、接触感知 authority intervention，  
验证 responsibility signal 是否可重复。

Stage 2B-II：  
Expert controller + simulator oracle responsibility，  
验证 responsibility-conserving operator 是否改善闭环。

不要先训练 ACT。  
不要先训练责任网络。  
不要创建 PAI job。  
不要使用 π0.5 或大型 world model。

# ==================================================  
2. Stage 2B-I：Contact-Aware Authority Intervention

当前普通 direction/null 无效的原因是：

另一只刚性抓持的手限制物体，  
导致正确的 TCP task-direction command  
不能转化为 object-driving command。

实现 ContactAwareAuthorityProbe。

建立 object task frame：

- e_parallel：  
handover/transport task direction；
- e_vertical：  
gravity/support direction；
- e_perp：  
horizontal orthogonal direction；
- rotation axes。

设计 matched profiles：

LEFT_AUTHORITY：

- 左手在 e_parallel 上执行 task-direction drive；
- 右手在 e_parallel 上进入 compliant follower；
- 右手在 vertical/perp/rotation 方向保持 nominal support；
- 两个 gripper 都保持闭合。

RIGHT_AUTHORITY：

- 完全镜像。

优先实现 anisotropic compliance：

K_parallel = gamma \* K_nominal  
K_vertical = K_perp = K_rotation = K_nominal

gamma candidates：

0.6  
0.4  
0.2

保留 0.05 作为 diagnostic positive control，  
不能作为唯一主结果。

若控制器不支持 anisotropic stiffness：

实现 follower target：

- 非主导手在 e_parallel 上跟随物体或主导手；
- 其他轴保持 snapshot 目标；
- 保持 gripper closure；
- 不通过 open gripper 人为制造 authority。

# ==================================================  
3. Calibration / Evaluation 分离

使用两个成功 expert episode 作为 calibration seeds：

只用于选择：

- gamma；
- task direction；
- motion-effect threshold；
- pair-validity threshold；
- synergy threshold。

冻结配置后，至少使用 5 个 held-out success episodes，  
不得继续调参数。

正式采样窗口使用相对事件：

start = E4 - 250 physics steps  
end = min(E5, E4 + 150 physics steps)  
stride = 25 physics steps

Counterfactual horizons：

H = 5  
H = 10

每个 state/profile/horizon 运行：

LR  
L  
R  
ZERO

neutral action 继续使用：

- measured qpos hold；
- zero target velocity；
- preserve gripper closure；
- unchanged low-level mode。

# ==================================================  
4. Intervention Validity

一个 LEFT/RIGHT profile pair 只有在以下条件都满足时才有效：

LEFT_AUTHORITY profile：

- left singleton 在 task direction 上产生正向 object motion；
- left effect 明显大于 right effect。

RIGHT_AUTHORITY profile：

- right singleton 在 task direction 上产生正向 object motion；
- right effect 明显大于 left effect。

阈值必须由 calibration seeds 冻结。

无效 pair：

- 只作为 intervention failure；
- 不计入 oracle accuracy；
- 不得记为 oracle 错误；
- 必须报告 valid-pair rate。

# ==================================================  
5. Responsibility Representation

保留现有：

e_L = y_L - y_ZERO  
e_R = y_R - y_ZERO  
e_joint = y_LR - y_L - y_R + y_ZERO

分别计算：

- motion responsibility
- support responsibility
- progress responsibility
- harmful/opposing contribution
- joint synergy

主表示使用：

rho_L  
rho_R

rho_joint

不要强制 rho_L + rho_R = 1。  
不要把 rho_joint 平分给左右手。

输出四种状态：

LEFT_DOMINANT  
JOINT_SUPPORT  
RIGHT_DOMINANT  
CONFLICT

CONFLICT：  
某只手对 task direction 产生明显负贡献。

# ==================================================  
6. Stage 2B-I 结果

至少报告：

- per-episode valid-pair rate
- per-episode oracle orientation accuracy
- episode-level responsibility margin
- gamma sensitivity
- E4-relative responsibility curve
- rho_joint distribution
- harmful contribution distribution
- force/distance/phase baselines
- shuffled orientation control

统计单位是 episode。  
不得把同一 episode 的多个 branch point 当独立样本。

使用 episode-level paired bootstrap 95% CI。

输出：

results/signal_replication/  
reports/SIGNAL_REPLICATION_REPORT.md  
reports/SIGNAL_REPLICATION_DECISION.json

Decision 允许：

MULTISEED_SIGNAL_SUPPORTED  
MULTISEED_SIGNAL_PARTIAL  
ONLY_EXTREME_INTERVENTION_SUPPORTED  
THREE_WAY_RESPONSIBILITY_REQUIRED  
SIGNAL_NOT_REPLICATED

无论结果怎样，都保留全部 raw traces。

# ==================================================  
7. Stage 2B-II：Oracle Closed-Loop Operator

完成多 seed signal replication 后，  
直接实现 oracle operator。  
不需要等待 ACT。

第一版只修改 object task direction，  
不直接实现完整 14D QP。

实现：

OneDimensionalEffectConservingTransfer

从当前 expert base action 中提取：

a_L_base  
a_R_base

通过 simulator central finite differences，  
在双接触保持条件下估计：

b_L = d(object task-direction effect) / d(a_L)  
b_R = d(object task-direction effect) / d(a_R)

基础 expert effect：

d_base = b_L \* a_L_base + b_R \* a_R_base

求新动作：

minimize

|b_L \* a_L_new - rho_L \* d_base|²

- |b_R \* a_R_new - rho_R \* d_base|²
- lambda \* ||a_new - a_base||²

subject to：

|b_L \* a_L_new + b_R \* a_R_new - d_base| <= epsilon_effect  
action bounds  
velocity bounds  
trust region around base action  
both grippers remain closed unless release guard permits  
no collision / no support violation

第一版只替换 e_parallel 分量。  
其他平移、旋转、gripper 动作保持 base expert。

# ==================================================  
8. Joint Mode

当 rho_joint > frozen threshold：

不要强制左右责任单向转移。

进入 JOINT_SUPPORT：

- 保留 base expert 的共同支撑分量；
- 保持 total object effect；
- 只消除产生反方向 task effect 的分量；
- 不把物体强制交给某一只手。

实现 two-way 和 three-way 两个版本，  
用于机制消融。

# ==================================================  
9. Release Guard

实现 ResponsibilityReleaseGuard。

donor open 只有在以下条件满足时允许：

- receiver stable contact；
- receiver support responsibility 超过阈值；
- receiver contact retention 高；
- slip/drop risk 未升高。

分别评测：

CONTINUOUS_ONLY  
RELEASE_GUARD_ONLY  
FULL_CONTINUOUS_PLUS_RELEASE

不能把 release-guard 收益冒充 continuous responsibility transfer 收益。

# ==================================================  
10. 闭环对象

第一版继续使用 RoboTwin expert controller。

在 E2–E5 overlap 阶段插入 operator。  
其他阶段保持 exact base expert。

每次 operator 修改必须保存：

- base action
- routed action
- rho_L/rho_R/rho_joint
- selected mode
- b_L/b_R
- desired effect
- realized effect
- effect-conservation error
- QP/solver status
- trust-region clipping
- release-guard decision

# ==================================================  
11. 闭环 Baselines

B0 Base expert

B1 Linear E3–E5 phase blending

B2 Distance-based routing

B3 Contact-force-based routing

B4 Oracle responsibility direct scaling  
不保持 total object effect

B5 Effect conservation only  
不使用 responsibility

B6 Two-way oracle responsibility + conservation

B7 Three-way oracle responsibility + conservation

B8 Shuffled responsibility + conservation

B9 Correct responsibility + operator-null

B10 Release guard only

B11 Full three-way + conservation + release guard

所有方法必须：

- 使用相同 expert base trajectory
- 相同 seed
- 相同 perturbation
- 相同 snapshot
- 相同 control frequency
- paired evaluation

# ==================================================  
12. Perturbation Calibration

使用 calibration episodes 选择不过强的 stress：

- receiver gain 0.7
- receiver delay 2 或 4 control steps
- donor release advance 2 或 4 control steps
- receiver friction reduction
- receiver grasp offset
- COM shift

先逐项测试，不做组合大网格。

选择能产生以下任一情况的强度：

- Base success 40%–80%；  
或
- success 仍高，但 jerk/angular velocity/slip 明显升高。

冻结 perturbation 后在 held-out episodes 比较方法。

# ==================================================  
13. 初始闭环规模

Pilot：

- 5 held-out expert episodes
- 至少 3 个 stress conditions
- 所有主要 baselines
- paired runs

若结果方向稳定，再扩到：

- 10–20 episodes
- handover_mic
- lift_pot
- pick_dual_bottles

初始阶段不要立即运行完整 30+20+controls 矩阵。

# ==================================================  
14. Metrics

Task：

- success
- drop
- slip
- handover completion
- premature release

Disturbance：

- peak object angular velocity
- peak object linear jerk
- E3–E6 pose deviation
- donor residual influence after release
- receiver takeover delay

Mechanism：

- valid authority-pair rate
- oracle responsibility accuracy
- responsibility conservation error
- operator effect-conservation error
- QP feasible rate
- rho_joint occupancy
- harmful contribution suppression
- action deviation from expert
- routing activation outside E2–E5

Cost：

- extra simulator branches
- finite-difference evaluations
- solver latency
- total wall time

统计：

- episode-level paired differences
- episode-level bootstrap 95% CI
- report each seed separately
- no pseudo-replication over branch points

# ==================================================  
15. 结果解释

ORACLE_OPERATOR_PROMISING：

- 多 seed responsibility 可复现；
- full operator 在至少两个 stress condition  
优于最佳 force/distance/phase baseline；
- shuffled responsibility 失去收益；
- conservation-null 明显较差；
- clean episode 不明显退化。

SIGNAL_VALID_OPERATOR_WEAK：

- responsibility 可复现；
- 但 command transfer 不改善控制。

ONLY_EXTREME_INTERVENTION_SUPPORTED：

- 只有 gamma=0.05 才能产生有效 swap。

THREE_WAY_REQUIRED：

- rho_joint 高；
- three-way 明显优于 two-way。

MECHANISM_NOT_SUPPORTED：

- 正确责任与 shuffled 一样；
- 或 effect-conservation only 与 full 一样；
- 或多 seed 信号无法复现。

不要使用单个硬 gate 自动终止全部方向。  
分别报告：

signal validity  
operator validity

specificity  
policy compatibility  
deployability

accepted 始终保持 false。

# ==================================================  
16. 后续阶段

只有在 Oracle operator 至少表现出稳定正趋势后：

1. 训练 ACT baseline；
2. 在 ACT 上使用 oracle responsibility；
3. 再训练 deployable responsibility estimator；
4. 再加入 Diffusion Policy；
5. 最后才考虑 π0.5 / TwinVLA。

若 Oracle operator 都没有收益：  
不要训练 responsibility network 或 π0.5。

# ==================================================  
17. 代码交付

stage2_robotwin/stage2b/  
configs/  
contact_aware_signal.yaml  
oracle_operator.yaml  
intervention/  
task_frame.py  
anisotropic_compliance.py  
follower_mode.py  
paired_authority_profiles.py  
operator/  
local_effect_gain.py  
effect_conserving_transfer_1d.py  
joint_support_mode.py  
release_guard.py  
baselines/  
phase_blend.py  
distance_router.py  
force_router.py  
direct_scale.py  
conservation_only.py  
scripts/  
run_signal_replication.py  
run_oracle_operator_pilot.py  
analyze_stage2b.py  
tests/  
results/  
reports/  
SIGNAL_REPLICATION_REPORT.md  
ORACLE_OPERATOR_REPORT.md  
CURRENT_STAGE2B_DECISION.json

# ==================================================  
18. 第一项立即执行

先不要实现完整 operator。

第一项任务：

1. 在 2 个 calibration episode 上实现并测试  
anisotropic compliance / follower authority profiles；
2. 找到不使用全臂 0.05 compliance，  
但能在左右 profile 中分别产生有效 object-driving motion 的设置；
3. 冻结参数；
4. 在 5 个 held-out episode 的 E4-relative 窗口重放；
5. 输出 per-episode valid-pair rate、oracle accuracy 和 rho_joint；
6. 随后不等待确认，直接实现并运行  
1D oracle responsibility-conserving operator pilot。

每完成一个子阶段，简短汇报：

DONE  
KEY RESULT  
LIMITATION  
NEXT

优先真实机制实验，不要扩建大型形式化审计系统。  
不要删除已有失败 lineage。  
不要把 simulator oracle 结果写成 deployable、VLA 或论文验收结果。
