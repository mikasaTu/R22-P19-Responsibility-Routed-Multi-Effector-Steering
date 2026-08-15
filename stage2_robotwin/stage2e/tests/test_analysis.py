from stage2_robotwin.stage2e.scripts.analyze_withdrawal import analyze


def test_analysis_requires_all_three_episodes_and_preserved_other_channels():
    rows = []
    for seed in (0, 1, 2):
        for channel in ("motion", "support", "rotation", "retention"):
            for fade in (1.0, 0.75, 0.5, 0.25, 0.0):
                for repeat in (0, 1):
                    effects = {name: 1.0 for name in ("motion", "support", "rotation", "retention")}
                    effects[channel] = fade
                    rows.append({"seed": seed, "channel": channel, "fade": fade,
                                 "repeat": repeat, "donor_effect_integrals": effects,
                                 "receiver_command_sha256": f"seed-{seed}",
                                 "donor_contact_fraction": fade if channel == "retention" else 1.0,
                                 "donor_final_contact": not (channel == "retention" and fade == 0.0)})
    result = analyze(rows)
    assert result["decision"] == "WITHDRAWAL_GO"
    rows.pop()
    assert analyze(rows)["decision"] == "WITHDRAWAL_NOT_IMPLEMENTABLE"
