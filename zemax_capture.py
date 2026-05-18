# -*- coding: utf-8 -*-
"""
Zemax 原生图全屏保存脚本 v6（发布版）
核心修正：
1. 不再靠模糊标题匹配已有窗口，而是“打开分析前后对比”，优先抓新出现的分析窗口。
2. 抓到分析窗口后，强制移动到主屏可见区域并放大，再截图。
3. 保留多后端截图与文字日志，但不再生成调试图片。
4. 评价函数不再渲染二进制 .MF，而是导出清晰预览图与 CSV。
5. 结束前尝试关闭除主窗口外的分析窗口。

依赖：
    python -m pip install pythonnet pillow pyautogui pywin32 mss numpy

使用前：
1. 打开 OpticStudio
2. 打开目标镜头文件
3. Programming -> Interactive Extension -> Python
4. 建议先关闭旧的分析窗口，避免界面太乱（不是必须）
"""

import os
import re
import time
import ctypes
import traceback
import datetime
import csv
import winreg
from pathlib import Path

import clr
import numpy as np
import pyautogui
from PIL import Image, ImageGrab, ImageDraw, ImageFont
import mss
import win32gui
import win32con
import win32process
try:
    import win32clipboard
except Exception:
    win32clipboard = None

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass


def connect_interactive_extension(instance=0):
    aKey = winreg.OpenKey(
        winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER),
        r"Software\Zemax",
        0,
        winreg.KEY_READ,
    )
    zemaxData = winreg.QueryValueEx(aKey, "ZemaxRoot")
    net_helper = os.path.join(os.sep, zemaxData[0], r"ZOS-API\Libraries\ZOSAPI_NetHelper.dll")
    winreg.CloseKey(aKey)

    clr.AddReference(net_helper)
    import ZOSAPI_NetHelper  # type: ignore

    success = ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize("")
    if not success:
        raise RuntimeError("Cannot find OpticStudio")

    zemax_dir = ZOSAPI_NetHelper.ZOSAPI_Initializer.GetZemaxDirectory()
    clr.AddReference(os.path.join(os.sep, zemax_dir, r"ZOSAPI.dll"))
    clr.AddReference(os.path.join(os.sep, zemax_dir, r"ZOSAPI_Interfaces.dll"))
    import ZOSAPI  # type: ignore

    connection = ZOSAPI.ZOSAPI_Connection()
    app = connection.ConnectAsExtension(instance)
    if app is None:
        raise RuntimeError("Unable to acquire ZOSAPI application. 请先打开 Interactive Extension -> Python")
    if app.IsValidLicenseForAPI is False:
        raise RuntimeError("License is not valid for ZOSAPI use. 请确认 Interactive Extension 已开启")

    system = app.PrimarySystem
    if system is None:
        raise RuntimeError("Unable to acquire Primary system")

    print(f"Found OpticStudio at: {zemax_dir}")
    print("Connected to OpticStudio")
    print("Serial #:", app.SerialCode)
    return ZOSAPI, app, system


def try_get_enum_member(enum_obj, candidates):
    available = dir(enum_obj)
    for name in candidates:
        if name in available:
            return getattr(enum_obj, name), name
    return None, None


def open_analysis(system, zosapi, title, enum_candidates):
    enum_value, enum_name = try_get_enum_member(zosapi.Analysis.AnalysisIDM, enum_candidates)
    if enum_value is None:
        raise RuntimeError(f"未找到枚举：{title} -> {enum_candidates}")
    analysis = system.Analyses.New_Analysis_SettingsFirst(enum_value)
    analysis.ApplyAndWaitForCompletion()
    return analysis, enum_name


def get_opticstudio_main_hwnd_and_pid():
    wins = []

    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and "OpticStudio" in title:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                wins.append((hwnd, title, pid))

    win32gui.EnumWindows(enum_handler, None)
    if not wins:
        raise RuntimeError("没有找到 OpticStudio 主窗口")
    wins.sort(key=lambda x: len(x[1]), reverse=True)
    return wins[0]


def normalize_title(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def get_window_rect(hwnd):
    try:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        return (l, t, r, b)
    except Exception:
        return None


def get_window_pid(hwnd):
    try:
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        return pid
    except Exception:
        return None


def is_window_visible(hwnd):
    try:
        return bool(win32gui.IsWindowVisible(hwnd))
    except Exception:
        return False


def force_close_window(hwnd, timeout=1.5):
    if not hwnd:
        return False
    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception:
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if not win32gui.IsWindow(hwnd):
                return True
        except Exception:
            return True
        time.sleep(0.05)

    try:
        win32gui.SendMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception:
        pass

    deadline = time.time() + 0.5
    while time.time() < deadline:
        try:
            if not win32gui.IsWindow(hwnd):
                return True
        except Exception:
            return True
        time.sleep(0.05)
    return False


def wait_for_analysis_completion(analysis, timeout=20.0, poll=0.1):
    if analysis is None:
        return False
    try:
        analysis.ApplyAndWaitForCompletion()
        return True
    except Exception:
        pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if hasattr(analysis, "IsRunning") and not bool(analysis.IsRunning):
                return True
        except Exception:
            pass
        try:
            results = analysis.GetResults()
            if results is not None:
                return True
        except Exception:
            pass
        time.sleep(poll)
    return False


def rect_area(rect):
    if not rect:
        return 0
    l, t, r, b = rect
    return max(0, r - l) * max(0, b - t)


def is_reasonable_rect(rect):
    if not rect:
        return False
    l, t, r, b = rect
    return (r - l) > 250 and (b - t) > 200


def enum_top_windows_for_pid(pid):
    results = {}

    def enum_top(hwnd, _):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid != pid:
                return
            results[hwnd] = {
                "hwnd": hwnd,
                "title": win32gui.GetWindowText(hwnd),
                "class": win32gui.GetClassName(hwnd),
                "visible": win32gui.IsWindowVisible(hwnd),
                "rect": get_window_rect(hwnd),
            }
        except Exception:
            pass

    win32gui.EnumWindows(enum_top, None)
    return results


def find_new_analysis_window(pid, before_hwnds, timeout=4.0, poll=0.1):
    deadline = time.time() + timeout
    best = None
    while time.time() < deadline:
        now = enum_top_windows_for_pid(pid)
        new_items = []
        for hwnd, info in now.items():
            if hwnd in before_hwnds:
                continue
            if not info["visible"]:
                continue
            if not is_reasonable_rect(info["rect"]):
                continue
            new_items.append(info)
        if new_items:
            new_items.sort(key=lambda x: rect_area(x["rect"]), reverse=True)
            best = new_items[0]
            return best, new_items
        time.sleep(poll)
    return None, []


def find_window_by_keywords(pid, keywords, exclude_hwnds=None):
    exclude_hwnds = exclude_hwnds or set()
    kws = [normalize_title(k) for k in keywords]
    candidates = []
    for info in enum_top_windows_for_pid(pid).values():
        if info["hwnd"] in exclude_hwnds:
            continue
        if not info["visible"]:
            continue
        if not is_reasonable_rect(info["rect"]):
            continue
        blob = f"{normalize_title(info['title'])} {normalize_title(info['class'])}"
        if any(k in blob for k in kws):
            candidates.append(info)
    candidates.sort(key=lambda x: rect_area(x["rect"]), reverse=True)
    return (candidates[0] if candidates else None), candidates


def force_activate(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass
    time.sleep(0.05)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        try:
            pyautogui.press("alt")
            time.sleep(0.05)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
    time.sleep(0.12)


def move_resize_to_primary(hwnd, margin_left=40, margin_top=40, margin_right=40, margin_bottom=80):
    screen_w = ctypes.windll.user32.GetSystemMetrics(0)
    screen_h = ctypes.windll.user32.GetSystemMetrics(1)
    x = margin_left
    y = margin_top
    w = max(900, screen_w - margin_left - margin_right)
    h = max(700, screen_h - margin_top - margin_bottom)

    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.05)
    except Exception:
        pass

    flags = win32con.SWP_SHOWWINDOW
    try:
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, flags)
        time.sleep(0.12)
    except Exception:
        pass

    try:
        win32gui.MoveWindow(hwnd, x, y, w, h, True)
        time.sleep(0.12)
    except Exception:
        pass

    force_activate(hwnd)

    # 再来一次，防止第一次被系统忽略
    try:
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, flags)
        time.sleep(0.12)
    except Exception:
        pass

    return get_window_rect(hwnd)


def click_center_of_window(hwnd):
    rect = get_window_rect(hwnd)
    if not rect:
        return
    l, t, r, b = rect
    cx = (l + r) // 2
    cy = (t + b) // 2
    try:
        pyautogui.click(cx, cy)
        time.sleep(0.1)
    except Exception:
        pass


def is_almost_black(img: Image.Image, mean_threshold=8.0, nonblack_ratio_threshold=0.005):
    arr = np.asarray(img.convert("RGB"), dtype=np.uint8)
    gray = arr.mean(axis=2)
    mean_val = float(gray.mean())
    nonblack_ratio = float((gray > 15).mean())
    return (mean_val < mean_threshold) or (nonblack_ratio < nonblack_ratio_threshold), mean_val, nonblack_ratio


def _capture_bbox_mss(l, t, width, height):
    with mss.mss() as sct:
        shot = sct.grab({"left": l, "top": t, "width": width, "height": height})
        return Image.frombytes("RGB", shot.size, shot.rgb)


def iter_capture_bbox(bbox):
    l, t, r, b = bbox
    width = r - l
    height = b - t

    capture_steps = [
        ("mss", lambda: _capture_bbox_mss(l, t, width, height)),
        ("pyautogui", lambda: pyautogui.screenshot(region=(l, t, width, height))),
        ("pil", lambda: ImageGrab.grab(bbox=bbox, all_screens=True)),
    ]

    for method_name, grab in capture_steps:
        try:
            yield method_name, grab()
        except Exception as exc:
            print(f"  capture backend {method_name} failed, skipped: {exc}")


def capture_bbox(bbox):
    return list(iter_capture_bbox(bbox))


def save_full_debug_with_rect(out_path: Path, bbox, note=""):
    full = ImageGrab.grab(all_screens=True)
    draw = ImageDraw.Draw(full)
    draw.rectangle(bbox, outline=(255, 0, 0), width=6)
    if note:
        draw.text((bbox[0] + 12, max(12, bbox[1] - 30)), note, fill=(255, 0, 0))
    full.save(out_path)


def get_font(size=24, mono=False):
    candidates = []
    if mono:
        candidates += [
            r"C:\Windows\Fonts\consola.ttf",
            r"C:\Windows\Fonts\cour.ttf",
            r"C:\Windows\Fonts\lucon.ttf",
        ]
    else:
        candidates += [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ]
    for fp in candidates:
        try:
            return ImageFont.truetype(fp, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def wrap_text_by_width(draw, text, font, max_width):
    if text is None:
        return [""]
    out = []
    for raw in str(text).splitlines() or [""]:
        if not raw:
            out.append("")
            continue
        buf = ""
        for ch in raw:
            test = buf + ch
            try:
                w = draw.textbbox((0, 0), test, font=font)[2]
            except Exception:
                w = len(test) * 12
            if w <= max_width or not buf:
                buf = test
            else:
                out.append(buf)
                buf = ch
        out.append(buf)
    return out


def render_text_image(lines, out_path: Path, title="Merit Function Editor"):
    width = 1800
    margin = 36
    header_h = 72
    line_h = 30
    bg = (250, 250, 250)
    fg = (20, 20, 20)
    sub = (90, 90, 90)
    font_title = get_font(30, mono=False)
    font_body = get_font(22, mono=True)
    dummy = Image.new("RGB", (width, 400), bg)
    draw = ImageDraw.Draw(dummy)
    max_text_width = width - margin * 2
    wrapped = []
    for line in lines:
        wrapped.extend(wrap_text_by_width(draw, line, font_body, max_text_width))
    height = header_h + margin * 2 + max(10, len(wrapped)) * line_h + 40
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width, 58), fill=(236, 236, 236))
    draw.text((margin, 14), title, fill=fg, font=font_title)
    draw.text((width - 290, 18), "Generated by script", fill=sub, font=get_font(18, mono=False))
    y = header_h
    for line in wrapped:
        draw.text((margin, y), line, fill=fg, font=font_body)
        y += line_h
    img.save(out_path)
    return out_path


def _safe_call(obj, attr_name, default=None):
    try:
        value = getattr(obj, attr_name)
        if callable(value):
            value = value()
        return value
    except Exception:
        return default


def _cell_to_text(cell):
    for attr_name in ["Text", "Value", "StringValue", "DoubleValue", "IntegerValue"]:
        try:
            value = getattr(cell, attr_name)
            if callable(value):
                value = value()
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        except Exception:
            pass
    return ""


def _short_enum_name(value):
    text = str(value)
    if "." in text:
        text = text.split(".")[-1]
    return text


def _truncate_text(text, max_len):
    text = str(text) if text is not None else ""
    text = text.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')
    text = ' '.join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + '…'



def _safe_getattr(obj, name, default=""):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _fmt_value(v):
    if v is None:
        return ""
    try:
        if isinstance(v, float):
            return f"{v:.12g}"
    except Exception:
        pass
    try:
        return str(v)
    except Exception:
        return ""


def export_lens_data_csv(system, csv_path: Path):
    """
    导出当前镜头的 LDE 关键参数表。
    """
    headers = [
        "surface_index",
        "is_stop",
        "type",
        "comment",
        "radius",
        "thickness",
        "material",
        "semi_diameter",
        "conic",
        "coating",
    ]

    rows = []
    lde = system.LDE
    count = int(lde.NumberOfSurfaces)

    for i in range(count):
        surf = lde.GetSurfaceAt(i)
        row = {
            "surface_index": i,
            "is_stop": _fmt_value(_safe_getattr(surf, "IsStop", "")),
            "type": _fmt_value(_safe_getattr(surf, "TypeName", "")),
            "comment": _fmt_value(_safe_getattr(surf, "Comment", "")),
            "radius": _fmt_value(_safe_getattr(surf, "Radius", "")),
            "thickness": _fmt_value(_safe_getattr(surf, "Thickness", "")),
            "material": _fmt_value(_safe_getattr(surf, "Material", "")),
            "semi_diameter": _fmt_value(_safe_getattr(surf, "SemiDiameter", "")),
            "conic": _fmt_value(_safe_getattr(surf, "Conic", "")),
            "coating": _fmt_value(_safe_getattr(surf, "Coating", "")),
        }
        rows.append(row)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "count": count,
        "path": csv_path,
    }




def _get_clipboard_text():
    if win32clipboard is None:
        return ''
    txt = ''
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                txt = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ''
            elif win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
                raw = win32clipboard.GetClipboardData(win32con.CF_TEXT)
                txt = raw.decode('mbcs', errors='ignore') if isinstance(raw, (bytes, bytearray)) else str(raw)
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass
    return txt


def _clear_clipboard():
    if win32clipboard is None:
        return
    try:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass


def _copy_window_text_via_clipboard(hwnd):
    if not hwnd or not win32gui.IsWindow(hwnd):
        return ''
    try:
        _clear_clipboard()
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.4)

        try:
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            pyautogui.click(l + max(80, min(220, (r - l) // 5)),
                            t + max(60, min(180, (b - t) // 5)))
            time.sleep(0.2)
        except Exception:
            pass

        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.15)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.35)
        txt = _get_clipboard_text()
        if txt and len(txt.strip()) > 20:
            return txt

        pyautogui.hotkey('ctrl', 'home')
        time.sleep(0.1)
        pyautogui.keyDown('shift')
        pyautogui.hotkey('ctrl', 'end')
        pyautogui.keyUp('shift')
        time.sleep(0.15)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.35)
        return _get_clipboard_text()
    except Exception:
        return ''


def _save_analysis_text_result(analysis, out_path: Path):
    notes = []
    try:
        analysis.ApplyAndWaitForCompletion()
    except Exception as e:
        notes.append(f'ApplyAndWaitForCompletion failed: {e}')

    targets = []
    try:
        res = analysis.GetResults()
        if res is not None:
            targets.append(('results', res))
    except Exception as e:
        notes.append(f'GetResults failed: {e}')
    targets.append(('analysis', analysis))

    for owner_name, obj in targets:
        for method_name in [
            'GetTextFile', 'SaveTextFile', 'SaveToTextFile', 'ExportToTextFile',
            'WriteTextFile', 'SaveAsText', 'Save'
        ]:
            if not hasattr(obj, method_name):
                continue
            try:
                getattr(obj, method_name)(str(out_path))
                if out_path.exists() and out_path.stat().st_size > 0:
                    return True, f'{owner_name}.{method_name}'
            except Exception as e:
                notes.append(f'{owner_name}.{method_name} failed: {e}')

    return False, ' | '.join(notes[-8:]) if notes else 'No text export method succeeded'


def _parse_system_report_text_to_csv(report_txt: Path, report_csv: Path):
    rows = []
    section = ''
    for raw in report_txt.read_text(encoding='utf-8', errors='ignore').splitlines():
        s = raw.rstrip()
        if not s.strip():
            continue
        st = s.strip()
        if st.endswith(':') and st.count(':') == 1 and len(st) < 100:
            section = st[:-1].strip()
            continue
        if ':' in st:
            key, value = st.split(':', 1)
            rows.append([section, key.strip(), value.strip()])
        else:
            rows.append([section, st, ''])
    with report_csv.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['Section', 'Key', 'Value'])
        writer.writerows(rows)
    return report_csv


def export_merit_function_csv(system, run_dir: Path):
    csv_path = run_dir / "merit_function.csv"
    mfe = system.MFE
    try:
        operand_count = int(mfe.NumberOfOperands)
    except Exception as exc:
        raise RuntimeError(f"无法读取评价函数操作数数量：{exc}")

    rows = []
    max_cells = 12
    for row_idx in range(1, operand_count + 1):
        try:
            op = mfe.GetOperandAt(row_idx)
        except Exception:
            continue

        row = {
            'Row': row_idx,
            'Type': _short_enum_name(_safe_call(op, 'Type', '')),
            'Target': _safe_call(op, 'Target', ''),
            'Weight': _safe_call(op, 'Weight', ''),
            'Value': _safe_call(op, 'Value', ''),
        }
        for col_idx in range(1, max_cells + 1):
            try:
                cell = op.GetCellAt(col_idx)
                row[f'C{col_idx}'] = _cell_to_text(cell)
            except Exception:
                row[f'C{col_idx}'] = ''
        rows.append(row)

    with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
        fieldnames = ['Row', 'Type', 'Target', 'Weight', 'Value'] + [f'C{i}' for i in range(1, max_cells + 1)]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def write_text_md_from_txt(txt_path: Path):
    md_path = txt_path.with_suffix('.md')
    text = txt_path.read_text(encoding='utf-8', errors='ignore')
    md_path.write_text('# System Data 全文\n\n```text\n' + text + '\n```\n', encoding='utf-8')
    return md_path


def export_system_report_files(system, zosapi, run_dir: Path, app_hwnd=None):
    report_txt = run_dir / "system_data_full.txt"
    created_files = []
    notes = []
    analysis = None
    try:
        analysis_id = getattr(zosapi.Analysis.AnalysisIDM, "SystemData")
        analysis = system.Analyses.New_Analysis(analysis_id)
        wait_for_analysis_completion(analysis, timeout=20.0)
        results = analysis.GetResults()
        results.GetTextFile(str(report_txt))
        if not report_txt.exists() or report_txt.stat().st_size <= 0:
            raise RuntimeError("System Data 全文导出为空")
        created_files.append(report_txt)
    except Exception as exc:
        notes.append(f"System Data 全文导出失败：{exc}")
    finally:
        if analysis is not None:
            try:
                analysis.Close()
            except Exception:
                pass
    return created_files, notes


def export_system_data_files(system, run_dir: Path):
    notes = []
    created_files = []

    snapshot_zmx = run_dir / f"{run_dir.name}.zmx"
    try:
        system.SaveAs(str(snapshot_zmx))
        if snapshot_zmx.exists() and snapshot_zmx.stat().st_size > 0:
            created_files.append(snapshot_zmx)
        else:
            notes.append("当前镜头快照保存后为空")
    except Exception as exc:
        notes.append(f"保存当前镜头快照失败：{exc}")

    return created_files, notes


def export_merit_function_image(system, images_dir: Path, app_hwnd=None):
    # 旧版兼容函数：v8 主流程不再调用评价函数图片导出，只保留 CSV。

    """直接从 MFE API 抽取操作数，生成可读预览图 + CSV。"""
    try:
        mfe = system.MFE
    except Exception as e:
        return False, None, f"无法访问 MFE：{e}"

    try:
        merit_value = mfe.CalculateMeritFunction()
    except Exception:
        merit_value = None

    try:
        operand_count = int(mfe.NumberOfOperands)
    except Exception as e:
        return False, None, f"无法读取操作数数量：{e}"

    rows = []
    max_cells = 10
    for row_idx in range(1, operand_count + 1):
        try:
            op = mfe.GetOperandAt(row_idx)
        except Exception:
            continue

        op_type = _short_enum_name(_safe_call(op, 'Type', ''))
        target = _safe_call(op, 'Target', '')
        weight = _safe_call(op, 'Weight', '')
        value = _safe_call(op, 'Value', '')

        cell_values = []
        for col_idx in range(1, max_cells + 1):
            try:
                cell = op.GetCellAt(col_idx)
                cell_values.append(_cell_to_text(cell))
            except Exception:
                cell_values.append('')

        nonempty_params = [x for x in cell_values if x]
        params_preview = ' | '.join(nonempty_params[:4])

        row = {
            'Row': row_idx,
            'Type': op_type,
            'Target': target,
            'Weight': weight,
            'Value': value,
            'ParamsPreview': params_preview,
        }
        for idx in range(1, max_cells + 1):
            row[f'C{idx}'] = cell_values[idx - 1]
        rows.append(row)

    csv_path = images_dir / 'merit_function.csv'
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(
                f,
                fieldnames=['Row', 'Type', 'Target', 'Weight', 'Value', 'ParamsPreview'] + [f'C{i}' for i in range(1, max_cells + 1)],
            )
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        return False, None, f"已读取 MFE，但写入 CSV 失败：{e}"

    img_path = images_dir / 'merit_function_editor.png'
    try:
        preview_rows = rows[:60]
        font_title = try_load_font(30)
        font_header = try_load_font(22)
        font_body = try_load_font(20)
        font_small = try_load_font(18)

        columns = [
            ('Row', 70),
            ('Type', 170),
            ('Target', 150),
            ('Weight', 120),
            ('Value', 150),
            ('参数预览', 1060),
        ]
        left = 40
        top = 40
        row_h = 32
        info_h = 120
        table_w = sum(w for _, w in columns) + left * 2
        table_rows_h = (len(preview_rows) + 1) * row_h
        footer_h = 90
        img_w = max(1760, table_w)
        img_h = top + 54 + info_h + table_rows_h + footer_h

        img = Image.new('RGB', (img_w, img_h), 'white')
        draw = ImageDraw.Draw(img)

        draw.text((left, top), '评价函数总览（清晰预览版）', fill='black', font=font_title)
        meta_y = top + 52
        try:
            merit_text = '未计算' if merit_value is None else f"{float(merit_value):.6g}"
        except Exception:
            merit_text = str(merit_value)
        draw.text((left, meta_y), f"操作数总数：{operand_count}", fill='black', font=font_header)
        draw.text((left + 320, meta_y), f"Merit Function：{merit_text}", fill='black', font=font_header)
        draw.text((left, meta_y + 38), '说明：图片只展示前 60 行预览；完整内容请查看同目录下的 merit_function.csv', fill='black', font=font_small)
        draw.text((left, meta_y + 68), f"CSV 文件：{csv_path.name}", fill='black', font=font_small)

        table_top = top + 54 + info_h
        x = left
        header_fill = (240, 240, 240)
        draw.rectangle([left, table_top, img_w - left, table_top + row_h], fill=header_fill, outline='black', width=1)
        for col_name, col_w in columns:
            draw.line((x, table_top, x, table_top + row_h + len(preview_rows) * row_h), fill='black', width=1)
            draw.text((x + 8, table_top + 5), col_name, fill='black', font=font_header)
            x += col_w
        draw.line((x, table_top, x, table_top + row_h + len(preview_rows) * row_h), fill='black', width=1)

        for ridx, row in enumerate(preview_rows):
            y0 = table_top + row_h + ridx * row_h
            y1 = y0 + row_h
            if ridx % 2 == 0:
                draw.rectangle([left, y0, img_w - left, y1], fill=(252, 252, 252))
            x = left
            values = [
                str(row['Row']),
                _truncate_text(row['Type'], 14),
                _truncate_text(row['Target'], 12),
                _truncate_text(row['Weight'], 10),
                _truncate_text(row['Value'], 12),
                _truncate_text(row['ParamsPreview'], 90),
            ]
            for (_, col_w), value in zip(columns, values):
                draw.rectangle([x, y0, x + col_w, y1], outline=(210, 210, 210), width=1)
                draw.text((x + 8, y0 + 5), value, fill='black', font=font_body)
                x += col_w

        footer_y = table_top + row_h + len(preview_rows) * row_h + 18
        if operand_count > len(preview_rows):
            draw.text((left, footer_y), f"其余 {operand_count - len(preview_rows)} 行未在图片中展开。", fill='black', font=font_small)
        else:
            draw.text((left, footer_y), '全部操作数均已展示在图片中。', fill='black', font=font_small)

        img.save(img_path)
        return True, img_path, f"已生成清晰版评价函数图片；完整表格见 {csv_path}"
    except Exception as e:
        return False, None, f"已写出 CSV，但生成评价函数图片失败：{e}"


def restore_lens_data_editor_view(main_hwnd):
    try:
        from pywinauto import Application
    except Exception:
        return False, "pywinauto 未安装，跳过恢复 LDE 视图"

    try:
        app = Application(backend="uia").connect(handle=main_hwnd)
        win = app.window(handle=main_hwnd)
        force_activate(main_hwnd)
        time.sleep(0.5)

        def click_by_name(names):
            wanted = [n.lower() for n in names]
            for e in win.descendants():
                try:
                    name = (e.window_text() or "").strip()
                    if name and name.lower() in wanted:
                        e.click_input()
                        time.sleep(0.5)
                        return True
                except Exception:
                    pass
            return False

        ok_tab = click_by_name(["Setup", "设置"])
        ok_btn = click_by_name(["Lens Data Editor", "LDE", "镜头数据编辑器", "镜头数据"])
        return (ok_tab or ok_btn), f"restore setup={ok_tab}, lde={ok_btn}"
    except Exception as e:
        return False, str(e)


def close_all_non_main_windows(main_hwnd):
    main_pid = get_window_pid(main_hwnd)
    if not main_pid:
        return []

    closed_titles = []
    items = enum_top_windows_for_pid(main_pid)
    iterable = items.items() if hasattr(items, 'items') else []

    for hwnd, info in iterable:
        if hwnd == main_hwnd:
            continue
        if not is_window_visible(hwnd):
            continue

        title = (info or {}).get("title", "") if isinstance(info, dict) else str(info or "")
        title_lower = title.lower()
        if not title_lower:
            continue
        if any(key in title_lower for key in ["programming", "python", "interactive extension", "lens data editor"]):
            continue

        try:
            force_close_window(hwnd)
            closed_titles.append(title)
        except Exception:
            pass
    return closed_titles


def write_version_log_md(run_dir: Path, run_date: str, zmx_file: str, export_folder: str, graph_overview_name: str = "图形总览"):
    version_log_path = run_dir / "版本日志.md"
    content = f"""---
tags:
  - zemax
  - 版本笔记
project: 
version: 
date: {run_date}
design_stage: 初始结构
score:
keywords:
  -
---


## 1. 基本信息
- 日期：{run_date}
- 版本号：
- 简介：
- 上一版本：
- 当前阶段：初始结构 / 粗优化 / 像差平衡 / 定稿前检查

---

## 2. 本次目标

### 2.1 这次想解决什么
1.
2.
3.

### 2.2 本次重点关注指标
- EFL：
- NA / F#：
- 视场：
- RMS Spot：
- MTF：
- 畸变：
- 场曲：
- 总长：
- 其他：

---

## 3. 本次改动记录

### 3.1 结构改动
- 改了哪些面：
- 改了哪些参数：
- 是否调整光阑位置：
- 是否换玻璃：
- 是否新增约束：

### 3.2 优化设置改动
- 是否修改 Merit Function：是 / 否
- 新增操作数：
- 删除操作数：
- 权重调整：
- 优化方式：局部优化 / 全局优化 / 手动试参

---

## 4. 导出结果

[[{graph_overview_name}]]


---

## 5. 结果速记

### 5.1 直接观察
- 中心像质：
- 边缘像质：
- 最差视场：
- 最差波长：
- 结构看起来是否合理：
- 有没有明显异常：

### 5.2 指标记录
- 中心 RMS：
- 边缘 RMS：
- 关键频率下 MTF：
- 最大畸变：
- 场曲情况：
- 与上一版相比：更好 / 更差 / 不明显

---

## 6. 分析判断

### 6.1 当前主要问题
1.
2.
3.

### 6.2 问题可能来自哪里
- 更像是哪类像差主导：
- 可能关联的面或参数：
- 为什么这样判断：

### 6.3 对当前版本的总体评价
- 这个版本的优点：
- 这个版本的缺点：
- 是否值得继续沿这个方向优化：是 / 否 / 观察后再定

---

## 7. 与上一版对比
- 上一版本：[[ ]]
- 这次变好的地方：
- 这次变差的地方：
- 可能原因：
- 是否保留本版本：保留 / 暂存 / 废弃

---

## 8. 下一步思路

### 方案A 
- 改动：
- 目标：
- 预期收益：
- 风险：

### 方案B 
- 改动：
- 目标：
- 预期收益：
- 风险：

### 方案C 
- 改动：
- 目标：
- 预期收益：
- 风险：

---

## 9. 一句话结论
>[!tip] 本版本结论：
>

"""
    version_log_path.write_text(content, encoding='utf-8')
    return version_log_path


def main():
    print("=== Zemax 原生图全屏保存脚本 v19（发布版）开始 ===")
    print("请先确保：")
    print("1. OpticStudio 已打开")
    print("2. 目标镜头文件已打开")
    print("3. Programming -> Interactive Extension -> Python 已开启")
    print("4. 运行时尽量不要手动切窗口")

    export_root = Path(r"D:\Zemax-PythonFiles\study\01")
    print(f"导出总目录固定为：{export_root}")
    export_root.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = export_root / ts
    images_dir = run_dir / "images"
    run_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    ZOSAPI, app, system = connect_interactive_extension(0)
    current_file = str(system.SystemFile)
    main_hwnd, main_title, pid = get_opticstudio_main_hwnd_and_pid()
    print(f"OpticStudio 主窗口：{main_title}")
    print(f"PID：{pid}")

    analysis_plan = [
        {"title": "Cross Section", "enums": ["Draw2D", "CrossSection"], "file": "cross_section.png", "keywords": ["cross section", "2d layout"]},
        {"title": "FFT MTF", "enums": ["FftMtf"], "file": "fft_mtf.png", "keywords": ["fft mtf"]},
        {"title": "Standard Spot Diagram", "enums": ["StandardSpot", "SpotDiagram"], "file": "spot_diagram.png", "keywords": ["spot diagram"]},
        {"title": "Seidel Diagram", "enums": ["SeidelDiagram", "SeidelCoefficients", "Seidel"], "file": "seidel_diagram.png", "keywords": ["seidel"]},
        {"title": "Field Curvature And Distortion", "enums": ["FieldCurvatureAndDistortion"], "file": "field_curvature_distortion.png", "keywords": ["field curv", "distortion"]},
        {"title": "Ray Fan", "enums": ["RayFan"], "file": "ray_fan.png", "keywords": ["ray fan"]},
        {"title": "Full Field Aberration", "enums": ["FullFieldAberration"], "file": "full_field_aberration.png", "keywords": ["full field aberration"]},
    ]

    results = []
    opened = []
    used_hwnds = set()

    for item in analysis_plan:
        print(f"\n开始处理：{item['title']}")
        try:
            before = enum_top_windows_for_pid(pid)
            before_hwnds = set(before.keys())

            analysis, enum_name = open_analysis(system, ZOSAPI, item["title"], item["enums"])
            opened.append(analysis)
            print(f"  已打开分析窗口，枚举名：{enum_name}")
            time.sleep(0.35)

            best, new_candidates = find_new_analysis_window(pid, before_hwnds, timeout=3.5)
            detect_mode = "new_window"

            if best is None:
                best, kw_candidates = find_window_by_keywords(pid, item["keywords"], exclude_hwnds=used_hwnds)
                detect_mode = "keyword_fallback"
                new_candidates = kw_candidates

            if best is None:
                raise RuntimeError("未找到分析窗口。建议先手动关闭旧分析窗口后重试。")

            hwnd = best["hwnd"]
            used_hwnds.add(hwnd)
            print(f"  命中窗口：hwnd={hwnd}, mode={detect_mode}, title={best['title']}, rect={best['rect']}")

            force_activate(hwnd)
            rect_after_move = move_resize_to_primary(hwnd)
            click_center_of_window(hwnd)
            time.sleep(0.35)
            rect = get_window_rect(hwnd)
            if rect is None:
                rect = rect_after_move
            if rect is None:
                raise RuntimeError("窗口矩形读取失败")

            tries = []
            final_ok = False
            chosen = None
            chosen_mean = None
            chosen_ratio = None
            out_png = images_dir / item["file"]
            last_img = None

            for method_name, img in iter_capture_bbox(rect):
                last_img = img
                black, mean_val, ratio = is_almost_black(img)
                tries.append(f"{method_name}:mean={mean_val:.2f},ratio={ratio:.4f},size={img.size[0]}x{img.size[1]}")
                if not black and not final_ok:
                    img.save(out_png)
                    final_ok = True
                    chosen = method_name
                    chosen_mean = mean_val
                    chosen_ratio = ratio
                    break

            if not final_ok:
                if last_img is not None:
                    last_img.save(out_png)
                status = "疑似黑图"
                note = f"所有后端都偏黑；检测方式={detect_mode}"
                print("  警告：仍疑似黑图")
            else:
                status = "成功"
                note = f"检测方式={detect_mode}；后端={chosen}, mean={chosen_mean:.2f}, ratio={chosen_ratio:.4f}"
                print(f"  已保存：{out_png}")
                print(f"  后端：{chosen}，mean={chosen_mean:.2f}，ratio={chosen_ratio:.4f}")

            cand_dump = []
            for c in new_candidates[:6]:
                cand_dump.append(f"hwnd={c['hwnd']} title={c['title']} rect={c['rect']}")

            results.append({
                "title": item["title"],
                "status": status,
                "enum": enum_name,
                "file": out_png.name,
                "path": str(out_png),
                "note": note,
                "tries": " ; ".join(tries),
                "cand": " || ".join(cand_dump) if cand_dump else "-",
            })
        except Exception as e:
            print(f"  失败：{e}")
            results.append({
                "title": item["title"],
                "status": "失败",
                "enum": "-",
                "file": "未生成",
                "path": "",
                "note": str(e),
                "tries": "-",
                "cand": "-",
            })

    extra_files = []
    extra_notes = []

    try:
        lens_info = export_lens_data_csv(system, run_dir / "lens_data.csv")
        extra_files.append(lens_info["path"])
        extra_notes.append(f"已保存镜头参数 CSV：{lens_info['path'].name}（共 {lens_info['count']} 面）")
    except Exception as e:
        extra_notes.append(f"镜头参数 CSV 导出失败：{e}")

    try:
        merit_csv = export_merit_function_csv(system, run_dir)
        extra_files.append(merit_csv)
        extra_notes.append(f"已保存评价函数 CSV：{merit_csv.name}")
    except Exception as e:
        extra_notes.append(f"评价函数 CSV 导出失败：{e}")

    report_ok = False
    try:
        report_files, report_notes = export_system_report_files(system, ZOSAPI, run_dir, app_hwnd=main_hwnd)
        if report_files:
            report_ok = True
            extra_files.extend(report_files)
        extra_notes.extend(report_notes if report_notes else [])
    except Exception as e:
        extra_notes.append(f"系统数据报告导出失败：{e}")

    try:
        created_files, created_notes = export_system_data_files(system, run_dir)
        for p in created_files:
            extra_files.append(p)
        if created_notes:
            extra_notes.extend(created_notes)
    except Exception as e:
        extra_notes.append(f"系统数据附加导出失败：{e}")

    exported_paths = {Path(item["path"]).stem: Path(item["path"]) for item in results if item.get("path") and Path(item["path"]).exists()}
    ordered_preview_paths = [
        exported_paths.get("cross_section"),
        exported_paths.get("fft_mtf"),
        exported_paths.get("spot_diagram"),
        exported_paths.get("seidel_diagram"),
        exported_paths.get("field_curvature_distortion"),
        exported_paths.get("ray_fan"),
        exported_paths.get("full_field_aberration"),
    ]
    ordered_preview_paths = [p for p in ordered_preview_paths if p is not None]

    overview = []
    overview.append("# 图形总览")
    overview.append("")
    overview.append("## 预览")
    overview.append("")
    for p in ordered_preview_paths:
        if not p:
            continue
        overview.append(f"### {p.stem}")
        overview.append(f"![[images/{p.name}]]")
        overview.append("")
    (run_dir / "图形总览.md").write_text("\n".join(overview) + "\n", encoding="utf-8")

    run_date = ts.split("_")[0]
    snapshot_zmx_name = f"{ts}.zmx"
    version_log_md = write_version_log_md(
        run_dir=run_dir,
        run_date=run_date,
        zmx_file=snapshot_zmx_name,
        export_folder=str(run_dir),
        graph_overview_name="图形总览",
    )

"""
    try:
        restored, restore_note = restore_lens_data_editor_view(main_hwnd)
    except Exception as e:
        restored, restore_note = False, f"恢复 LDE 视图失败：{e}"

    try:
        closed_titles = close_all_non_main_windows(main_hwnd)
    except Exception as e:
        closed_titles = []
        print(f"关闭非主窗口时跳过：{e}")

    if restored:
        print(f"已尝试恢复到镜头数据编辑界面：{restore_note}")
    else:
        print(f"未恢复 LDE 视图：{restore_note}")
    print(f"已关闭非主窗口数量：{len(closed_titles)}")
    for t in closed_titles:
        print(f"  - {t}")

    print("\n=== 完成 ===")
    print(f"导出目录：{run_dir}")
    print(f"图片目录：{images_dir}")
    print(f"图形总览：{run_dir / '图形总览.md'}")
    print(f"版本日志：{version_log_md}")
"""

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("程序运行失败：")
        print(traceback.format_exc())
