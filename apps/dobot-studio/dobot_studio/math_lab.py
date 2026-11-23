"""The tabletop Equation Lab UI and optional answer-tile transfers."""
from math import hypot
import tkinter as tk
from tkinter import messagebox, ttk

from .equations import evaluate, split_chips, token
from .robot import GRIPPER_TOOL, MotionStopped, Pose
from .tabletop import same_chip
from .theme import MUTED, PANEL, PURPLE


class EquationLab:
    def __init__(self, cell, parent):
        self.cell = cell
        self.divider = None
        self.setting_divider = False
        self.rows = []
        self.placed = 0
        self.used = []
        self.pending_chip = None
        self.status = tk.StringVar(value="Train number and operator labels, then scan the tray.")
        self.equation = tk.StringVar(value="—")
        self.answer = tk.StringVar(value="—")
        self.selection = tk.StringVar()
        ui = cell.studio
        ui._label(parent, "Equations above the divider\nAnswer chips below it", size=10, fg=PURPLE,
                  wraplength=287, justify="left").pack(fill="x")
        tools = tk.Frame(parent, bg=PANEL)
        tools.pack(fill="x", pady=(5, 4))
        ui._button(tools, "Set divider", self.set_divider).pack(side="left")
        ui._button(tools, "Read equations", self.scan, "Teal").pack(side="left", padx=4)
        if ui.demo:
            ui._button(tools, "Demo coordinates", cell.demo_coordinates).pack(side="left")
        self.row_picker = ttk.Combobox(parent, textvariable=self.selection, values=(), width=16,
                                       state="readonly")
        self.row_picker.pack(fill="x", pady=4)
        self.row_picker.bind("<<ComboboxSelected>>", lambda _event: self.show_answer())
        ui._label(parent, textvariable=self.equation, size=12, weight="bold",
                  wraplength=285).pack(fill="x", pady=(7, 3))
        ui._label(parent, textvariable=self.answer, size=25, weight="bold",
                  fg=PURPLE, wraplength=285).pack(fill="x")
        ui._label(parent, textvariable=self.status, size=9, fg=MUTED,
                  wraplength=288, justify="left").pack(fill="x", pady=5)
        self.place_button = ui._button(parent, "Place next answer chip", self.place, "Teal")
        self.place_button.pack(anchor="w", pady=5)
        self._render()

    def set_divider(self):
        self.setting_divider = True
        self.status.set("Click between the equation rows and the answer bank.")

    def click(self, y):
        if self.setting_divider and not self.cell.busy:
            self.divider = y
            self.setting_divider = False
            self.reset()
            self.status.set("Divider set. Read equations to scan.")
            self.cell._draw()

    def reset(self):
        self.rows, self.placed = [], 0
        self.used = []
        self.pending_chip = None
        self.row_picker.configure(values=())
        self.selection.set("")
        self.equation.set("—")
        self.answer.set("—")
        self._render()

    def _read(self):
        if self.divider is None:
            raise ValueError("Set the divider between the two tray areas first.")
        return split_chips(self.cell.recognise_text(), self.divider)

    def scan(self):
        if self.cell.busy:
            return
        self.reset()
        try:
            rows, bank = self._read()
        except (ImportError, OSError, ValueError) as error:
            self.status.set(str(error))
            return
        for row in rows:
            labels = tuple(chip.label for chip in row)
            try:
                line, result = evaluate(labels)
                self.rows.append((labels, line, result))
            except ValueError as error:
                self.rows.append((labels, " ".join(labels), str(error)))
        if not self.rows:
            self.status.set("Place an equation above the divider, then scan again.")
            return
        choices = [f"Row {i+1}" for i in range(len(self.rows))]
        self.row_picker.configure(values=choices)
        self.row_picker.current(0)
        self.show_answer()
        if not isinstance(self.rows[0][2], str):
            self.status.set(f"Found {len(rows)} equation row(s) and {len(bank)} answer bank chip(s).")
        self.cell.chips = [chip for row in rows for chip in row] + bank
        self.cell._draw()

    def show_answer(self):
        index = self.row_picker.current()
        if not 0 <= index < len(self.rows):
            return
        _labels, equation, result = self.rows[index]
        self.equation.set(equation)
        self.placed = 0
        self.answer.set(f"= {result}" if not isinstance(result, str) else "Check row")
        if isinstance(result, str):
            self.status.set(result)
        elif result.denominator != 1:
            self.status.set("Exact fraction displayed. Placement uses whole-number answers.")
        else:
            self.status.set("A matching chip in the bank can be moved to the answer line.")
        self._render()

    def _render(self):
        index = self.row_picker.current()
        result = self.rows[index][2] if 0 <= index < len(self.rows) else None
        enabled = (not self.cell.busy and result is not None and not isinstance(result, str)
                   and result.denominator == 1 and self.placed < len(str(result)))
        self.cell.studio._set_button(self.place_button, enabled)
        self.row_picker.configure(state="disabled" if self.cell.busy else "readonly")

    def _answer_pose(self, offset):
        poses = self.cell.poses
        if not all(key in poses for key in ("Bin A", "Bin B", "Park")):
            raise ValueError("Teach the first and last answer positions as Bin A and Bin B, and teach Park.")
        first, last = poses["Bin A"], poses["Bin B"]
        distance = hypot(last.x-first.x, last.y-first.y)
        spacing = 30
        if distance < 15 or offset * spacing > distance:
            raise ValueError("The taught answer line is too short for this result.")
        fraction = offset * spacing / distance
        return Pose(first.x + fraction*(last.x-first.x), first.y + fraction*(last.y-first.y),
                    first.z + fraction*(last.z-first.z), first.r)

    def place(self):
        cell = self.cell
        index = self.row_picker.current()
        if cell.busy or not 0 <= index < len(self.rows):
            return
        labels, _, result = self.rows[index]
        if isinstance(result, str) or result.denominator != 1:
            return
        answer = str(result)
        if self.placed >= len(answer):
            return
        wanted = answer[self.placed]
        try:
            fresh, bank = self._read()
            if index >= len(fresh) or tuple(chip.label for chip in fresh[index]) != labels:
                raise ValueError("The equation changed. Read the tray again.")
            self.used = [item for item in self.used
                         if any(same_chip(item, current, require_bin=False) for current in bank)]
            chip = next((candidate for candidate in bank if token(candidate.label) == wanted and
                         not any(same_chip(item, candidate, require_bin=False) for item in self.used)), None)
            if chip is None:
                raise ValueError(f"Put a matching {wanted} chip in the answer bank.")
            if cell.studio.demo:
                def transfer():
                    if cell.stop_event.wait(0.55):
                        raise MotionStopped("Placement stopped.")
                    return None
            else:
                if not cell.studio.robot or not cell.studio.homed:
                    raise ValueError("Connect and home the Dobot before placing answer chips.")
                drop = self._answer_pose(self.placed)
                # Check that the complete answer fits before moving its first digit.
                self._answer_pose(len(answer)-1)
                calibration = cell._calibration()
                if any(calibration.contains_robot(self._answer_pose(offset)) for offset in range(len(answer))):
                    raise ValueError("Teach the answer line outside the pickup triangle.")
                park = cell.poses["Park"]
                tool = cell.attachment.get()
                text = f"Place {wanted} in answer spot {self.placed+1}. Check the travel path."
                if tool == GRIPPER_TOOL:
                    text += " Check jaw clearance around the chip and adjacent answer spots."
                if not messagebox.askokcancel("Place answer chip", text, parent=cell.window):
                    return
                latest, bank = self._read()
                if index >= len(latest) or tuple(c.label for c in latest[index]) != labels:
                    raise ValueError("The equation changed during confirmation. Scan again.")
                now = next((c for c in bank if same_chip(chip, c, require_bin=False)), None)
                if now is None:
                    raise ValueError("The chip moved during confirmation. Check the bank.")
                pick = calibration.pick(now.centre, park.r)

                def transfer():
                    return cell.studio.robot.sort_chip(pick, drop, park, cell.stop_event, tool)
            self.pending_chip = chip
            self.status.set(f"Placing {wanted} in answer spot {self.placed+1}…")
            cell._start_job("math", transfer)
        except (ImportError, OSError, ValueError) as error:
            self.status.set(str(error))
        self._render()

    def complete(self, error):
        if error:
            self.status.set(str(error))
        else:
            self.placed += 1
            self.used.append(self.pending_chip)
            self.status.set(f"Answer chips placed: {self.placed}. Check the result line.")
        self.pending_chip = None
        self._render()
