#!/usr/bin/env python3
"""Finite Isaac Lab runtime smoke test for pip-installed Isaac Sim."""

from isaaclab.app import AppLauncher


def main() -> None:
    app_launcher = AppLauncher({"headless": True})
    simulation_app = app_launcher.app

    sim = None
    try:
        import isaaclab  # noqa: F401
        import isaaclab_tasks  # noqa: F401
        from isaaclab.sim import SimulationCfg, SimulationContext

        sim = SimulationContext(SimulationCfg(dt=0.01))
        sim.reset()
        for _ in range(5):
            sim.step()
        print("isaaclab_runtime_smoke_ok", flush=True)
    finally:
        if sim is not None:
            sim.clear_all_callbacks()
            sim.clear_instance()
        simulation_app.close(wait_for_replicator=False, skip_cleanup=True)


if __name__ == "__main__":
    main()
