---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/Eqlcw8WZniGSMtkOTuZc5gcgnMg
wiki_node_token: Eqlcw8WZniGSMtkOTuZc5gcgnMg
document_token: Km1FdY8PDoJwgExdkOJcBYyen9b
revision_id: 4
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: 8b1907614bbac3b72f05b9d862727ca255f5bc0eaa92e772dbe35244d7d716be
---

# step2

继续推进 R22-P19 Responsibility-Routed Multi-Effector Steering。



现有仓库：

https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering



最高优先级目标：

进入真正的双臂仿真实验，验证左右机械臂之间的 causal responsibility

（因果责任）是否能够被识别，以及 responsibility-conserving command

transfer（责任守恒的命令转移）是否能改善双臂交接稳定性。



重要修正：

之前的 LIBERO_SUBSTRATE_NO_GO 不再作为阻止双臂实验的硬门槛。

该结果只来自单臂 arm-pose vs gripper 的代理实验，不能代表原始双臂假设失败。

LIBERO 结果保留为 preliminary evidence：

- phase AUC ≈ 0.839
- authority-swap accuracy ≈ 0.933
- 但相对 action-magnitude baseline 的增量偏小
- gate-off false activation 偏高

这些缺陷要在双臂实验中继续观察，但不得因为旧 gate 没通过而停止。



本阶段仍需保持：

- accepted=false
- 不把 oracle/simulator privileged result 称为 deployable result
- 不把单个正向数字称为论文结论
- 但不再使用单个预注册阈值自动终止整个方向
- 根据真实双臂实验结果动态调整 responsibility 定义和 operator

==================================================

一、实验平台和模型选择

==================================================



首选 benchmark：

RoboTwin 2.0



第一批任务：



Primary：

1. handover_block

用于验证一只手向另一只手转移同一物体控制权。

Secondary：

1. handover_mic

用于验证不规则长物体和不同抓取几何下的责任转移。

Control：

1. lift_pot

两只手长期共同承载同一个物体，不应被错误解释成必须从左向右转移。

1. pick_dual_bottles

两只手分别操作不同物体，共享物体责任 router 应保持关闭。

模型选择遵循“适合当前问题，而不是强制 π0.5”：



Stage 2A：

- RoboTwin expert controller / expert demonstrations
- simulator counterfactual branching
- 不需要训练策略，不需要世界模型

Stage 2B：

- ACT 作为第一 learned-policy baseline
- 原因：训练快、action chunk 清楚、左右臂动作容易拆分

Fallback：

- 如果 ACT baseline 长期无法达到可分析水平，可以改用 Diffusion Policy
- 如果 learned policy 暂时不可用，先用 expert replay 验证 oracle operator

Later：

- 只有 oracle responsibility operator 在 ACT/DP 上表现出稳定信号后，

才考虑 π0.5、TwinVLA、DIF 或 BiCoord

- 不要一开始训练 π0.5
- 当前 idea 不需要 DINO-WM 或大型视频世界模型

==================================================

二、立即执行的第一项工作：双臂环境与事件链 Smoke

==================================================



先建立独立 branch：



stage2-robotwin-bimanual-oracle



不要修改已有 LIBERO Phase-1 结果。

新增目录：



stage2_robotwin/

  configs/

  wrappers/

  responsibility/

  operator/

  baselines/

  tests/

  results/

  reports/



冻结并记录：



- R22-P19 repo commit
- RoboTwin commit
- ACT/XPolicyLab commit
- Python/PyTorch/CUDA/SAPIEN 版本
- robot embodiment
- control frequency
- action representation
- action chunk size
- camera keys
- left/right arm state and action ordering
- task config
- random seeds

第一轮只运行 handover_block：



1. 运行 10 个 expert smoke episodes。
2. 确认每个 episode 中都能识别：

E0：donor 单臂控制物体

E1：receiver 首次接触

E2：双臂共同接触开始

E3：receiver 稳定抓持

E4：donor 发出松开命令

E5：donor 实际失去接触

E6：receiver 单臂控制物体

1. 保存视频和时间对齐曲线。
2. 人工检查全部 10 条事件链。
3. 若事件顺序错误，先修 event detector，不进入正式反事实分支。
4. 检查 simulator snapshot/restore：

   - 同一 snapshot
   - 同一 joint action
   - 重放两次
   - object pose/twist 应在容差内一致
5. 生成：

stage2_robotwin/reports/SMOKE_REPORT.md

stage2_robotwin/results/smoke_summary.json

Smoke 报告必须回答：



- handover 是否真实经过双臂 overlap
- donor/receiver 身份是否正确
- snapshot 是否可确定性重放
- gripper neutral command 是否保持抓持
- 左右臂动作维度是否正确
- contact actor ID 是否可读取
- object pose/twist 是否可读取
- 是否可以修改单侧 gain、delay、friction

完成 Smoke 后直接继续正式 Signal Audit，不需要再次等待确认。



==================================================

三、Stage 2A：真正双臂 Oracle Responsibility Signal Audit

==================================================



数据规模：



handover_block：

- 至少 30 个成功 expert episodes
- 额外 20 个扰动 episodes

lift_pot：

- 至少 20 个成功 episodes

pick_dual_bottles：

- 至少 20 个成功 episodes

handover_mic：

- handover_block 完成后再增加 20–30 个 episodes

在 E1–E6 的 overlap 区间保存 branch states。

默认每隔 2–5 个 control steps 分支一次。



每个 branch state 从完全相同的 simulator snapshot 执行四个分支：



LR：

  左右臂均执行原始 action。



L：

  左臂执行原 action；

  右臂执行 neutral action。



R：

  右臂执行原 action；

  左臂执行 neutral action。



ZERO：

  两臂都执行 neutral action。



neutral action 必须：

- 末端增量为零
- 保持当前 gripper closure
- 不主动打开夹爪
- 保持相同低层控制模式
- 不能通过让某只手松开物体来人为制造责任差异

Counterfactual horizon：

- H_cf=5
- H_cf=10 作为敏感性分析

Outcome vector 至少包含：



- object translation
- object rotation
- object linear velocity
- object angular velocity
- support height
- task progress
- slip
- drop
- contact retention

计算：



phi_L = 0.5 \* [(y_L - y_ZERO) + (y_LR - y_R)]

phi_R = 0.5 \* [(y_R - y_ZERO) + (y_LR - y_L)]



synergy = y_LR - y_L - y_R + y_ZERO



不要把所有结果强行压成一个责任标量。

至少分别输出：



- motion responsibility
- support responsibility
- task-progress responsibility
- harmful/opposing contribution
- joint synergy

如果 joint synergy 很高，立即考虑三通道表示：



rho_L

rho_R

rho_joint



而不是强行要求 rho_L + rho_R = 1。



==================================================

四、必须加入的 Authority-Swap 实验

==================================================



这是判断 idea 是否真的有因果意义的核心实验。



构造 paired states，使以下变量尽量保持相同：



- object pose
- left/right TCP pose
- 当前 handover phase
- 当前 contact preload
- gripper-object distance
- 初始 contact force
- 当前图像

但交换未来哪只手真正能驱动物体，例如：



1. 左右 actuator gain 交换：

(1.3, 0.7) vs (0.7, 1.3)

1. 单侧动作 delay：

left delay 0/2/4 steps

right delay 0/2/4 steps

1. 单侧 contact friction：

left high/right low

left low/right high

1. 单侧 compliance 改变
2. 保持接触力相近，但让一只手动作位于 object-motion direction，

另一只手动作位于 object-motion null direction

Oracle responsibility 应跟随实际 authority 变化，而不是跟随：



- 左右手身份
- 距离
- 当前力大小
- 固定 handover phase

需要比较：



- fixed 50/50
- linear phase transfer
- distance share
- force share
- arm identity
- oracle counterfactual responsibility
- shuffled oracle responsibility

本阶段不要因为某个阈值差一点自动停止。

需要输出综合判断：



SIGNAL_STRONG

SIGNAL_PARTIAL

SIGNAL_NEEDS_THREE_WAY

SIGNAL_WEAK



判断依据至少包括：



- authority-swap accuracy
- responsibility phase curve
- 与 force/distance/action-magnitude 的增量信息
- responsibility mismatch 对 jerk/slip/drop 的预测能力
- shuffled control 是否失效
- lift_pot 中 joint synergy 是否合理
- pick_dual_bottles 中 shared-object router 是否基本关闭

==================================================

五、Stage 2B：ACT + Oracle Responsibility Operator

==================================================



完成真实双臂 Signal Audit 后，无论是否所有旧式 gate 全通过，都允许训练 ACT，

但必须在报告中记录 signal 强弱和风险。



ACT 数据：



- handover_block 先使用 100 条 expert demonstrations
- 先训练 1 个 seed 做 smoke
- 然后扩展到 3 个 seeds
- 使用固定测试 seeds

如果 ACT baseline：



- success 40%–90%：

直接进行方法对比

- success <40%：

先排查数据/action/gripper/control-frequency；

若仍不稳定，使用 Diffusion Policy 或 expert replay 验证 operator，

不要把低质量 ACT 失败归因于 responsibility method

- success >90%：

使用 gain、delay、friction、COM、release offset 构造 stress test

ACT 输出：



u_L_base

u_R_base



使用 simulator finite difference 或局部 effect model 估计：



B_L = d(object effect) / d(u_L)

B_R = d(object effect) / d(u_R)



基础动作的物体效果：



d_base = B_L u_L_base + B_R u_R_base



责任守恒 operator：



minimize



  ||B_L u_L_new - rho_L d_base||²

- ||B_R u_R_new - rho_R d_base||²
- lambda ||u_new - u_base||²

subject to：



- B_L u_L_new + B_R u_R_new ≈ d_base
- action bounds
- velocity/acceleration bounds
- no premature donor release
- collision constraints
- receiver 没有稳定抓持前 donor 不得完全退出

如果 rho_joint 较高：



- 不执行单向责任转移
- 保留 joint-support mode
- 只消除左右动作中相互冲突的分量
- 保留共同支撑所必需的分量

==================================================

六、闭环 Baselines 与 Ablations

==================================================



比较：



A0. Base ACT



A1. Linear time/phase blending



A2. Distance-based responsibility



A3. Contact-force-based responsibility



A4. Learned phase gate

若容易实现，可用轻量 MLP 预测 handover phase



A5. Oracle responsibility，直接缩放左右动作，不做 effect conservation



A6. Oracle responsibility + effect conservation

这是 proposed



A7. Shuffled responsibility + effect conservation



A8. Correct responsibility + operator-null

计算责任但不修改动作



A9. Oracle responsibility + conservation-null



A10. Three-way responsibility：

rho_L / rho_R / rho_joint

若 Signal Audit 显示 synergy 明显，则作为主方法之一



所有方法必须：



- 使用同一 ACT checkpoint
- 使用相同 seeds
- 使用相同 observation
- 使用相同 base action chunk
- 使用相同控制频率
- 记录相同额外计算量

==================================================

七、扰动条件

==================================================



handover_block / handover_mic：



- receiver gain：0.7 / 1.0 / 1.3
- donor release offset：-4 / 0 / +4 steps
- unilateral delay：0 / 2 / 4 steps
- unilateral friction：low / nominal / high
- object COM：left / center / right
- receiver grasp offset
- object mass
- gripper compliance

lift_pot：



- 左右 gain 不平衡
- COM 偏移
- 单侧 delay
- 单侧 friction

完整方法不应错误地将双臂共同承载强制变成单臂接管。



pick_dual_bottles：



- shared-object responsibility router 应保持关闭
- clean success 不应明显下降
- 不应因为两个手臂同时动作就错误触发 shared responsibility

==================================================

八、主要指标

==================================================



Task：



- success rate
- drop rate
- slip rate
- successful release rate

Handover：



- peak object linear jerk
- peak object angular velocity
- object pose deviation
- overlap duration
- receiver takeover delay
- donor residual influence after release
- premature release count

Mechanism：



- authority-swap accuracy
- responsibility conservation error
- responsibility temporal variation
- rho_joint / synergy ratio
- responsibility mismatch vs disturbance AUROC
- routing activation outside shared-object overlap
- responsibility curve aligned to E1–E6

Cost：



- additional simulator calls
- QP latency
- total inference latency
- action deviation from Base ACT

所有结果都要 paired comparison，并报告置信区间。



==================================================

九、动态决策规则

==================================================



不要再使用“一个 gate 没过就整个项目永久停止”的规则。



分别判断：



1. Signal validity
2. Operator validity
3. Policy compatibility
4. Specificity
5. Deployability

进入 learned responsibility estimator 的建议条件：



- Oracle operator 在至少两个真实双臂扰动条件中，

相比最佳 force/distance/phase baseline 有一致改善

- shuffled responsibility 明显失去收益
- conservation-null 明显差于完整 operator
- lift_pot 不发生错误单臂接管
- pick_dual_bottles 基本不被干扰

不要求所有历史 gate 全通过。



如果 signal 有信息，但 operator 没效果：



- 不要立即否定 idea
- 优先修改 operator：

  - three-way responsibility
  - responsibility-conditioned impedance
  - 只调整 donor release timing
  - 只投影 object-control component
  - 保留 arm null-space motion

如果真正双臂 oracle responsibility 仍不优于 force/distance/phase，

并且 authority swap 也识别不了，则考虑终止原始 idea。



==================================================

十、执行与资源约束

==================================================



- dev14 最多同时使用两张 GPU
- expert/simulator branch 优先 CPU 或单卡
- 不杀已有任务
- 不为了审计投入大规模 formal infrastructure
- 优先真实实验、视频、曲线和 paired metrics
- 每完成一个阶段立即给出简短状态：

DONE / ISSUE / NEXT

- 根据实验结果实时调整后续流程
- 不需要等待我逐阶段确认，除非出现不可逆的数据删除、代码覆盖或高成本资源冲突

==================================================

十一、交付物

==================================================



stage2_robotwin/

  configs/

  source_manifest.json

  experiment_plan.md

  wrappers/

    bimanual_trace_wrapper.py

    event_detector.py

    counterfactual_brancher.py

  responsibility/

    shapley_responsibility.py

    joint_synergy.py

    responsibility_analysis.py

  operator/

    local_effect_jacobian.py

    responsibility_projection_qp.py

    joint_mode_operator.py

  baselines/

  tests/

  results/

    smoke/

    oracle_signal/

    act_baseline/

    oracle_operator/

    traces.parquet

    metrics.csv

    summary.json

    plots/

    videos/

  reports/

    SMOKE_REPORT.md

    SIGNAL_REPORT.md

    ACT_BASELINE_REPORT.md

    ORACLE_OPERATOR_REPORT.md

    CURRENT_DECISION.json



CURRENT_DECISION.json 至少包含：



- original_bimanual_signal_tested
- signal_status
- operator_status
- oracle_result
- policy_used
- tasks_completed
- failed_conditions
- next_recommended_stage
- accepted=false

第一项立即执行：

先完成 RoboTwin handover_block 的 10 个 expert smoke episodes、

事件链人工审计和 snapshot deterministic replay。

完成后直接继续双臂 Oracle Responsibility Signal Audit。
