---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/QtmtwRJiki7DAqkWGA5cvhdInWf
wiki_node_token: QtmtwRJiki7DAqkWGA5cvhdInWf
document_token: MJkidLxlqo2w8Xx2R8ncKIpXnOe
revision_id: 4
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: a32c3707e840840cc331361ca4afddca6159fe46328e0040395d7c411fb6be1e
---

<title>实验报告</title>

# R22-P19 Step4 / Stage 2C 实验报告

**日期：**2026-08-14

**任务：**RoboTwin handover_block 双臂交接

**最终判定：**RESPONSIBILITY_MECHANISM_NOT_SUPPORTED

**验收与后续：**accepted=false；ACT gate=BLOCK；PAI jobs=0

**证据边界：**本报告只覆盖 RoboTwin handover_block 的 privileged simulator oracle 机制验证；不代表 learned responsibility estimator、ACT/VLA 兼容性、可部署闭环、其他任务或真实机器人。

## 0. 执行摘要

- **完整执行：**按用户“即使 gate 未通过也必须完成全部实验”的显式 override，完成 fresh-prefix noise、natural responsibility、eta calibration、local operator、24-candidate stress calibration，以及 8 seeds × 4 conditions × 14 methods 的 448/448 closed-loop 单元。negative gate 与 ineligible lineage 均保留。
- **Replay 修复有效：**100/100 个独立进程 exact-null 单元的六项 median/P95/max floor 全为 0；Stage 2B 的非零 floor 来自同一 scene 的 snapshot restore 无法恢复 PhysX warm-start cache。
- **Natural signal 未成立：**hidden-authority 预期方向 accuracy=0.316667，95% CI [0.241667, 0.400000]；反向 accuracy=0.683333，判定 RESPONSIBILITY_UNSTABLE。
- **Operator 可改动作但不 causal：**local median correction ratio=0.173306，active rate=0.85，预测守恒与安全约束通过；但 correct target movement=0、swapped movement=0、conservation-only specificity 失败，判定 RESPONSIBILITY_NOT_CAUSAL。
- **闭环 specificity 失败：**C13 按预注册规则改善 0/3 stress；正确责任优于 swapped/shuffled 为 0/3；full 优于 conservation-only 为 0/3；最终为 RESPONSIBILITY_MECHANISM_NOT_SUPPORTED。
- **训练边界：**冻结计划禁止 ACT、responsibility estimator、pi0.5 与 PAI job，因此本阶段只在 dev14 A800 上执行 bounded simulator oracle 实验，未提交任何 PAI 作业。

## 1. 冻结合同、运行环境与产物

- held-out seeds：2、3、5、6、7、8、9、10；calibration seeds：0、1。
- RoboTwin commit：266f3aadf505a4f7fe9af0faa41a20f5f47cd123。
- XPolicyLab gitlink：c37109c500be67d0dea6b36bf7337bbd26e763cd。
- Python 3.10.19；SAPIEN 3.0.0b1；MPLib 0.2.1；NumPy 1.26.4；SciPy 1.10.1；PyYAML 6.0.3。
- 执行机：dev14；NVIDIA A800-SXM4-80GB；driver 580.95.05；正式 GPU indices 0、1、2、3。
- 正式 config SHA-256：c530b6435ef3e108efe00cefb7c892abf0046c7bdca16621eb2e191de0b7b10d；frozen stress SHA-256：6d6297e94ca80fe6be7d7414465104582ff11ffd3d4bef4890b6f670a8a6b953。
- episode 是唯一推断单位；paired bootstrap 10,000 次，seed 22019；branch points 不作为独立 n。
- 正式 CPFS 根：/mnt/cpfs/zbl-cpfs-new/USERS/leon/logs/R22-P19/stage2c；完整子目录记录在 Git 的 results/PROVENANCE.json。
- Git 只保存约 6.3 MB 的代码、配置、紧凑 JSON、报告和测试；raw tapes、448 cell 目录、NPZ traces、runtime logs、环境、数据、权重和凭据不进入 Git。

[GitHub 仓库](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering)；[main commit e31e1dd](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/commit/e31e1ddc78e8ffa22c5dba51d2988151ec7f755f)；[完整 Step4 Markdown 报告](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2c/reports/STEP4_EXPERIMENT_REPORT.md)；[机器可读最终判定](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2c/reports/CURRENT_STAGE2C_DECISION.json)。

## 2. Stage 2C-0：Fresh-Prefix Replay Noise Audit

### DONE

完成 100/100 独立进程单元：5 seeds × clean/receiver_gain_0p7 × B0/operator-null × 5 replicas。每个单元从 episode 起点重放同一 expert tape，到 E2 后进入方法段；oracle branch 使用独立 SAPIEN scene，主 scene 不接受 branch state restore。

### KEY RESULT

六项 exact-null floor 的 median/P95/max 全为 0：within-method 每项 200 个 paired differences，B0-vs-operator-null 每项 50 个 paired differences。fresh-prefix substrate 判定 USABLE，后续 3×P95 gate 为 0。

- peak angular velocity：旧 P95 1.215343；新 P95 0。
- peak linear jerk：旧 P95 5.766071；新 P95 0。
- contact-masked slip：旧 P95 0.001290693 m；新 P95 0。
- min object height：旧 P95 0.000183657 m；新 P95 0。

### LIMITATION

零 floor 只证明完全相同动作的 replay substrate 可复现，不证明 responsibility signal 或 operator。

### NEXT

用每项 3×P95 null floor 审计 local 与 closed-loop 的真实方法效应。

## 3. Stage 2C-1：Natural Responsibility / Hidden Authority

### DONE

完成 90/90 profile 单元。每 seed 包含 NATURAL 与 gamma=0.8/0.6/0.4/0.2 的左右 hidden-authority 配对；profile assignment 前的起点、E2 prefix 与 high-level expert tape 相同。按冻结规则选择非极端 gamma=0.8。

### KEY RESULT

判定 RESPONSIBILITY_UNSTABLE。

- held-out 预期方向 accuracy=0.316667，95% CI [0.241667, 0.400000]。
- 反向方向 accuracy=0.683333，95% CI [0.600000, 0.758333]。
- valid-pair rate=0.882353；H5/H10/H20 sign consistency=0.671875。
- adjacent share delta median/P95=0.062234/0.941307。
- swapped accuracy=0.683333；episode shuffle=0.384042；time shift=0.441176。
- risk correlation：angular 0.102806；jerk -0.188305；slip -0.184652；release-contact risk 0。
- baselines：action magnitude 0.033333；contact impulse 0.483333；inverse distance 0.483333；phase 0；fixed 50/50 0。

### LIMITATION

SoftExpertAuthorityProfile 不是把 soft arm 的命令乘以 gamma，而是在 e_parallel 上插值 expert target 与 object-follower target。直接 audit 中，绝对平行动作真正变小的比例为 0.617647，follower 幅值大于 expert 的比例为 0.485294，符号保持率 0.941176。因此反向 contrast 来自 follower 几何与 expert command 的相对关系，不是简单标签写反，也不能作为自然 responsibility 正证据。

### NEXT

只把该信号当作 privileged diagnostic，继续依赖 local causal transfer 与 wrong-responsibility controls 做 falsification。

## 4. Stage 2C-2：Eta Calibration 与 Local Operator Gate

### DONE

在 seeds 0、1 的 clean/hidden profiles 上完成 eta=0.25/0.5/0.75/1.0 的 4/4 calibration 单元；按“5%–20% correction 中最接近 12.5%，tie 取较小 eta”冻结 eta=0.25。随后完成 5 seeds × clean/hidden 的 10/10 local-gate 单元，共 1,800 method-state-horizon rows。

### KEY RESULT

判定 RESPONSIBILITY_NOT_CAUSAL。

- median correction ratio=0.173306；active states 超过 5% correction 的比例=0.85；两项通过。
- predicted effect error P95 约 2.6e-16；realized total-effect deviation 低于 0.1% 量级；守恒通过。
- correct responsibility target movement median=0，未达到 0.15；swapped movement=0，未反向；conservation-only specificity 未通过。
- correct operator 的 200 个主审计 rows：NULLSPACE_APPLIED 54、NULLSPACE_CLIPPED 126、DEGENERATE_GAIN_BASE_FALLBACK 20。
- angular delta median=0.000738；slip delta median=4.668e-7，虽超过 exact-zero floor，但不对应正确的 realized contribution transfer。

### LIMITATION

新算子沿 [b_R,-b_L] 的精确 effect nullspace 移动，并用 relative trust region 限幅，已摆脱 Stage 2B 固定 ridge 导致的 near-null；但“动作能改、总 effect 守恒”不等于“正确 responsibility 可因果控制 realized contribution”。因为 1D responsibility transfer 失败，conditional 4D physics gate 未触发；4D 实现与单测保留，但代码存在不被称为实验结果。

### NEXT

根据用户 override 继续完成 stress 与 closed-loop，同时保留该 negative gate。

## 5. Stage 2C-3：Stress Calibration

### DONE

完成 96/96 calibration 单元：24 个候选（clean + 23 non-clean）× seeds 0、1 × C0/C13。全部预注册单因素与少量两因素候选均实际执行。donor_release_advance 按 250 Hz physics/tape step 计，每步 4 ms。

### KEY RESULT

判定 DIAGNOSTIC_STRESSES_FROZEN_WITH_ELIGIBILITY_FAILURE。没有候选满足 base success 30%–80%，也没有同时满足 disturbance 至少 2× clean 且存在可改善空间。为执行完整下游矩阵，冻结以下 ineligible diagnostic fallback：

- S1 hidden mismatch：gamma=0.8；base success=1.0；max disturbance/clean=1.551777；improvable=no；eligible=no。
- S2 premature release：advance 10 steps=40 ms；base success=1.0；max ratio=1.422416；improvable=yes；eligible=no。
- S3 contact quality：receiver friction ×0.5；base success=1.0；max ratio=1.530215；improvable=yes；eligible=no。

### LIMITATION

三项 stress 都未打开预注册失败空间，因此闭环矩阵只能是 diagnostic falsification，不能冒充 qualified stress benchmark。

### NEXT

保持冻结值不变，在 8 held-out episodes 上执行 14-method fresh-prefix 矩阵。

## 6. Stage 2C-4：448-cell Fresh-Prefix Closed Loop

### DONE

完成 448/448：8 seeds × clean/S1/S2/S3 × C0–C13。448 个 result 唯一、missing=0、extra=0、非有限值=0；32 个 seed-condition 组内 prefix hash 全同；oracle budget 全等；C0 budget=0。416 个 oracle 单元均使用独立 sandbox scene；32 个 C0 无 oracle。C0 与 C11 对所有报告指标逐 episode 精确相等。

4 个四 worker contention 期间的 C6/S1 BrokenPipeError 失败产物被保留；seeds 2、3、5、6 均通过 fresh-process 重跑恢复，recovered=4，unrecovered=0。

### KEY RESULT

所有 seed、condition、method 的 success 与 handover completion 均为 1.0；drop、premature release、receiver takeover failure 均为 0，存在明确 success ceiling。

- clean：C0/C13 angular 2.411924/2.524117；jerk 169.987089/169.766140；slip 0.0878581/0.0878243；C13 不优于 C0。
- S1：C0/C13 angular 2.536190/3.226541；jerk 168.609793/185.061146；slip 0.0879483/0.0915880；三项 mean benefit 都为负。
- S2：angular benefit=+0.279047，95% CI [0.068100, 0.557954]；但 jerk benefit=-0.264761，95% CI [-0.584538, -0.031000]，slip 未改善，是稳定性 trade-off。
- S3：angular/jerk/slip benefit=-0.004269/-0.066309/-0.000196，均未形成合格改善。
- clean 只有 slip 单指标 benefit=+3.3737e-5，95% CI [5.7067e-6, 6.6851e-5]；angular 方向不利，整体 rule 不通过。

**Mechanism controls：**C6 correct 优于 C8 swapped=0/3；C6 correct 优于 C9 shuffled=0/3；C7 stateful 优于 C10 time-shifted=0/3；C13 full 优于 C4 conservation-only=0/3；C13 优于 C0=0/3。effect 超过 null floor 的 stress=1/3，要求至少 2/3。

**Operator audit：**C13 的 1,532 refresh 中，DEGENERATE_GAIN_BASE_FALLBACK=941，contact-retention + degenerate fallback=75，NULLSPACE_APPLIED=186，NULLSPACE_CLIPPED=330。全矩阵 episode-median correction 的中位数为 0，平均 active >5% rate=0.312573；release guard 在 13,440 donor-open request steps 中阻断 698 次。

**Cost：**159,328 oracle branches；796,640 simulated oracle physics steps；累计 replay wall time 34,913.07 s；estimator time 517.00 s；solver time 239.53 s。

### LIMITATION

stress 全部 ineligible，8 个 episode 的 task 指标封顶；因此这里只能判定正确责任与 wrong/shuffled controls 无 specificity。refresh、oracle branch 与 local states 不是独立统计样本。

### NEXT

ACT、responsibility estimator、Diffusion Policy、pi0.5/TwinVLA 与额外 RoboTwin tasks 全部保持 BLOCK。本报告不生成新 idea，也不通过单指标变化继续升级证据。

## 7. 代码机理反解：为什么提升或下降

### 7.1 Replay floor 为什么归零

Stage 2B 在同一长期 scene 中 restore 显式 rigid/articulation state，但 SAPIEN 不暴露 PhysX warm-start cache；oracle branch 会改变主 scene 的隐含 solver history。Stage 2C 把显式状态单向复制到第二个 SAPIEN scene，所有 branch 在 sandbox 运行，从不 restore 回主 scene，因此相同动作不再被 branch 污染。

### 7.2 旧 ridge 为什么 near-null，新算子为什么 effectful 但不 causal

旧 KKT objective 的固定 ridge_lambda=0.05 作用于 action deviation，而 contribution residual 的尺度由很小的 physical gain 决定；绝对正则项支配目标，解贴近 base。新算子沿 [b_R,-b_L] 的精确零空间移动，并使用相对 trust region，不再用绝对 ridge 压死 correction，所以出现 17% 量级 local 修正。可是 correct、swapped、conservation-only 的 realized target movement 都为 0，说明当前 gain × parallel action 的 1D proxy 没有提供可由该动作方向因果控制的 responsibility 目标。

### 7.3 Direct scale、guard 与 full method 的 trade-off

- C5 direct scale 的全矩阵 median correction=0.881341，不守恒总 task effect。S3 angular 明显降低：benefit +0.384440，95% CI [0.048332, 0.767212]；同时 jerk 与 slip 明显恶化。这是总命令幅值变化的 trade-off，不是 responsibility-preserving transfer。
- C12 guard-only 在 S1 的 jerk benefit=+4.069510，95% CI [0.001438, 12.166032]，同时 angular/slip 方向不利，说明 guard 本身足以改变轨迹稳定性。
- C13 在 S2 改善 angular 却恶化 jerk；正确、swapped、shuffled、time-shifted controls 都无 specificity。该变化可由 generic conservation、degenerate fallback、trust clipping 与 guard 的轨迹扰动解释，不能归因于正确 responsibility direction。
- C13 release guard 阻断率约 5.19%，而 C12 为 10.54%；trajectory 分歧会反过来改变 guard request，不能只用 block count 把差异归入 responsibility routing。

## 8. 测试、发布与回读证据

- Stage 2C unit/regression：15 passed；最终 combined Stage2/2B/2C：52 passed in 11.01s。
- 33 个 Python source in-memory compile 通过；18 个 compact JSON 全部 parse；448/448 finite decision audit 通过。
- Git artifact audit：symlink=0；raw/runtime forbidden matches=0；high-confidence secret matches=0；最大文件 1,724,453 bytes。
- GitHub main commit：e31e1ddc78e8ffa22c5dba51d2988151ec7f755f。
- dev14 通过 GitHub SSH 做 depth-1 sparse fresh clone；远端 HEAD=e31e1ddc78e8ffa22c5dba51d2988151ec7f755f；fresh-clone Stage 2C tests=15 passed in 0.96s；worktree status lines=0。

## 9. 最终结论

Step4 已完成计划中的全部可执行实验，而不是在首个 negative gate 停止。三个必要链条同时失败：natural responsibility 不稳定；1D operator 虽数值 effectful 且守恒，却不能因果转移 realized responsibility；closed loop 中 correct 与 wrong/shuffled controls 无区分，full 也不胜 conservation-only，stress improvement=0/3。

**最终机制码：RESPONSIBILITY_MECHANISM_NOT_SUPPORTED。**

**accepted=false；ACT gate=BLOCK；PAI jobs=0。**

该结论准确含义是“当前实现与 RoboTwin handover_block 当前证据不支持责任路由机制”，不是证明所有 responsibility modeling 永远无效，也不产生新的 research idea。
