"""教师端工具：每两天读一次"便捷登录码.xlsx"，把每个班最新的登录码
写进 dist_output/<班级>/login_code.txt。

表格格式（Sheet1）：
    班级          便捷登录码
    七年级1班      81634017

用法：在项目目录下运行  python update_login_codes.py
"""

import os

import openpyxl

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_TABLE_NAME = "便捷登录码.xlsx"
DIST_DIR = os.path.join(PROJECT_DIR, "dist_output")


def format_code(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def load_codes(xlsx_path: str) -> dict:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]
    if not rows:
        raise ValueError("表格是空的")

    header = rows[0]
    col = {name: idx for idx, name in enumerate(header)}
    for required in ("班级", "便捷登录码"):
        if required not in col:
            raise ValueError(f"表格缺少必须的列：{required}")

    codes = {}
    for row in rows[1:]:
        class_label = row[col["班级"]]
        code = row[col["便捷登录码"]]
        if not class_label or code is None:
            continue
        codes[str(class_label).strip()] = format_code(code)
    return codes


def main():
    xlsx_path = os.path.join(PROJECT_DIR, CODE_TABLE_NAME)
    if not os.path.exists(xlsx_path):
        print(f"未找到 {CODE_TABLE_NAME}，请把登录码表格放在项目目录下。")
        return

    codes = load_codes(xlsx_path)
    if not codes:
        print("表格里没有读到有效的班级/登录码。")
        return

    if not os.path.isdir(DIST_DIR):
        print(f"未找到 {DIST_DIR}，请先用 build_class_exe.py 生成过至少一个班级。")
        return

    updated, missing = [], []
    for class_label, code in codes.items():
        class_dir = os.path.join(DIST_DIR, class_label)
        if not os.path.isdir(class_dir):
            missing.append(class_label)
            continue
        login_code_path = os.path.join(class_dir, "login_code.txt")
        with open(login_code_path, "w", encoding="utf-8") as f:
            f.write(code)
        updated.append(class_label)

    print(f"已更新 {len(updated)} 个班级的 login_code.txt：")
    for label in updated:
        print(f"  - {label}")

    if missing:
        print(f"\n以下班级在表格里有登录码，但还没生成过 exe（跳过），"
              f"请先用 build_class_exe.py 生成：")
        for label in missing:
            print(f"  - {label}")

    print("\n提醒：这里只更新了你电脑上 dist_output 里的 login_code.txt，"
          "还需要用 U 盘把每个更新过的 login_code.txt 覆盖到对应机房电脑桌面上才会生效。")


if __name__ == "__main__":
    main()
