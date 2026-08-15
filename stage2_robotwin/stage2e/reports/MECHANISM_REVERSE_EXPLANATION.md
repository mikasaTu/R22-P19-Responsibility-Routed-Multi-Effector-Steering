# Mechanism Reverse Explanation

This note applies the code-first audit only to explain the observed gains and losses;
it does not propose a new idea.

## Arm-channel withdrawal: code changed, physical effect did not

The motion/support/rotation modules alter the donor target in joint space after a
single-step live-Jacobian projection. The intervention magnitude behaved correctly:
at fade 0 the median modifications were 0.006887, 0.006105, and 0.014759 rad,
respectively, and each approached zero continuously at fade 1. Runtime receipts also
show 60 action modifications and zero solver calls per branch.

The measured contact effects did not follow those interventions. Every selected
fade-0/fade-1 ratio was between 0.9995 and 1.0021 up to the reported per-seed values.
The code-level explanation is:

- the projection acts on desired instantaneous end-effector twist inferred from pose
  error, not on achieved contact wrench or impedance;
- the mapped joint target is applied through the same high-gain diagonal joint drives;
- the grasp remains closed and donor contact remains present for every step;
- closed-chain contact constraints and the receiver arm can compensate the removed
  kinematic component before it appears as a reduced donor contact impulse;
- the pseudoinverse preserves the remaining twist, but those joint motions are not
  dynamically orthogonal under contact.

Thus the smooth command-space change is real, while the lack of wrench change is also
real. The decrease in command modification with increasing fade validates the adapter's
algebra only; it does not validate channel-specific physical responsibility.

## Retention withdrawal: strong decrease with coupled losses

Retention fade changes a different actuator: it interpolates the donor gripper toward
the simulator's real open command. At fade 0, donor contact ended in all six repeats
and the retention impulse norm fell to 6.5-6.6% of fade-1 baseline. This gain is
explained directly by opening the grasp and reducing normal/frictional contact.

The same contact break also caused the loss: donor motion and support fell to about
6.3-6.5% and rotation to 6.5-11.1%. Those channels are all transmitted through the
same gripper-object contact manifold, so removing retention removes their transmission
path too. Contact remained for 63.3% of the horizon because the incremental opening
command requires multiple simulation steps before separation, even though final
contact was false.

The result is therefore not a selective retention mechanism. It is a physically real
whole-contact ablation.

## Controls and attribution boundary

The receiver hash was invariant within every seed/channel group, two repeats were
bitwise deterministic in the reported effects, and launch order was randomized. The
observed changes can therefore be attributed to the donor intervention in this
deterministic simulator setup. They cannot be attributed to capacity-aware routing,
because no capacity estimate, desired-responsibility state, common allocator, or
closed-loop policy executed.

