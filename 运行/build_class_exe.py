"""教师端工具：从总表里选一个班级，编译出该班专属的 login_tool_<班级>.exe，
并在同一输出文件夹放一份初始 login_code.txt。

用法：在项目目录下运行  python build_class_exe.py
"""

import os
import shutil
import subprocess

import openpyxl

from crypto_utils import encode_roster
from paths import app_dir

PROJECT_DIR = app_dir()
REQUIRED_COLUMNS = ["年级", "班级", "姓名", "身份证号码"]
CODE_TABLE_COLUMNS = ["班级", "便捷登录码"]


def find_xlsx_candidates():
    return [
        f
        for f in os.listdir(PROJECT_DIR)
        if f.lower().endswith(".xlsx") and not f.startswith("~$")
    ]


def classify_xlsx(xlsx_path: str) -> str:
    """粗略判断一张表格是学生总表、登录码表，还是认不出来。"""
    try:
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        header = next(wb.worksheets[0].iter_rows(values_only=True), None)
    except Exception:
        return "unknown"
    if not header:
        return "unknown"
    cols = set(header)
    if set(REQUIRED_COLUMNS).issubset(cols):
        return "roster"
    if set(CODE_TABLE_COLUMNS).issubset(cols):
        return "codes"
    return "unknown"


def write_roster_template(path: str) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "学生名单"
    ws.append(REQUIRED_COLUMNS)
    ws.append(["七年级", 1, "示例-张三", "110101201501011234"])
    wb.save(path)


def find_system_python() -> str:
    """查找系统里真正的 Python 解释器（不能用 sys.executable ——
    manage_panel 打包成 exe 后 sys.executable 会指向自己，而不是 Python）。"""
    for candidate in ("python", "python3"):
        found = shutil.which(candidate)
        if found:
            return found
    raise RuntimeError(
        "没有在这台电脑上找到 Python。生成登录程序需要用到系统安装的 Python + PyInstaller，"
        "请先安装 Python 并运行 pip install -r requirements.txt。"
    )


def load_students(xlsx_path: str):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]
    if not rows:
        raise ValueError("表格是空的")

    header = rows[0]
    col = {name: idx for idx, name in enumerate(header)}
    for required in REQUIRED_COLUMNS:
        if required not in col:
            raise ValueError(f"表格缺少必须的列：{required}")

    students = []
    for row in rows[1:]:
        name = row[col["姓名"]]
        id_number = row[col["身份证号码"]]
        grade = row[col["年级"]]
        klass = row[col["班级"]]
        if not name or not id_number:
            continue
        students.append(
            {
                "grade": str(grade).strip(),
                "class": str(klass).strip(),
                "name": str(name).strip(),
                "id": str(id_number).strip(),
            }
        )
    return students


def choose_from_list(prompt: str, options: list, allow_all: bool = False) -> "int | str":
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = input(prompt).strip()
        if allow_all and raw.lower() == "all":
            return "all"
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        if allow_all:
            print("输入无效，请重新输入编号，或输入 all 编译所有班级。")
        else:
            print("输入无效，请重新输入编号。")


def sanitize_filename(text: str) -> str:
    for ch in r'\/:*?"<>|':
        text = text.replace(ch, "")
    return text


def generate_roster_module(roster: dict, class_label: str, out_path: str):
    encoded = encode_roster(roster)
    content = f"CLASS_LABEL = {class_label!r}\nENCODED_ROSTER = {encoded!r}\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)


def run_pyinstaller(exe_name: str, dist_dir: str, log=print):
    python_cmd = find_system_python()
    driver_path = os.path.join(PROJECT_DIR, "msedgedriver.exe")
    icon_path = os.path.join(PROJECT_DIR, "login_icon.ico")
    cmd = [
        python_cmd,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconsole",
        "--clean",
        "--noconfirm",
        "--name",
        exe_name,
        "--distpath",
        dist_dir,
        "--workpath",
        os.path.join(PROJECT_DIR, "build_tmp"),
        "--specpath",
        os.path.join(PROJECT_DIR, "build_tmp"),
    ]
    if os.path.exists(icon_path):
        cmd += ["--icon", icon_path]
    if os.path.exists(driver_path):
        cmd += ["--add-binary", f"{driver_path};."]
    else:
        log("提示：未在项目目录找到 msedgedriver.exe，打包后的程序将依赖 Selenium 自动下载驱动"
            "（需要联网），如果机房电脑联网受限，请下载与 Edge 版本匹配的 msedgedriver.exe"
            "放到本项目目录后重新构建。")
    cmd.append(os.path.join(PROJECT_DIR, "login_tool.py"))
    result = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"PyInstaller 编译失败（退出码 {result.returncode}）：\n{tail}")


def build_one_class(grade: str, klass: str, class_students: list, log=print) -> str:
    class_label = f"{grade}{klass}班"
    roster = {s["name"]: s["id"] for s in class_students}
    log(f"共 {len(roster)} 名学生（{class_label}）")

    roster_module_path = os.path.join(PROJECT_DIR, "roster_data.py")
    generate_roster_module(roster, class_label, roster_module_path)

    safe_label = sanitize_filename(class_label)
    exe_name = f"{safe_label}自动登录程序"
    dist_dir = os.path.join(PROJECT_DIR, "dist_output", safe_label)

    log(f"正在编译 {exe_name}.exe ，请稍候……")
    try:
        run_pyinstaller(exe_name, dist_dir, log=log)
    finally:
        if os.path.exists(roster_module_path):
            os.remove(roster_module_path)

    exe_path = os.path.join(dist_dir, f"{exe_name}.exe")
    login_code_path = os.path.join(dist_dir, "login_code.txt")
    if not os.path.exists(login_code_path):
        with open(login_code_path, "w", encoding="utf-8") as f:
            f.write("请填写本班当前有效的便捷登录码")

    log(f"完成：{exe_path}")
    return exe_path


def main():
    candidates = find_xlsx_candidates()
    if not candidates:
        print("未在当前目录找到任何 .xlsx 总表文件。")
        return
    if len(candidates) == 1:
        xlsx_path = os.path.join(PROJECT_DIR, candidates[0])
        print(f"使用表格：{candidates[0]}")
    else:
        print("找到多个表格：")
        idx = choose_from_list("请选择要使用的表格编号：", candidates)
        xlsx_path = os.path.join(PROJECT_DIR, candidates[idx])

    students = load_students(xlsx_path)
    if not students:
        print("表格中没有读到有效学生数据。")
        return

    combos = sorted({(s["grade"], s["class"]) for s in students})
    print("可选班级：")
    combo_labels = [f"{grade} {klass}班" for grade, klass in combos]
    choice = choose_from_list("请输入班级编号（输入 all 可一次性编译所有班级）：", combo_labels, allow_all=True)

    if choice == "all":
        total = len(combos)
        failed = []
        for i, (grade, klass) in enumerate(combos, 1):
            class_students = [s for s in students if s["grade"] == grade and s["class"] == klass]
            if not class_students:
                continue
            print(f"\n[{i}/{total}] {grade}{klass}班")
            try:
                build_one_class(grade, klass, class_students)
            except Exception as e:
                print(f"  编译失败：{e}")
                failed.append(f"{grade}{klass}班")

        print(f"\n全部完成：{total - len(failed)}/{total} 个班级编译成功。")
        if failed:
            print("以下班级编译失败，请单独重新运行处理：")
            for label in failed:
                print(f"  - {label}")
        return

    grade, klass = combos[choice]
    class_students = [s for s in students if s["grade"] == grade and s["class"] == klass]
    if not class_students:
        print("该班级没有学生数据。")
        return

    build_one_class(grade, klass, class_students)
    print("请把生成的 exe 和 login_code.txt 一起拷贝到该班机房电脑的桌面。")


if __name__ == "__main__":
    main()
