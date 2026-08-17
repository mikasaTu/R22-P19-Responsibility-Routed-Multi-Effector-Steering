---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/BXZ6wKg28iGg1vkq5occ8CBrnmb
wiki_node_token: BXZ6wKg28iGg1vkq5occ8CBrnmb
document_token: NYrJdegHSo2EcGxGPmwcwhQpnpc
revision_id: 7
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: adf797a674c54c67fd30b7b0e9144512a0e15a521a003e74e2d204acd179f7ca
---

<title>实验报告</title>

# R22-P19 Step 2 — RoboTwin 双臂 Oracle 初步验证报告

**执行日期：**2026-08-13

**当前机器结论：**PILOT_LOCALIZED_SIGNAL_FORMAL_PENDING

**验收标记：**accepted=false

**一句话结论：**RoboTwin 真实双臂 handover_block 的事件、接触、可恢复反事实分支链路已跑通；普通干预没有形成可解释的物体 authority swap，强 0.05 非主导臂 compliance 诊断仅在交接释放窗口产生局部正信号。因此这是“局部机制线索、正式审计待完成”，不是正式 SIGNAL 分类，也不是 operator 或 ACT 有效性结果。

## 1. 本轮执行范围

- 任务：RoboTwin 2.0 的真实双臂 **handover_block**，Aloha-AgileX 双臂 embodiment。
- RoboTwin commit：266f3aadf505a4f7fe9af0faa41a20f5f47cd123；XPolicyLab gitlink：c37109c500be67d0dea6b36bf7337bbd26e763cd。
- 物理与 trace：250 Hz；observer RGB 视频目标 10 Hz，并保留事件帧。
- 动作契约：14-D，即左臂 6 + 左夹爪 1 + 右臂 6 + 右夹爪 1。
- 运行位置：dev14；渲染使用单张 A800 GPU3；没有进行大规模训练。
- planner 使用显式 mplib_screw fallback。当前环境没有可用的 CuRobo/PyTorch3D，因此本结果不声称 CuRobo expert parity；每个成功 episode 都记录了 2 次 MPLib 无法执行的 CuRobo partial-pose hold 请求。

## 2. 双臂 smoke 结果

- 最终 run 共尝试 11 个确定性 seed，选择出 10 个 task-success 且 E0–E6 完整的 episode；seed 4 在 receiver contact 之前 planner 失败并被原样保留。10/11 只是 seed-search yield，不是无偏成功率。
- 10/10 episode 通过逐个 montage 人工视觉检查：donor-only、双臂共同接触、donor release、receiver-only 四阶段均可见。
- 10/10 episode 可读取 contact actor IDs、impulse、物体 pose 与 twist。
- 在 E3 快照上重复两次相同 H=10 drive target，10 个 episode 的物体 pose、线速度、角速度最大差异均为 0。
- E2→E5 双臂 overlap：4.576–4.840 s，中位数 4.736 s；E3→E4 稳定 overlap 中位数 2.658 s；E5→E6 固定为 0.056 s。
- 保留全部开发谱系：planner API 错误、空 target_pose、错误 unpack_poses 快照、一次有界 replay divergence，以及修正后的零差异 replay；没有只保留成功样本。

## 3. Oracle 分支与责任分解实现

- 从同一 SAPIEN 状态执行 LR、L、R、ZERO 四个分支，neutral arm 使用当前 measured qpos + zero target velocity，并保持夹爪闭合与低层 drive mode。
- 快照覆盖 articulation qpos/qvel、root pose/twist、joint drive position/velocity targets、dynamic actor pose/twist/sleep state 与归一化夹爪状态。
- 输出 translation、rotation、twist、support、progress、slip、drop、contact retention；分别计算 Shapley、support、progress、harmful、slip、joint synergy，并保留三通道 rho_L / rho_R / rho_joint。
- 新增独立 intervention-validity gate：只有 nominal left/right profile 真正对物体产生正向且占优的 task-direction motion 时，才允许统计 oracle direction accuracy。

## 4. 六轮有界 pilot 谱系

1. **pilot-v1：**初始 integration，50/50 paired comparisons 全部 tie，定位到 neutral-action 错误。
2. **pilot-v2-neutral-qpos：**neutral 改为 measured qpos；仅 1/230 comparison informative。
3. **pilot-v3-horizon-sensitivity：**测试 H=5/10/25/50；459/460 ties，延长 horizon 未修复干预失效。
4. **pilot-v4-direction-null：**加入 4 mm Jacobian direction/null action；FK direction cosine 约 0.99998 以上，但 0/10 valid object-authority swaps。
5. **pilot-v5-compliance-assisted：**加入非主导臂 0.05 compliance；单一 transition state 得到 2/10 valid pairs，oracle 2/2。
6. **pilot-v6-dense-transition：**每 25 physics steps 稠密采样 transition window，得到本轮最终有界结果。

## 5. 最终 pilot-v6 定量结果

- 1 个成功 expert episode，46 个物理状态，H=5 与 H=10，共 460 条 branch records。
- 普通 direction/null：0/92 valid paired object-authority swaps，因此 ordinary profile 的 oracle accuracy 不可解释。
- 诊断性 direction/null + 0.05 non-dominant compliance：21/92 valid pairs，来自 12 个唯一 physics steps，范围 3850–4150，跨越 donor release E4=4083 的邻域。
- 在这 21 个经独立 validity gate 确认的 pair 上，oracle informative count=21，方向准确率 21/21=1.0。
- 该 21/21 全部来自一个 episode、一个窄 transition window，且依赖强 compliance confound；不能外推为正式机制效应。

## 6. 科学判定与证据边界

**判定：**PILOT_LOCALIZED_SIGNAL_FORMAL_PENDING；formal_signal_classification=null。

- 这不是 SIGNAL_STRONG、SIGNAL_PARTIAL、SIGNAL_NEEDS_THREE_WAY 或 SIGNAL_WEAK；正式标签因样本量和 controls 不足而不分配。
- 正式进度：handover_block signal 1/30；perturbed 0/20；lift_pot 0/20；pick_dual_bottles 0/20；handover_mic 0/20–30。
- 尚未验证 lift_pot joint synergy、pick_dual_bottles router specificity、handover_mic cross-geometry transfer，也没有跨 episode 估计 mismatch 对 jerk/slip/drop 的预测。
- Oracle 使用 simulator snapshot、privileged contact 和 object state，当前不可部署。
- 没有测试责任守恒 operator、learned closed loop 或 real robot。

## 7. ACT / PAI 决策

- ACT training 与 inference 均未启动；没有 PAI CreateJob，JobId=null。
- 科学原因：真实 Stage 2A 目前只有 one-episode bounded pilot，尚未达到进入 learned-policy 验证的 gate。
- 基础设施原因：预检发现共享 PAI registry 为 dirty，live idle-helper SHA256 与当前 skill contract 不一致，因此在 CreateJob 前 fail closed。该问题与局部科学信号相互独立，不能解释为机制负结果。

## 8. 测试与制品审计

- dev14 全仓测试：22 passed；其中 Stage 2：19 passed。
- 84 个 JSON 全部解析；14 个 JSONL 共 6,896 行全部解析。
- 20 个 Parquet 共 96,049 行、3,553,813 个数值标量全部 finite。
- 20 个 MP4 共 3,951 帧与 26 个 PNG 均可解码。
- 疑似密钥高置信扫描 0 findings；symlink 0；最大文件 16,379,165 bytes；SHA256 manifest 共 236 entries 并通过 readback。

## 9. GitHub 归档与复核

代码、配置、单元测试、完整 smoke/pilot traces、JSONL、Parquet、视频、图、runtime logs、失败谱系、报告与 SHA256 清单均已推送到 GitHub main。

- [GitHub 仓库](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering)
- [本轮提交 df38f8a](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/commit/df38f8aa8a74fb511d3789e5bd1b995ffd70c43b)
- [详细 signal pilot 报告](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/reports/SIGNAL_PILOT_REPORT.md)
- [详细 smoke 报告](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/reports/SMOKE_REPORT.md)
- [机器判定 JSON](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/reports/CURRENT_DECISION.json)
- [测试与制品审计](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/reports/STAGE2_TEST_RESULTS.md)
- [全部 Stage 2 原始结果](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/tree/main/stage2_robotwin/results)

通过 dev14 SSH 从 GitHub main 重新 fresh-clone 后复核：HEAD=df38f8aa8a74fb511d3789e5bd1b995ffd70c43b；236/236 SHA256 entries 通过；22/22 tests 通过；git status clean。

## 10. 下一步建议

1. 冻结一种 contact-aware、但不依赖极端 0.05 compliance 的 ordinary intervention。
2. 先在相对 E4 的 3850–4150 类型窗口做 3–5 seeds 小规模复验，要求 ordinary profile 跨 seed 产生有效 object-authority swap。
3. 若此 gate 通过，再执行完整 30 successful + 20 perturbed handover_block 与三个 control/secondary tasks。
4. 只有正式 Stage 2A signal gate 通过后，才进入 operator 消融与 ACT/PAI 训练推理。
