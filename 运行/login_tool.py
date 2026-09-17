"""学生端登录助手：学生选择姓名后，自动打开浏览器并填好证件号码/便捷登录码，
验证码留给学生本人查看并手动输入。"""

import ctypes
import os
import threading
import tkinter as tk
from collections import Counter
from tkinter import messagebox

from crypto_utils import decode_roster
from paths import app_dir
import roster_data

LOGIN_URL = (
    "https://tyyh.dgjy.net/tpass/login?service=https%3A%2F%2Ftyyh.dgjy.net"
    "%2Ftpass%2Foauth2.0%2FcallbackAuthorize%3Fsession_state"
    "%3DA9D5AF6BF81E98A30182F742CACBA289"
)

_SINGLE_INSTANCE_MUTEX_NAME = "GuanJiaoTong_LoginHelper_SingleInstance"
_ERROR_ALREADY_EXISTS = 183


def acquire_single_instance_lock() -> bool:
    """同一台电脑上只允许一个登录助手在运行；进程结束后系统会自动释放这个锁。"""
    ctypes.windll.kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX_NAME)
    return ctypes.windll.kernel32.GetLastError() != _ERROR_ALREADY_EXISTS


def load_login_code() -> str:
    path = os.path.join(app_dir(), "login_code.txt")
    if not os.path.exists(path):
        raise FileNotFoundError(f"未找到登录码文件：{path}\n请确认 login_code.txt 与本程序放在同一文件夹。")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def build_display_names(roster: dict) -> dict:
    """返回 显示名 -> 身份证号；同班重名的学生用身份证后4位消歧。"""
    counts = Counter(roster.keys())
    display = {}
    for name, id_number in roster.items():
        if counts[name] > 1:
            label = f"{name}（{id_number[-4:]}）"
        else:
            label = name
        display[label] = id_number
    return display


def do_login(id_number: str, login_code: str) -> None:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.edge.options import Options
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    options = Options()
    options.add_experimental_option("detach", True)  # 程序退出后浏览器保持打开
    options.page_load_strategy = "eager"  # 不等图片/样式加载完，DOM 一可交互就返回，加快启动

    local_driver = os.path.join(app_dir(), "msedgedriver.exe")
    if os.path.exists(local_driver):
        from selenium.webdriver.edge.service import Service
        driver = webdriver.Edge(service=Service(executable_path=local_driver), options=options)
    else:
        driver = webdriver.Edge(options=options)  # 由 Selenium Manager 自动定位/下载驱动

    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 15)

    convenient_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "学生便捷登录")))
    convenient_link.click()

    id_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='请输入证件号码']"))
    )
    id_input.clear()
    id_input.send_keys(id_number)

    code_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder='请输入便捷登录码']")
    code_input.clear()
    code_input.send_keys(login_code)

    # 不能调用 driver.quit()：即使开了 detach，quit() 仍会把浏览器一起关掉。
    # 直接杀掉驱动进程本身，浏览器窗口不受影响，避免机房电脑上残留大量后台驱动进程。
    try:
        driver.service.process.kill()
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self, class_label: str, roster: dict):
        super().__init__()
        self.title(f"莞教通登录助手 - {class_label}")
        self.geometry("360x460")
        self.resizable(False, False)

        self.display_roster = build_display_names(roster)
        self.all_names = sorted(self.display_roster.keys())

        tk.Label(self, text=f"{class_label}  请选择你的姓名", font=("Microsoft YaHei", 12)).pack(
            pady=(12, 4)
        )

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        entry = tk.Entry(self, textvariable=self.search_var, font=("Microsoft YaHei", 11))
        entry.pack(fill="x", padx=16)

        self.listbox = tk.Listbox(self, font=("Microsoft YaHei", 11))
        self.listbox.pack(fill="both", expand=True, padx=16, pady=8)
        self._refresh_list(self.all_names)

        self.login_btn = tk.Button(
            self,
            text="登录",
            command=self._on_login,
            font=("Microsoft YaHei", 12),
            bg="#1a73e8",
            fg="white",
        )
        self.login_btn.pack(fill="x", padx=16, pady=(0, 16))
        self._logging_in = False

    def _refresh_list(self, names):
        self.listbox.delete(0, tk.END)
        for n in names:
            self.listbox.insert(tk.END, n)

    def _on_search(self, *_args):
        keyword = self.search_var.get().strip()
        if not keyword:
            self._refresh_list(self.all_names)
        else:
            self._refresh_list([n for n in self.all_names if keyword in n])

    def _on_login(self):
        if self._logging_in:
            return  # 防止界面卡顿期间被连续点击，重复开出多个浏览器

        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先在列表中选择你的姓名")
            return
        display_name = self.listbox.get(selection[0])
        id_number = self.display_roster[display_name]

        try:
            login_code = load_login_code()
        except FileNotFoundError as e:
            messagebox.showerror("错误", str(e))
            return
        if not login_code:
            messagebox.showerror("错误", "登录码文件内容为空，请联系老师确认 login_code.txt")
            return

        self._logging_in = True
        self.login_btn.config(state="disabled", text="正在打开浏览器，请稍候…")

        def worker():
            try:
                do_login(id_number, login_code)
            except Exception as e:
                self.after(0, self._on_login_failed, e)
            else:
                self.after(0, self._on_login_success)

        threading.Thread(target=worker, daemon=True).start()

    def _on_login_success(self):
        self.destroy()  # 浏览器已经打开好了，选人窗口没用了，直接关掉

    def _on_login_failed(self, error):
        self._logging_in = False
        self.login_btn.config(state="normal", text="登录")
        messagebox.showerror("登录出错", f"自动登录过程中出现问题：\n{error}")


def main():
    if not acquire_single_instance_lock():
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("提示", "登录助手已经在运行了，请直接使用已经打开的窗口，不要重复打开程序。")
        root.destroy()
        return

    roster = decode_roster(roster_data.ENCODED_ROSTER)
    app = App(roster_data.CLASS_LABEL, roster)
    app.mainloop()


if __name__ == "__main__":
    main()
