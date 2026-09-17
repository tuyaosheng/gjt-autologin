"""教师端可视化管理面板：生成各班登录程序 + 更新便捷登录码。

用法：在项目目录下运行  python manage_panel.py
（或使用打包好的 manage_panel.exe，但这台电脑仍需装有 Python + PyInstaller，
"生成登录程序"这一步本质是现场编译，无法脱离 Python 环境。）
"""

import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox

import build_class_exe as builder
import update_login_codes as coder
from paths import app_dir

PROJECT_DIR = app_dir()

BG = "#f4f6f9"
ACCENT = "#1a73e8"
LOG_BG = "#12161f"
LOG_FG = "#d9e1f2"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("莞教通登录助手 - 教师管理面板")
        self.geometry("760x680")
        self.minsize(680, 560)
        self.configure(bg=BG)
        try:
            self.iconbitmap(os.path.join(PROJECT_DIR, "panel_icon.ico"))
        except Exception:
            pass

        self.log_queue = queue.Queue()
        self.busy = False
        self.students = []
        self.class_combos = []

        self._build_ui()
        self._refresh_all()
        threading.Thread(target=self._check_env, daemon=True).start()
        self.after(100, self._poll_log_queue)

    # ---------------- UI ----------------

    def _build_ui(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(18, 6))
        tk.Label(header, text="莞教通登录助手 · 管理面板", font=("Microsoft YaHei", 16, "bold"),
                 bg=BG, fg="#1b2330").pack(side="left")
        tk.Button(header, text="重新检测文件", command=self._refresh_all).pack(side="right")

        self.env_label = tk.Label(self, text="正在检测运行环境…", font=("Microsoft YaHei", 9),
                                   bg=BG, fg="#888", anchor="w")
        self.env_label.pack(fill="x", padx=18)

        # ---- ① 生成登录程序 ----
        gen_box = tk.LabelFrame(self, text="① 生成登录程序", font=("Microsoft YaHei", 11, "bold"),
                                 bg=BG, padx=12, pady=10)
        gen_box.pack(fill="both", expand=True, padx=18, pady=(10, 8))

        self.roster_label = tk.Label(gen_box, text="", font=("Microsoft YaHei", 10),
                                      bg=BG, anchor="w", justify="left")
        self.roster_label.pack(fill="x")

        list_frame = tk.Frame(gen_box, bg=BG)
        list_frame.pack(fill="both", expand=True, pady=(8, 6))
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.class_listbox = tk.Listbox(
            list_frame, selectmode="extended", font=("Microsoft YaHei", 10),
            yscrollcommand=scrollbar.set, height=8, activestyle="none",
        )
        self.class_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.class_listbox.yview)

        btn_row = tk.Frame(gen_box, bg=BG)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="全选", command=self._select_all_classes).pack(side="left")
        tk.Button(btn_row, text="清空", command=self._clear_class_selection).pack(side="left", padx=(6, 0))
        self.gen_button = tk.Button(
            btn_row, text="开始生成", bg=ACCENT, fg="white", activebackground="#1558b0",
            font=("Microsoft YaHei", 10, "bold"), command=self._on_generate,
        )
        self.gen_button.pack(side="right")

        # ---- ② 更新便捷登录码 ----
        code_box = tk.LabelFrame(self, text="② 更新便捷登录码", font=("Microsoft YaHei", 11, "bold"),
                                  bg=BG, padx=12, pady=10)
        code_box.pack(fill="x", padx=18, pady=(0, 8))

        self.code_label = tk.Label(code_box, text="", font=("Microsoft YaHei", 10),
                                    bg=BG, anchor="w", justify="left")
        self.code_label.pack(fill="x")

        code_btn_row = tk.Frame(code_box, bg=BG)
        code_btn_row.pack(fill="x", pady=(8, 0))
        self.update_button = tk.Button(
            code_btn_row, text="读取并更新登录码", bg=ACCENT, fg="white", activebackground="#1558b0",
            font=("Microsoft YaHei", 10, "bold"), command=self._on_update_codes,
        )
        self.update_button.pack(side="right")

        # ---- 日志 ----
        log_box = tk.LabelFrame(self, text="运行日志", font=("Microsoft YaHei", 11, "bold"), bg=BG, padx=8, pady=6)
        log_box.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.log_text = tk.Text(log_box, font=("Consolas", 9), state="disabled", wrap="word",
                                 bg=LOG_BG, fg=LOG_FG, relief="flat", padx=8, pady=6)
        self.log_text.pack(fill="both", expand=True)

    # ---------------- 状态刷新 ----------------

    def _refresh_all(self):
        self._refresh_roster_info()
        self._refresh_code_table_info()

    def _list_by_kind(self, kind: str):
        names = builder.find_xlsx_candidates()
        return [n for n in names if builder.classify_xlsx(os.path.join(PROJECT_DIR, n)) == kind]

    def _refresh_roster_info(self):
        matches = self._list_by_kind("roster")
        self.class_listbox.delete(0, "end")
        self.students = []
        self.class_combos = []

        if not matches:
            self.roster_label.config(text="⚠ 未找到学生总表（需要包含：年级 / 班级 / 姓名 / 身份证号码 列）")
            return

        roster_name = matches[0]
        if len(matches) > 1:
            self.roster_label.config(
                text=f"检测到 {len(matches)} 张疑似总表，使用「{roster_name}」——建议目录下只保留一份总表，避免用错"
            )
        else:
            self.roster_label.config(text=f"学生总表：{roster_name}")

        try:
            self.students = builder.load_students(os.path.join(PROJECT_DIR, roster_name))
        except Exception as e:
            self.roster_label.config(text=f"⚠ 读取总表出错：{e}")
            return

        self.class_combos = sorted({(s["grade"], s["class"]) for s in self.students})
        for grade, klass in self.class_combos:
            self.class_listbox.insert("end", f"{grade}{klass}班")

    def _refresh_code_table_info(self):
        matches = self._list_by_kind("codes")
        if not matches:
            self.code_label.config(text="⚠ 未找到便捷登录码表格（需要包含：班级 / 便捷登录码 列）")
        elif len(matches) > 1:
            self.code_label.config(text=f"检测到 {len(matches)} 张疑似登录码表，使用「{matches[0]}」")
        else:
            self.code_label.config(text=f"登录码表格：{matches[0]}")

    def _check_env(self):
        try:
            python_cmd = builder.find_system_python()
            result = subprocess.run([python_cmd, "-m", "PyInstaller", "--version"],
                                     capture_output=True, text=True)
            if result.returncode == 0:
                msg = f"✓ 已检测到 Python 和 PyInstaller（{python_cmd}），生成功能可以正常使用"
            else:
                msg = "⚠ 检测到 Python，但没装 PyInstaller，请先运行：pip install -r requirements.txt"
        except Exception as e:
            msg = f"⚠ {e}"
        self.log_queue.put(("env", msg))

    # ---------------- 日志队列 ----------------

    def _poll_log_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "env":
                    self.env_label.config(text=payload)
                elif kind == "log":
                    self._append_log(payload)
                elif kind == "gen_done":
                    self._on_generate_done()
                elif kind == "update_done":
                    self._on_update_done()
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _append_log(self, text: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ---------------- ① 生成登录程序 ----------------

    def _select_all_classes(self):
        self.class_listbox.selection_set(0, "end")

    def _clear_class_selection(self):
        self.class_listbox.selection_clear(0, "end")

    def _set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.gen_button.config(state=state)
        self.update_button.config(state=state)

    def _on_generate(self):
        if self.busy:
            return
        selection = self.class_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先在列表中选择至少一个班级（也可以点“全选”）")
            return
        selected_combos = [self.class_combos[i] for i in selection]

        self._set_busy(True)
        self.gen_button.config(text="生成中…")

        def worker():
            total = len(selected_combos)
            failed = []
            for i, (grade, klass) in enumerate(selected_combos, 1):
                class_students = [s for s in self.students if s["grade"] == grade and s["class"] == klass]
                self.log_queue.put(("log", f"[{i}/{total}] {grade}{klass}班"))
                try:
                    builder.build_one_class(
                        grade, klass, class_students,
                        log=lambda m: self.log_queue.put(("log", "    " + m)),
                    )
                except Exception as e:
                    self.log_queue.put(("log", f"    编译失败：{e}"))
                    failed.append(f"{grade}{klass}班")

            ok = total - len(failed)
            self.log_queue.put(("log", f"生成完成：{ok}/{total} 个班级成功。"))
            if failed:
                self.log_queue.put(("log", "失败班级：" + "、".join(failed)))
            self.log_queue.put(("gen_done", None))

        threading.Thread(target=worker, daemon=True).start()

    def _on_generate_done(self):
        self._set_busy(False)
        self.gen_button.config(text="开始生成")

    # ---------------- ② 更新便捷登录码 ----------------

    def _on_update_codes(self):
        if self.busy:
            return
        matches = self._list_by_kind("codes")
        if not matches:
            messagebox.showerror("错误", "未找到便捷登录码表格（需要包含：班级 / 便捷登录码 列）")
            return
        code_path = os.path.join(PROJECT_DIR, matches[0])

        self._set_busy(True)
        self.update_button.config(text="更新中…")

        def worker():
            try:
                codes = coder.load_codes(code_path)
                if not codes:
                    self.log_queue.put(("log", "登录码表格里没有读到有效数据。"))
                elif not os.path.isdir(coder.DIST_DIR):
                    self.log_queue.put(("log", "还没有生成过任何班级的登录程序，无法更新。"))
                else:
                    updated, missing = coder.apply_codes(codes)
                    if updated:
                        self.log_queue.put(("log", f"已更新 {len(updated)} 个班级：" + "、".join(updated)))
                    else:
                        self.log_queue.put(("log", "没有可更新的班级（都还没生成过 exe）。"))
                    if missing:
                        self.log_queue.put(("log", "以下班级还没生成过 exe，已跳过：" + "、".join(missing)))
                    self.log_queue.put(("log", "提醒：这里只更新了本机 dist_output 里的文件，"
                                                "还需要用 U 盘把更新后的 login_code.txt 覆盖到机房电脑。"))
            except Exception as e:
                self.log_queue.put(("log", f"更新登录码出错：{e}"))
            self.log_queue.put(("update_done", None))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_done(self):
        self._set_busy(False)
        self.update_button.config(text="读取并更新登录码")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
