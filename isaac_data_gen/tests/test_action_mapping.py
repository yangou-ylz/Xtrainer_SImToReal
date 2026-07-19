from __future__ import annotations

import numpy as np
import pytest

from phys_data_gen.action_mapping import (
    COMMAND14_NAMES,
    LEISAAC16_NAMES,
    check_leisaac16_gripper_symmetry,
    command14_to_leisaac16,
    leisaac16_to_command14,
    make_replay_command14,
)


def test_names_are_stable():
    assert COMMAND14_NAMES[0] == "left_joint1"
    assert COMMAND14_NAMES[6] == "left_gripper"
    assert COMMAND14_NAMES[13] == "right_gripper"
    assert LEISAAC16_NAMES[6] == "J1_7.pos"
    assert LEISAAC16_NAMES[7] == "J1_8.pos"
    assert LEISAAC16_NAMES[14] == "J2_7.pos"
    assert LEISAAC16_NAMES[15] == "J2_8.pos"


def test_command14_to_leisaac16_open_closed_and_order():
    command = np.arange(14, dtype=np.float32) / 10.0
    command[6] = 0.0
    command[13] = 1.0

    mapped = command14_to_leisaac16(command)

    np.testing.assert_allclose(mapped[0:6], command[0:6])
    np.testing.assert_allclose(mapped[8:14], command[7:13])
    assert mapped[6] == pytest.approx(-0.0)
    assert mapped[7] == pytest.approx(0.0)
    assert mapped[14] == pytest.approx(-0.04)
    assert mapped[15] == pytest.approx(0.04)


def test_gripper_midpoint_and_clamp():
    command = np.zeros(14, dtype=np.float32)
    command[6] = 0.25
    command[13] = 2.0

    mapped = command14_to_leisaac16(command)

    assert mapped[6] == pytest.approx(-0.01)
    assert mapped[7] == pytest.approx(0.01)
    assert mapped[14] == pytest.approx(-0.04)
    assert mapped[15] == pytest.approx(0.04)


def test_round_trip_batch():
    commands = np.stack(
        [
            make_replay_command14(left_gripper=0.0, right_gripper=1.0),
            make_replay_command14(left_j1=-0.2, right_j1=0.3, left_gripper=0.5, right_gripper=0.25),
        ],
        axis=0,
    )

    mapped = command14_to_leisaac16(commands)
    restored = leisaac16_to_command14(mapped)

    np.testing.assert_allclose(restored, commands, atol=1e-6)


def test_symmetry_check():
    mapped = command14_to_leisaac16(make_replay_command14(left_gripper=0.25, right_gripper=0.5))
    result = check_leisaac16_gripper_symmetry(mapped)
    assert result.passed
    broken = mapped.copy()
    broken[7] += 0.01
    result = check_leisaac16_gripper_symmetry(broken)
    assert not result.passed
    assert result.left_max_abs > result.tolerance


def test_shape_errors():
    with pytest.raises(ValueError):
        command14_to_leisaac16(np.zeros(13, dtype=np.float32))
    with pytest.raises(ValueError):
        leisaac16_to_command14(np.zeros(15, dtype=np.float32))
