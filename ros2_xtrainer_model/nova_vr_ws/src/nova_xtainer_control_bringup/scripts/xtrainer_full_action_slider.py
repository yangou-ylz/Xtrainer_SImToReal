#!/usr/bin/env python3
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import rclpy

from xtrainer_full_command14 import ACTION14_NAMES, DEFAULT_ACTION14, FullCommand14Publisher


class SliderApp:
    def __init__(self, node: FullCommand14Publisher) -> None:
        self.node = node
        self.root = tk.Tk()
        self.root.title("X-Trainer 14 Action Control")
        self.vars: list[tk.DoubleVar] = []
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(50, self._spin_ros)

    def _build(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        for idx, name in enumerate(ACTION14_NAMES):
            var = tk.DoubleVar(value=DEFAULT_ACTION14[idx])
            self.vars.append(var)
            row = ttk.Frame(main)
            row.grid(row=idx, column=0, sticky="ew", pady=2)
            row.columnconfigure(1, weight=1)
            ttk.Label(row, text=name, width=14).grid(row=0, column=0, sticky="w")
            if "gripper" in name:
                lo, hi, resolution = 0.0, 1.0, 0.01
            else:
                lo, hi, resolution = -3.1416, 3.1416, 0.01
            scale = ttk.Scale(row, from_=lo, to=hi, variable=var, orient=tk.HORIZONTAL, command=lambda _v: self.send())
            scale.grid(row=0, column=1, sticky="ew", padx=8)
            spin = ttk.Spinbox(row, from_=lo, to=hi, increment=resolution, textvariable=var, width=8, command=self.send)
            spin.grid(row=0, column=2, sticky="e")
        buttons = ttk.Frame(main)
        buttons.grid(row=len(ACTION14_NAMES), column=0, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Send", command=self.send).grid(row=0, column=0, padx=3)
        ttk.Button(buttons, text="Home", command=self.home).grid(row=0, column=1, padx=3)
        ttk.Button(buttons, text="Open", command=lambda: self.set_grippers(0.0)).grid(row=0, column=2, padx=3)
        ttk.Button(buttons, text="Close", command=lambda: self.set_grippers(1.0)).grid(row=0, column=3, padx=3)

    def values(self) -> list[float]:
        return [float(v.get()) for v in self.vars]

    def send(self) -> None:
        self.node.publish_action14(self.values(), duration=0.45)

    def home(self) -> None:
        for var, value in zip(self.vars, DEFAULT_ACTION14):
            var.set(value)
        self.send()

    def set_grippers(self, value: float) -> None:
        self.vars[6].set(value)
        self.vars[13].set(value)
        self.send()

    def _spin_ros(self) -> None:
        rclpy.spin_once(self.node, timeout_sec=0.0)
        self.root.after(50, self._spin_ros)

    def run(self) -> None:
        self.send()
        self.root.mainloop()

    def close(self) -> None:
        self.root.destroy()


def main() -> None:
    rclpy.init()
    node = FullCommand14Publisher("session_full_action_slider")
    try:
        SliderApp(node).run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
