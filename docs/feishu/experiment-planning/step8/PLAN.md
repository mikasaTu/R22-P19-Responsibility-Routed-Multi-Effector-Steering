---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/UMTAwkrwsihre2k6ppjc4CXInOg
wiki_node_token: UMTAwkrwsihre2k6ppjc4CXInOg
document_token: RQ8MdECkLoFiY7xCkrlcjLIgnrg
revision_id: 2
exported_at_utc: 2026-09-02T13:58:43+00:00
source_content_sha256: fa7db89e84b50b5ffc21cb7d15de53c7c3e6a83057433e560e30d2924017d655
---

<title>step8</title>

# 角色与任务

你在 dev14 上继续 R22-P19（repo: mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering, main）。  
当前顶层状态是 STAGE2E_DIRECTION_STOPPED。本次不是重跑旧 stage，而是执行修复路线第一步：  
Stage 2F / Step7 —— Physical Authority Knob Feasibility。只在 calibration seeds 上做。

# 必读（先读完再动手）

- stage2_robotwin/stage2c/intervention/soft_expert_authority.py
- stage2_robotwin/stage2c/reports/STEP4_EXPERIMENT_REPORT.md（Stage 2C-1 与其 LIMITATION 段）
- stage2_robotwin/stage2b/reports/SIGNAL_REPLICATION_REPORT.md
- stage2_robotwin/stage2e/reports/WITHDRAWAL_VALIDITY_REPORT.md 与 MECHANISM_REVERSE_EXPLANATION.md
- stage2_robotwin/responsibility/oracle_brancher.py 中的 AuthorityProfile 与 authority_override
- stage2_robotwin/stage2d/scripts/run_capacity_audit.py 中的 \_active_item
- stage2_robotwin/stage2c/configs/stage2c_formal_eta0p25.yaml

# 已确定的前提（不需要你重新论证，也不许推翻）

1. SoftExpertAuthorityProfile.blend 做的是 gamma\*expert_parallel + (1-gamma)\*follower_parallel，  
即在 e_parallel 上插值 expert target 与 object-follower target，不是把 soft arm 的权威按 gamma 缩放。  
直接 audit：绝对平行动作真正变小的比例 0.617647，follower 绝对幅值大于 expert 的比例 0.485294。  
因此 Stage 2C-1 的 hidden-authority accuracy 0.316667 / 反向 0.683333 是干预算子构造错误的产物，  
不能当作"自然责任方向不可辨识"的结论。
2. Stage 2E 证明：闭合抓取下只改 joint target，命令改动真实而物理接触效应不变  
（motion/support/rotation 的 fade0/fade1 = 0.9995\~1.0021）。所以本步验收不得只看 command 层。
3. 原 handover 重叠段 moving fraction 17.5%、速度 1.44 mm/s；Stage 2D 的 15 mm 正弦 active reference  
已修到 81.24% / 5.77 mm/s / dual contact 95.25% / 10-10 成功。本步一律用 active reference 版本。
4. 不换 substrate。任务仍是 RoboTwin handover_block，planner mplib_screw，physics 250 Hz。

# 本步判定的唯一命题

在 pinned RoboTwin/SAPIEN 上，是否存在一个标量 gamma∈[0,1] 的 actuator 级 authority knob，  
使 soft arm 对物体的**物理**作用随 gamma 单调变化，且不是靠破坏抓取实现，且保留任务成功。

# 要实现的东西

新建 stage2_robotwin/stage2f/{preregistration,intervention,configs,scripts,tests,reports,results}/。  
实现三个 knob，统一接口 apply(task, soft_arm, gamma)，语义固定为 gamma=1 名义权威、gamma→0 权威消失：

- K1 drive_compliance：复用 authority_override / AuthorityProfile(<side>\_compliance=gamma)，  
按 gamma 缩放 soft arm 手臂关节 stiffness+damping；force_limit、drive mode、gripper 关节一律不动。
- K2 force_limit：只按 gamma 缩放 soft arm 手臂关节 force_limit，stiffness/damping 不动。
- K3 target_interpolation：直接调用现有 SoftExpertAuthorityProfile 作缺陷基线对照，不修改其源文件。  
硬性：knob 必须覆盖该 branch 的整个 rollout 并在 finally 复原；drive property 不在 SapienSnapshot 里，  
不要指望 restore 还原。receiver（非 soft）臂的 command 必须逐字节不变并写进 receipt。

# 实验矩阵（本步全部内容）

- active reference：与 \_active_item 同款，amplitude 0.015 m，作用区间 E3–E5，双臂共模；knob 叠加在其上
- seeds：calibration 0,1。held-out 2,3,5,6,7,8,9,10 本步禁止使用
- gamma grid：1.0, 0.8, 0.6, 0.4, 0.2, 0.05
- knobs：K1,K2,K3 ；soft_arm：left 与 right 各一遍 ；repeats：2
- 采样窗：[max(E3, E4-250), min(E5, E4+150)]，stride 25。先报告每 seed 可用步数，<8 则停下报告
- 每个 state 跑 LR/L/R/ZERO 四分支，沿用 NaturalResponsibilityEstimator，horizons 5/10/20
- null floor：gamma=1.0 且 knob 不生效的 5 次独立复现，用于算 P95 spread
- 共 2×3×2×6×2 = 144 个 cell 加 10 个 null。单张 A800，fresh process per cell，随机启动顺序，  
不向主场景 restore snapshot

# 每个 cell 必须落盘的量

- command 层：expert_parallel_action_m、实际下发 target、|平行动作| 相对同 state gamma=1 的比值
- 物理层（判据在这里）：soft arm contact impulse 在 e_parallel / e_vertical 上的投影、  
soft 与 receiver 的 impulse share、active window 内物体位移与速度、dual-contact fraction、  
donor contact 持续步数
- 反事实层：decompose_outcomes 的 rho_soft / rho_receiver / rho_joint（H=5/10/20）
- 任务层：check_success()、plan_success
- receipt：knob 名、gamma、被修改的关节数与原值、receiver command hash、action modification 计数

# 冻结验收 gate（跑之前写进 preregistration，跑完不许改）

逐 knob 判定：

- G1 物理单调：soft arm 的 e_parallel contact impulse 投影对 gamma 的 Spearman rho >= 0.9，  
每个 seed × soft_arm 组都要满足
- G2 反事实单调：rho_soft 对 gamma 的 Spearman rho >= 0.9（以 H=10 为主，H=5/20 需同号）
- G3 幅度：gamma=0.2 处的 soft impulse 投影 <= gamma=1.0 处的 0.5 倍，  
且该差值 > 3 × P95(null spread)
- G4 非退化：gamma >= 0.2 时 dual-contact fraction >= 0.90、donor contact 不提前终止、  
task success >= 8/10。靠脱手实现的衰减一律判退化
- G5 command 单调（必要非充分，卡片旧判据）：|平行动作| 随 gamma 单调下降的状态比例 > 0.95
- G6 隔离：receiver command 逐字节不变；两次 repeat 的效应逐位一致

决策写入 results/AUTHORITY_KNOB_DECISION.json：

- 有 knob 过 G1–G6 → AUTHORITY_KNOB_SUPPORTED，并按"过 G1–G6 的最大非极端 gamma"冻结一个值到  
configs/frozen_stage2f_knob.yaml，供 Step8 使用
- 有 knob 过 G1/G2/G5 但 G4 失败 → AUTHORITY_KNOB_DEGENERATE
- 全不过 → AUTHORITY_KNOB_NOT_IMPLEMENTABLE，直接停线，不要提议换任务、换机器人、换 benchmark

# 禁止

不创建 PAI job、不训练、不跑 ACT / pi0.5 / 任何 learned estimator、不跑 closed-loop、  
不动 held-out seeds、不覆盖 stage2b/2c/2d/2e 的任何既有 results 根、不修改 SoftExpertAuthorityProfile  
源文件、不改 substrate。所有产物 accepted=false、pai_job_created=false。

# 交付与 checkpoint（硬性，中间必须停）

交付 1（现在做）：

1. stage2f/preregistration/EXPERIMENT_CONTRACT.yaml，schema 仿 stage2e 那份，含上面全部 gate 数值、  
seed 契约、矩阵规模、决策标签
2. 三个 knob 实现 + stage2f/tests/ 单测：gamma=1 与无 knob 基线逐位一致；异常路径下 drive property  
仍被复原；receiver command 不变；Spearman 与 gate 判定函数在合成数据上的行为
3. 2 个 cell 的 smoke（seed 0，K1，gamma=1.0 与 0.2，soft_arm=left），报告可用采样步数、  
单 cell 墙钟时间、144 cell 的预估总时长
4. 停下，输出 stage2f/reports/STEP7_PREFLIGHT.md，等我确认后再继续  
交付 2（我确认后才做）：跑满 144+10 个 cell，产出 stage2f/reports/STEP7_EXPERIMENT_REPORT.md  
（DONE / KEY RESULT / WHAT WAS FALSIFIED / LIMITATION / NEXT 五段，沿用 repo 现有格式）、  
AUTHORITY_KNOB_DECISION.json，更新 SHA256SUMS 与顶层 README 的 current result。

# 报告要求

数值带 95% CI，推断单元是 episode，bootstrap 10000 次、seed 22019。gate 失败照实写，  
不许换算法或换指标去救结果；如果缺陷基线 K3 反而表现最好，也照实写并给出机制解释。
