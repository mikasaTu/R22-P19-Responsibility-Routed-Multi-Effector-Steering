---
feishu_url: https://icnbwz7kd1ui.feishu.cn/wiki/WGOswYNN1ik5tlko5qfcvrWMncc
wiki_node_token: WGOswYNN1ik5tlko5qfcvrWMncc
document_token: EhZydbZvQoVnmXxbkQTcx2R0nuh
revision_id: 3
exported_at_utc: 2026-08-17T11:54:20+00:00
source_content_sha256: 209fe10625870d3b0be9ef2a165278060556edb61ecc5ac73d7e4d79a81372a4
---

# 实验报告

## DONE

- 冻结前序基线：`05600234df39367424fcb8036533b5e111d2a0aa`。
- 按 Step6 当前立即执行范围完成：A）Hypothesis–Code Conformance Gate；B）真实 motion/support/rotation/retention withdrawal；C）逐分支 fresh-scene 顺序与 null 审计；D）3 episode withdrawal monotonicity。
- 物理矩阵共 `3 seeds × 4 channels × 5 fade levels × 2 repeats = 120 cells`，结果为 `120/120 COMPLETE, 0 FAILED`。每个 cell 都使用独立进程、全新 RoboTwin 场景、从 episode 起点重放，未使用 snapshot restore；启动顺序随机化。
- dev14 实际仅使用 `CUDA_VISIBLE_DEVICES=2`，最多 2 个并发 worker。未创建 PAI job，未进行 VLA/ACT/pi0.5 训练或推理，也未实现 capacity classifier、allocator、learned estimator 或 closed-loop policy。
- 全仓 Stage-2/2B/2C/2D/2E 回归：`64 passed, 2 warnings`；warning 均来自既有 Stage2D SciPy bound clipping。
- 代码、预注册、120 份 compact raw JSON、机器决策、报告和 SHA256 清单已通过 dev14 SSH 推送至 GitHub `main`：commit [`f2c58d2888d3c0772644b808caba086f323a8577`](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/commit/f2c58d2888d3c0772644b808caba086f323a8577)。

## WHAT CODE ACTUALLY EXECUTED

### Conformance audit

实际执行的 method registry 与 runtime receipt 会记录 method name、真实 code path、是否修改 action、solver 调用次数、receiver command hash。审核结果为 `CONFORMANCE_NO_GO`，8 项中失败 5 项：

1. local 与 closed-loop 未调用同一个真实 4D allocator；
2. conservation-only 未实现为同一 allocator 的 `lambda_target=0`；
3. internal 方法未执行非零真实 wrench objective；
4. 未把真实 Stage2C V1 path 接入本次比较；
5. full mechanism 中不存在 release-only continuous arm-unchanged path。

通过的 3 项是 operator-null 无 action 修改、withdrawal receipt 与声明一致、method name 与真实 code path 一致。以上缺失路径没有被 mock，因为冻结计划在当前 withdrawal validity 之前明确禁止实现 allocator/state-machine/closed-loop。按照“不能因 gate 不到停止其他实验”的要求，后续 withdrawal 仍全部跑完，但只标记为 `DIAGNOSTIC_AFTER_CONFORMANCE_NO_GO`，不能反向覆盖 gate。

### 三类 arm-channel withdrawal

RoboTwin/SAPIEN 只暴露 diagonal joint-drive impedance，没有 Cartesian-axis impedance。本次实际执行的是计划允许的 object-following fallback：

1. 用 live Jacobian 把 expert donor joint-position error 投影为 task-space twist；
2. 分别选取 object motion axis translation、vertical translation、vertical-axis rotation；
3. 只把被选分量乘以 fade；
4. 用 Jacobian pseudoinverse 把剩余 twist 映射回 donor joint target；
5. receiver command 保持不变。

### retention withdrawal 与测量

Retention 使用 RoboTwin 真实 gripper open target，将 donor closure 连续插值到张开命令。每一步从 SAPIEN live contacts 读取每只手对物体的 impulse 与关于物体 COM 的 torque，再投影为 motion/support/rotation/retention 四个物理 effect proxy。

## KEY RESULT

总决策：**`STAGE2E_DIRECTION_STOPPED`**，`accepted=false`。

- Conformance：`CONFORMANCE_NO_GO`。
- Withdrawal：`WITHDRAWAL_NOT_IMPLEMENTABLE`。
- 12 个完整 seed×channel group 中 `0/12` 满足全部预注册 gate。

| Channel | fade=0 effect 中位数 | fade=1 effect 中位数 | 各 seed 的 fade0/fade1 | 关键失败项 |
|-|-|-|-|-|
| motion | 0.025546 | 0.025551 | 1.0003 / 1.0001 / 0.9998 | 目标 effect 未降至 ≤10% |
| support | 0.018136 | 0.018137 | 1.0000 / 0.9995 / 1.0001 | 目标 effect 未降至 ≤10% |
| rotation | 0.008412 | 0.008407 | 1.0006 / 1.0000 / 1.0021 | 目标 effect 未降至 ≤10% |
| retention | 0.002458 | 0.037034 | 0.0651 / 0.0664 / 0.0653 | 非目标通道保持与 contact-duration 失败 |

三类 arm target 修改确实发生，并随 fade 连续减小：fade=0 的 donor joint-target modification 中位数分别为 motion `0.006887 rad`、support `0.006105 rad`、rotation `0.014759 rad`；fade=1 数值为 0。但 donor 在全部 60 步持续接触，实际对应 contact effect 仍约为 baseline 的 100%。

Retention 张爪把 selected impulse-norm 降到 baseline 的约 6.5%，所有 fade=0 repeat 的最终 donor contact 都为 false；但 donor 在 60 步中的 contact fraction 仍为 `0.6333`，没有达到 ≤0.10。同时 motion/support 也只剩约 6.3–6.5%，rotation 只剩 6.5–11.1%，没有达到非目标通道 ≥80% 的选择性要求。

隔离控制全部通过：每个 seed×channel group 在全部 fade/repeat 下只有一个 receiver-command SHA-256；所有 duplicate relative error 都为 0；每个 fade 均有两个 fresh repeats。因此负结果不能用 receiver command 漂移、随机启动顺序或重复噪声解释。

## 机理反解（code-first，不生成新 idea）

### 为什么 arm command 有变化，但物理 effect 不降低

- 代码撤掉的是由当前 pose error 推断的单步 desired twist 分量，不是 achieved contact wrench 或 Cartesian impedance。
- 映射后的 joint target 仍由同一套高增益 diagonal joint drives 执行。
- gripper 始终闭合，donor contact fraction 为 1.0；closed-chain 接触约束与 receiver arm 可以在物理接触中补偿被撤掉的运动学分量。
- Jacobian pseudoinverse 在自由空间近似保持未选 twist，但这些 joint motions 在接触动力学中并不正交。

因此“command modification 随 fade 平滑变化”只证明适配器代数生效，不能证明 channel-specific physical responsibility。

### 为什么 retention 显著降低，但同时带来其他通道下降

Retention 直接张开 donor gripper，削弱法向/摩擦接触，因而 impulse norm 明显降低。这是物理上真实的下降。但 motion、support、rotation 都通过同一个 gripper-object contact manifold 传递；一旦破坏抓持，四个通道会一起消失。它实际是 whole-contact ablation，而不是 selective retention withdrawal。增量张爪还需要若干 simulation steps 才分离，所以最终无接触不等于 contact-duration ≤10%。

## WHAT WAS FALSIFIED

1. live-Jacobian target-projection fallback 在当前接触 regime 中不是有效的物理 channel-specific withdrawal operator。
2. 真实张爪是因果有效的，但无法单独撤掉 retention；它会同时撤掉几乎全部 donor wrench 通道。
3. 当前 RoboTwin 实现不能把 motion/support/rotation/retention 当作可独立操纵的 responsibility coordinates。
4. 本次物理诊断不包含 capacity-aware desired responsibility、common allocator 或 closed loop，不能被写成 V2 routing 的正证据，也不能覆盖 `CONFORMANCE_NO_GO`。

## LIMITATION

- 这是 `handover_block` 上 3 episode、每分支 60 步的 privileged-simulator 诊断，不是 policy benchmark、deployable controller 或 real-robot 结果。
- contact impulse 是 simulator per-step impulse，不是校准硬件力/力矩，绝对量不能外推到真实机器人。
- arm fallback 撤的是 commanded pose-error component，不是真实 Cartesian impedance/achieved wrench。
- duplicate error 为 0 来自 deterministic replay，只说明本次隔离重复稳定，不证明随机动力学鲁棒性。
- 可选 cuRobo/pytorch3d import 不可用；实际按合同使用 `mplib_screw`，120 个 cell 全部完成。

## NEXT

按冻结决策规则，本方向在此停止：不继续实现 capacity classifier、allocator、learned estimator、ACT pilot、PAI training 或 closed-loop claim。若未来继续，必须作为另行授权、重新预注册的新机制验证，不能把本次诊断重新解释为原 V2 的支持证据。

## 可审计产物

- [Withdrawal validity report](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2e/reports/WITHDRAWAL_VALIDITY_REPORT.md)
- [Mechanism reverse explanation](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2e/reports/MECHANISM_REVERSE_EXPLANATION.md)
- [Current machine decision](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2e/reports/CURRENT_STAGE2E_DECISION.json)
- [Raw analysis](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2e/results/withdrawal/analysis.json)
- [Integrity manifest](https://github.com/mikasaTu/R22-P19-Responsibility-Routed-Multi-Effector-Steering/blob/main/stage2_robotwin/stage2e/SHA256SUMS)
