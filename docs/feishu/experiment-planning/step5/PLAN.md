---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/T5txw3KpPiEwQHk54uicU1BOnCd
wiki_node_token: T5txw3KpPiEwQHk54uicU1BOnCd
document_token: PNBEdKW24oDrnNxJW3HcOnCQnEh
revision_id: 2
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: 02cd80f5277295f8fdac286b0ab3489a2df9f82b13602ce9657011ff26119c6e
---

<title>step5</title>

继续项目：

[https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering)

任务名称：

R22-P19 V2 / Stage 2D —  
Counterfactual Takeover Capacity  
and Desired Responsibility Tracking

当前冻结事实：

Stage 2C commit：  
e31e1ddc78e8ffa22c5dba51d2988151ec7f755f

Stage 2C 已完成 oracle-level falsification：

- natural responsibility = RESPONSIBILITY_UNSTABLE
- local operator = RESPONSIBILITY_NOT_CAUSAL
- correct responsibility did not beat swapped / episode-shuffled / time-shifted
- full did not beat conservation-only
- stress improvement = 0/3
- final decision = RESPONSIBILITY_MECHANISM_NOT_SUPPORTED
- ACT gate = BLOCK
- accepted=false

不得继续简单调 Stage 2C 的：

- eta
- gamma
- threshold
- current Shapley responsibility
- 1D self-targeted nullspace operator

不得直接训练：

- ACT
- Diffusion Policy
- π0.5
- learned responsibility estimator

# ==================================================  
0. V1 冻结与 V2 立项

1. 保留 Stage 2 / 2B / 2C 全部代码、结果和负结论。
2. 新建 branch：

stage2d-takeover-capacity-v2

1. 新建：

stage2_robotwin/stage2d/  
preregistration/  
novelty/  
analytic/  
tasks/  
capacity/  
operator/  
baselines/  
scripts/  
tests/  
results/  
reports/

1. 创建：

V2_HYPOTHESIS.md

必须清楚区分：

A. actual contribution  
当前实际贡献

B. takeover capacity  
如果另一只手退出，当前手是否能继续完成任务

C. desired responsibility  
任务下一阶段希望由谁承担多少责任

禁止：

desired responsibility = current measured responsibility

1. 创建：

NOVELTY_BOUNDARY.md

并启动两个独立 reviewer。  
V2 不自动继承 V1 的 N3。

==================================================

1. Stage 2D-A：Analytic Bimanual Testbed  
==================================================

第一步只执行解析测试床。

系统：

e = G_L u_L + G_R u_R

effect 维度：

[  
task-parallel translation,  
lateral translation,  
vertical support,  
yaw rotation  
]

必须能够计算：

- net object effect
- left contribution
- right contribution
- internal mode / internal-force proxy
- desired responsibility
- actual responsibility

随机生成至少 200 个固定 seeds：

- different G_L/G_R
- different condition numbers
- left/right gain mismatch
- delay
- partial actuator failure
- different base action
- different desired responsibility ramps
- joint-support cases
- conflict cases

Operator objective：

minimize

||G_L u_L + G_R u_R - e_star||\_W²

- lambda_r \*  
||G_R u_R - receiver_share_star \* e_star||²
- lambda_internal \*  
||internal_component(u_L,u_R)||²
- lambda_action \*  
||u-u_base||²

subject to：

- action bounds
- slew-rate bounds
- support constraint
- net-effect error bound

Baselines：

A0 base  
A1 conservation-only  
A2 fixed phase target  
A3 V1 self-targeted current responsibility  
A4 correct desired responsibility  
A5 left-right swapped desired responsibility  
A6 random desired responsibility  
A7 correct desired responsibility + internal-force suppression

Metrics：

- desired-vs-actual contribution MAE
- net-effect relative error
- internal-force proxy
- action modification ratio
- feasibility
- swapped direction response
- joint-support preservation

ANALYTIC GO：

1. contribution tracking MAE <= 0.15
2. net effect relative error <= 0.05
3. correct desired target beats swapped/random
4. swapped target produces opposite contribution movement
5. internal force <= conservation-only
6. feasibility >= 90%
7. V1 self-targeted method cannot reproduce desired transfer

若未通过：  
停止，不进入 RoboTwin V2。

输出：

reports/ANALYTIC_OPERATOR_REPORT.md  
reports/ANALYTIC_OPERATOR_DECISION.json

# ==================================================  
2. Stage 2D-B：Active Handover Task

只有 Analytic GO 后继续。

基于 RoboTwin handover_block 创建：

active_handover_block

任务要求：

1. donor 抓住物体；
2. 物体沿连续参考轨迹运动；
3. receiver 在运动中接触并抓住；
4. overlap 期间物体仍需跟踪轨迹；
5. donor 渐进退出；
6. receiver 接管后继续跟踪并放置。

必须记录：

- object reference trajectory
- object pose/twist
- trajectory tracking error
- left/right TCP
- contacts
- contact impulses
- gripper state
- object mass and COM
- donor/receiver phase
- internal-force proxy

Overlap 主窗口必须满足：

- object speed > frozen threshold
- duration >= frozen minimum
- receiver takeover affects future task success

先运行 expert smoke：

- 10 successful episodes
- manual video audit
- event-chain audit
- fresh-process determinism audit

# ==================================================  
3. Stage 2D-C：Oracle Takeover Capacity

在 overlap 状态做 donor-fade counterfactual。

Fade levels：

0.00  
0.25  
0.50  
0.75  
1.00

Horizons：

25 / 50 / 100 physics steps  
= 100 / 200 / 400 ms at 250 Hz

分别执行：

MOTION_FADE

- donor task-direction authority gradually removed
- minimum vertical support retained

SUPPORT_FADE

- donor vertical support gradually removed

ROTATION_FADE

- donor rotational authority gradually removed

RETENTION_FADE

- donor grasp/contact support gradually removed

Capacity vector：

[  
motion_capacity,  
support_capacity,  
rotation_capacity,  
retention_capacity  
]

Capacity 必须依据真实未来结果：

- trajectory tracking
- orientation tracking
- min object height
- slip
- contact retention
- drop
- takeover completion

禁止使用 V1 Shapley motion responsibility  
作为 takeover-capacity label。

# ==================================================  
4. Capacity Baselines

S0 fixed phase  
S1 contact duration  
S2 contact impulse / force  
S3 distance  
S4 action magnitude  
S5 V1 Shapley responsibility  
S6 oracle takeover capacity  
S7 episode-shuffled capacity  
S8 time-shifted capacity  
S9 channel-shuffled capacity

Calibration seeds：

0,1,2

Held-out seeds：

3,5,6,7,8,9,10,11

Episode 是唯一统计单位。

CAPACITY GO：

1. full-donor-fade success AUROC >= 0.80
2. outperform best heuristic by >= 0.08
3. report Brier score and ECE
4. capacity decreases monotonically with lower gain/friction
5. capacity increases with improved grasp quality
6. shuffled/time-shifted capacity loses performance
7. predicts takeover failure at least 100 ms early
8. H25/H50/H100 direction mostly consistent

若未通过：  
停止，不实现 closed-loop V2。

输出：

reports/TAKEOVER_CAPACITY_REPORT.md  
reports/TAKEOVER_CAPACITY_DECISION.json

# ==================================================  
5. Desired Responsibility State Machine

实现：

DONOR_LEAD  
SHARED_TRANSFER  
RECEIVER_LEAD  
ABORT_OR_RECOVER

Transition：

DONOR_LEAD → SHARED_TRANSFER  
only if:

- receiver contact stable
- support capacity above threshold
- retention capacity above threshold

SHARED_TRANSFER → RECEIVER_LEAD  
only if:

- motion capacity above threshold
- rotation capacity above threshold
- capacity stable for minimum dwell time

Rollback：

- capacity drops
- slip increases
- contact lost
- tracking error rises

Desired receiver share：

# r_star_receiver(t+1)

clip(  
r_star_receiver(t) + bounded_delta,  
0,  
1  
)

需要 hysteresis、minimum dwell 和 rate limit。

比较：

- phase-only ramp
- instantaneous capacity ramp
- capacity + hysteresis
- shuffled capacity ramp

# ==================================================  
6. Stage 2D-D：4D Desired-Responsibility Operator

Effect space：

[  
task-parallel translation,  
lateral translation,  
vertical support,  
yaw rotation  
]

估计：

G_L  
G_R

可使用：

- simulator finite difference
- analytical robot Jacobian
- short-horizon local identification

Control objective：

- track desired object effect
- track desired responsibility
- reduce internal-force conflict
- remain near base action
- preserve contact and support

每次控制必须记录：

- actual contribution
- desired contribution
- takeover capacity
- state-machine mode
- predicted net effect
- realized net effect
- internal-force proxy
- action modification
- fallback/clipping
- safety constraint

# ==================================================  
7. Local Causal Gate

先运行局部 H=25/50 rollouts。

Methods：

L0 base  
L1 conservation-only  
L2 phase target + V2 operator  
L3 correct capacity-generated r_star  
L4 swapped r_star  
L5 episode-shuffled r_star  
L6 time-shifted r_star  
L7 V1 self-targeted responsibility  
L8 full + internal-force suppression

LOCAL GO：

1. actual receiver contribution moves toward r_star >= 0.15
2. swapped moves in opposite direction
3. correct beats shuffled and time-shifted
4. contribution tracking MAE <= 0.15
5. net-effect error <= 10%
6. internal force <= base/conservation-only
7. contact retention unchanged or improved
8. action modification in 5%–30%
9. method effect exceeds null floor

若未通过：  
停止，不运行完整 closed loop。

# ==================================================  
8. Stress Calibration

Candidates：

receiver_gain:  
0.8 / 0.6 / 0.4

receiver_delay:  
4 / 8 / 12 / 16 steps

receiver_friction:  
0.7 / 0.5 / 0.3 / 0.2

receiver_grasp_offset:  
5 / 10 / 15 / 20 mm

object_mass_scale:  
0.8 / 1.2 / 1.5

object_COM_shift:  
10 / 20 / 30 mm

reference_acceleration:  
low / medium / high

donor_fade_rate:  
slow / medium / fast

temporary_receiver_contact_loss:  
short / medium

Freeze three eligible stresses：

T1 capability mismatch  
T2 premature transfer  
T3 contact/rotation degradation

Eligibility：

- Base success 30%–80%  
or
- disturbance >= 2x clean
- and full oracle has improvable room

不要冻结 100% success 且 disturbance <2x clean 的条件。

# ==================================================  
9. Oracle Closed-Loop Baselines

C0 Base expert  
C1 Fixed phase ramp  
C2 Contact-duration handover  
C3 Force/impulse handover  
C4 Release guard only  
C5 V1 Shapley responsibility  
C6 Oracle capacity + release only  
C7 Phase target + V2 operator  
C8 Correct capacity + desired responsibility  
C9 Episode-shuffled capacity  
C10 Time-shifted capacity  
C11 Swapped desired responsibility  
C12 Conservation-only  
C13 Full capacity + hysteresis + 4D allocation  
C14 Full + internal-force suppression  
C15 Operator-null

All methods：

- same seed
- same expert/reference tape
- same stress
- same oracle budget where applicable
- fresh process per cell
- episode as inference unit

# ==================================================  
10. Metrics

Task：

- success
- handover completion
- drop
- premature release
- takeover failure

Tracking：

- object trajectory RMSE
- orientation RMSE
- final placement error

Contact：

- slip
- contact retention
- min object height
- internal-force proxy
- contact impulse spikes

Capacity / responsibility：

- capacity AUROC
- Brier / ECE
- desired-vs-actual contribution MAE
- responsibility transition duration
- abort/recovery count
- responsibility slew

Cost：

- branch count
- simulator physics steps
- solver latency
- action modification
- fallback rate

# ==================================================  
11. Oracle V2 GO

ORACLE_V2_SUPPORTED only if：

1. capacity AUROC >= 0.80
2. correct capacity beats force/phase/contact-duration
3. correct beats shuffled/time-shifted
4. contribution tracking MAE <= 0.15
5. net-effect error <= 10%
6. full beats conservation-only
7. at least two eligible stresses improve
8. success absolute gain >=5 pp  
or failure-rate relative reduction >=20%
9. clean degradation <=3 pp
10. internal force does not increase
11. at least 4/5 evaluation seeds consistent

Only after ORACLE_V2_SUPPORTED：

- train ACT
- test ACT + oracle capacity
- train deployable capacity estimator
- test Diffusion Policy
- later test pi0.5 / TwinVLA

# ==================================================  
12. Resource Contract

dev14：

- maximum 2 GPUs concurrently
- prefer CPU/SAPIEN for analytic and oracle stages
- no PAI
- no ACT/pi0.5 before oracle gate
- do not kill existing jobs
- preserve all failure artifacts
- do not expand unnecessary audit infrastructure

# ==================================================  
13. Deliverables

stage2_robotwin/stage2d/  
preregistration/  
V2_HYPOTHESIS.md  
NOVELTY_BOUNDARY.md  
EXPERIMENT_CONTRACT.yaml  
analytic/  
system.py  
operator.py  
baselines.py  
run_analytic.py  
tasks/  
active_handover_block.py  
capacity/  
donor_fade.py  
channel_capacity.py  
capacity_analysis.py  
operator/  
desired_responsibility_state.py  
effect_allocator_4d.py  
internal_force.py  
scripts/  
tests/  
results/  
reports/  
ANALYTIC_OPERATOR_REPORT.md  
TAKEOVER_CAPACITY_REPORT.md  
LOCAL_CAUSAL_GATE_REPORT.md  
STRESS_CALIBRATION_REPORT.md  
ORACLE_V2_REPORT.md  
CURRENT_STAGE2D_DECISION.json

# ==================================================  
14. 第一项立即执行

当前只执行：

A. 冻结 V1 负结果  
B. 写 V2_HYPOTHESIS.md  
C. 建立 Analytic Bimanual Testbed  
D. 跑：  
correct  
swapped  
random  
conservation-only  
V1 self-targeted  
full internal-force regularization  
E. 输出 ANALYTIC_OPERATOR_DECISION.json

只有 Analytic GO 后，  
才实现 active_handover_block 和 takeover-capacity audit。

每完成一个阶段汇报：

DONE  
KEY RESULT  
WHAT WAS FALSIFIED  
LIMITATION  
NEXT

不得为了继续项目而忽略明确负结果。  
不得把 V2 自动称为 N3。
