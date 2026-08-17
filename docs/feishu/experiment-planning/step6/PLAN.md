---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/PYftwWBWpiN4cnkDKQ8czdvwnbb
wiki_node_token: PYftwWBWpiN4cnkDKQ8czdvwnbb
document_token: WLHLdVgkGoNSQpxkRL8cSYeSnOc
revision_id: 6
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: f8b62ed26ee19f05e3c07fa6afe2f498767e11368b2ee5cd7c34434e9f86aafb
---

<title>step6</title>

## 原始计划

继续项目：

[https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering)

最新冻结提交：

05600234df39367424fcb8036533b5e111d2a0aa

任务名称：

Stage 2E —  
Mechanism-Conformant Withdrawal Capacity  
and Actual 4D Role Transfer

最高目标：

不要继续调 Stage 2D 当前 composite capacity、手写 action offset  
或 sparse release state。

Stage 2E 是最后一次机制一致性修复，目标是验证：

true channel-specific donor withdrawal  
→ identifiable receiver takeover capacity  
→ independent desired responsibility  
→ actual 4D effect allocation  
→ measured contribution transfer  
→ timely donor release

若任一核心 gate 失败，停止该方向。  
不得继续上 ACT、Diffusion Policy、π0.5 或新一轮大矩阵。

accepted=false。

# ==================================================  
0. 冻结历史与新分支

保留 Stage 2 / 2B / 2C / 2D 全部代码、结果和负结论。

新建 branch：

stage2e-mechanism-conformant-final

新增：

stage2_robotwin/stage2e/  
preregistration/  
conformance/  
withdrawal/  
capacity/  
allocator/  
state_machine/  
tasks/  
baselines/  
scripts/  
tests/  
results/  
reports/

创建：

FINAL_MECHANISM_HYPOTHESIS.md  
HYPOTHESIS_CODE_MAP.yaml  
EXPERIMENT_CONTRACT.yaml

明确区分：

- actual contribution
- channel-specific withdrawal margin
- desired responsibility
- commanded allocation
- measured contribution

==================================================

1. Hypothesis–Code Conformance Gate  
==================================================

实现 MethodSpec registry。

每个实验方法必须声明：

- uses_capacity
- uses_desired_target
- uses_allocator
- lambda_target
- lambda_internal
- uses_release_guard
- uses_v1_path
- modifies_action
- expected_solver_calls

运行时写入 method_receipt.json。

必须建立自动测试：

A. 4D allocator 在 local/closed-loop 中真实被调用；  
B. conservation-only 使用同一 allocator，  
但 lambda_target=0；  
C. internal-force method 使用 nonzero internal objective；  
D. V1 baseline 调用 Stage 2C 真实 V1 路径；  
E. operator-null 保持相同 oracle/model budget，但不改动作；  
F. release-only 不改变连续 arm action；  
G. solver_latency / solver_call_count 与方法声明一致；  
H. 方法名称与实际 code path 一致。

任何一项失败：

CONFORMANCE_NO_GO  
停止，不运行物理实验。

# ==================================================  
2. True Channel-Specific Withdrawal

禁止继续使用：

donor target -> snapshot qpos  
gripper remains rigidly closed

分别实现：

MOTION_WITHDRAWAL

- donor task-motion axis stiffness/authority 降低；
- donor 可沿物体轨迹被动跟随；
- 保留必要竖直支撑。

SUPPORT_WITHDRAWAL

- donor vertical support 逐渐降低；
- 保留其他最低稳定约束。

ROTATION_WITHDRAWAL

- donor yaw/rotation authority 逐渐降低。

RETENTION_WITHDRAWAL

- donor gripper/contact authority 逐渐降低；
- fade=0 时 donor 必须真实释放或近似零抓持作用。

Fade levels：

1.00  
0.75  
0.50  
0.25  
0.00

每个 fade branch 必须：

- 独立 fresh oracle scene/process；
- 从相同 prefix 重放；
- 不与其他 fade branch 共用 warm-start history；
- 随机化 branch launch order；
- 加 duplicate branch null audit。

若底层支持 stiffness/damping：  
优先直接修改 drive/impedance。

若不支持：  
实现低刚度 object-following controller，  
但必须用实际物体效果证明 authority 被移除。

Withdrawal validity：

1. donor 被移除通道的实际作用随 fade 单调下降；
2. fade=0 时该通道作用 <= fade=1 的 10%；
3. 未移除通道维持在 80% 以上；
4. receiver command 不随 fade 改变；
5. duplicate/order audit 通过；
6. retention fade=0 时 donor contact/grip 真正消失。

若无法实现：

WITHDRAWAL_NOT_IMPLEMENTABLE  
停止整个方向。

# ==================================================  
3. Moving-Handover-Continuation Task

不要继续只使用边界归零的 overlap sinusoid。

创建：

moving_handover_continuation

任务：

1. E3–E5 双手共同跟踪移动轨迹；
2. E5 后 donor 必须退出；
3. receiver 独立继续移动 30–50 mm；
4. receiver 独立完成 5°–15° yaw；
5. 最后放置物体。

要求：

- overlap moving fraction >= 70%；
- receiver-only continuation duration >= 200 ms；
- donor release 是任务成功必要条件；
- receiver incapability 必须造成可观察失败；
- 10 个 clean expert smoke 全部人工视频检查。

# ==================================================  
4. Boundary-Seeking Stress Calibration

不要使用固定 stress 网格后被动等待失败。

Calibration seeds：

0,1,2,3

对每个 seed 和 stress family 执行二分搜索：

- receiver gain
- receiver friction
- receiver grasp offset
- receiver delay
- object mass
- object COM
- reference acceleration
- yaw amplitude

找到 capable ↔ incapable 的边界。

在边界两侧采样。

冻结至少三类 stress：

S1 motion-capability boundary  
S2 support/retention boundary  
S3 rotation/contact boundary

数据要求：

calibration：  
30%–70% capable

held-out：  
至少 30 个 capable episodes  
至少 30 个 incapable episodes

Primary inference unit 是 episode。  
同一 episode 多 anchor 只能做 clustered secondary analysis。

# ==================================================  
5. Channel Withdrawal Margin

对每个通道记录 donor fraction-response curve。

定义：

required_donor_fraction_k  
receiver_capacity_k = 1 - required_donor_fraction_k

通道：

motion  
support  
rotation  
retention

不要先求简单平均。

Primary takeover readiness：

min(  
capacity_motion,  
capacity_support,  
capacity_rotation,  
capacity_retention  
)

或使用 calibration seeds 冻结的逻辑 AND 阈值。

Baselines：

- phase
- contact duration
- contact impulse
- distance
- action magnitude
- V1 responsibility
- episode shuffle
- time shift
- channel shuffle

Capacity GO：

1. held-out episode AUROC >= 0.80；
2. 比最佳 baseline 高 >= 0.08；
3. capable/incapable 数据平衡；
4. stress 增强时各 capacity 单调下降；
5. shuffled/time-shifted 明显失效；
6. 至少提前 100 ms 预测 failure；
7. Brier/ECE 合理；
8. episode-clustered bootstrap CI 报告。

若失败：

CAPACITY_NOT_INFORMATIVE  
停止。

# ==================================================  
6. Actual 4D Effect Model

在 RoboTwin overlap state 估计：

G_L  
G_R

Effect 维度：

[  
task-parallel translation,  
lateral translation,  
vertical support,  
yaw rotation  
]

使用独立 fresh oracle branch 的中心有限差分：

## y(+delta) - y(-delta)

```
   2 delta
```

每个 arm × 每个 effect coordinate 分别估计。

检查：

- condition number
- repeatability
- local linear prediction error
- trust-region validity

若 G 退化：  
fallback 到较低维 active subspace，  
但必须明确记录，不得手写固定 effect 比例。

# ==================================================  
7. Integrate the Actual 4D Allocator

local 和 closed-loop 必须真实调用同一个 allocator。

Objective：

- preserve desired net object effect
- track desired receiver contribution
- stay near base action
- preserve support/contact
- optional internal-wrench penalty

必须保存：

- solver call count
- solver latency
- G_L/G_R
- base action
- allocated action
- predicted net effect
- realized net effect
- desired contribution
- measured actual contribution
- constraint residuals
- clipping/fallback

Conservation-only：

same allocator  
lambda_target = 0

Correct-target：

same allocator  
correct desired target

Swapped/shuffled：

same allocator  
wrong target only

不得再使用手写：

receiver += fixed offset  
donor -= fixed offset

代替 allocator。

# ==================================================  
8. Internal Wrench

只有 simulator 能提供：

- contact impulse/force vector
- contact point
- object pose

时才实现 internal-wrench term。

在 object frame 中计算：

- net wrench
- grasp/internal nullspace wrench

不要使用：

abs(left impulse magnitude - right impulse magnitude)

作为主要 internal-force 证据。

若真实 wrench 不可获得：  
删除 internal-force novelty claim，  
不要保留伪 proxy 主结论。

# ==================================================  
9. Local Actual-Contribution Gate

5 held-out episodes。  
每个 episode 3–5 fixed anchors。

Methods：

L0 base  
L1 conservation-only  
L2 phase target + allocator  
L3 correct capacity target + allocator  
L4 swapped target + allocator  
L5 episode-shuffled target + allocator  
L6 time-shifted target + allocator  
L7 true Stage 2C V1  
L8 internal-wrench variant, only if valid

实际 contribution 必须通过独立：

LR  
L  
R  
ZERO

分支测量。

LOCAL GO：

1. actual receiver contribution 向 r_star 移动 >= 0.15；
2. swapped 产生相反移动；
3. correct 优于 shuffled/time-shifted；
4. target MAE <= 0.15；
5. realized net-effect error <= 0.10；
6. action modification 5%–25%；
7. contact retention 不下降；
8. conservation-only 无法复制 contribution transfer；
9. branch-order/null audit 通过。

若失败：

ALLOCATOR_NOT_CAUSAL  
停止。

# ==================================================  
10. Desired Responsibility and Release Timing

capacity 可低频计算，  
但 target 每个 control step 更新。

对 capacity trace 做：

- time interpolation
- confidence hold
- hysteresis
- dwell

State：

DONOR_LEAD  
SHARED_TRANSFER  
RECEIVER_LEAD  
ABORT_OR_RECOVER

Release guard 直接使用：

- support readiness
- retention readiness
- stable dwell
- receiver contact

禁止继续使用：

desired_share >= 0.5

代替 readiness。

加入静态 timing reachability test：

根据：

- overlap length
- capacity update rate
- target slew
- release time

验证 target 理论上能否按时达到目标。

Timing smoke：

CAPABLE：

- donor 正确释放率 >= 90%

INCAPABLE：

- 错误释放率 <= 10%
- 应进入 shared/abort

不得再次出现：  
all donor-open requests blocked

# ==================================================  
11. Small Closed-Loop Pilot

只有前面全部 GO 后运行。

Held-out seeds：

至少 8

Conditions：

2 个 eligible boundary stresses

- clean

Methods：

P0 base expert  
P1 phase-only handover  
P2 release guard only  
P3 conservation-only allocator  
P4 correct capacity + desired target + allocator  
P5 shuffled capacity + same allocator

总规模：

8 seeds × 3 conditions × 6 methods  
= 144 cells maximum

PILOT GO：

1. correct capacity > shuffled；
2. full > phase-only；
3. full > conservation-only；
4. 至少一个 stress success +10 pp；
5. 另一个 stress 方向一致；
6. clean degradation <=5 pp；
7. actual contribution 跟踪目标；
8. donor 按时释放；
9. net effect / contact safety 可接受。

只有 PILOT GO 后：

- 扩大矩阵
- 重新做独立 novelty review
- ACT + oracle capacity
- learned estimator
- Diffusion Policy
- π0.5

# ==================================================  
12. Stop Rules

以下任何一个结论出现，结束该方向：

CONFORMANCE_NO_GO  
WITHDRAWAL_NOT_IMPLEMENTABLE  
CAPACITY_NOT_INFORMATIVE  
ALLOCATOR_NOT_CAUSAL  
PILOT_NO_GO

只有：

STATE_MACHINE_ONLY_FAILURE

允许修一次 timing/state-machine bug，  
因为此时 signal 与 allocator 已分别通过。

# ==================================================  
13. Resource Contract

dev14：

- maximum 2 GPUs concurrently
- prefer CPU/SAPIEN
- no PAI
- no ACT/pi0.5 before pilot GO
- do not kill existing jobs
- preserve negative lineage
- do not build another large audit framework
- no downstream override after failed gate

# ==================================================  
14. Deliverables

stage2_robotwin/stage2e/  
preregistration/  
FINAL_MECHANISM_HYPOTHESIS.md  
HYPOTHESIS_CODE_MAP.yaml  
EXPERIMENT_CONTRACT.yaml  
conformance/  
method_registry.py  
runtime_receipt.py  
withdrawal/  
motion_withdrawal.py  
support_withdrawal.py  
rotation_withdrawal.py  
retention_withdrawal.py  
branch_isolation.py  
capacity/  
withdrawal_margin.py  
boundary_search.py  
episode_analysis.py  
allocator/  
identify_effect_map_4d.py  
effect_allocator_4d_runtime.py  
contribution_audit.py  
state_machine/  
desired_role_state.py  
release_readiness.py  
timing_reachability.py  
tasks/  
moving_handover_continuation.py  
tests/  
results/  
reports/  
CONFORMANCE_REPORT.md  
WITHDRAWAL_VALIDITY_REPORT.md  
CAPACITY_REPORT.md  
LOCAL_ALLOCATOR_REPORT.md  
RELEASE_TIMING_REPORT.md  
PILOT_REPORT.md  
CURRENT_STAGE2E_DECISION.json

# ==================================================  
15. 第一项立即执行

当前只执行：

A. Hypothesis–Code Conformance Gate  
B. true motion/support/rotation/retention withdrawal  
C. per-branch fresh-scene order/null audit  
D. 3 个 episode 的 withdrawal monotonicity test

不要实现 capacity classifier。  
不要运行 allocator。  
不要跑 closed-loop。

第一份交付：

WITHDRAWAL_VALIDITY_REPORT.md  
WITHDRAWAL_VALIDITY_DECISION.json

只有 withdrawal 语义真实成立后，  
才进入 capacity boundary search。

每个阶段汇报：

DONE  
WHAT THE CODE ACTUALLY EXECUTED  
KEY RESULT  
WHAT WAS FALSIFIED  
LIMITATION  
NEXT
