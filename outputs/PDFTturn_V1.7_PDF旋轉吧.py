import importlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


APP_NAME = "PDF旋轉吧"
APP_CODE = "PDFTturn"
APP_VERSION = "V1.7"


CORE_PACKAGES = {
    "fitz": "PyMuPDF",
    "PIL": "Pillow",
}
OPTIONAL_PACKAGES = {"tkinterdnd2": "tkinterdnd2"}


def check_dependencies():
    missing = []
    for import_name, package_name in CORE_PACKAGES.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(package_name)

    optional_missing = []
    for import_name, package_name in OPTIONAL_PACKAGES.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            optional_missing.append(package_name)

    if not missing and not optional_missing:
        return True

    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()

    if optional_missing and not missing:
        names = "\n".join(f"- {name}" for name in optional_missing)
        install_optional = messagebox.askyesno(
            "可選套件",
            f"拖曳 PDF 功能需要以下套件：\n\n{names}\n\n是否要自動安裝？\n選擇「否」仍可使用按鈕選取檔案。",
        )
        if install_optional:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", *optional_missing])
            except Exception as exc:
                messagebox.showwarning("安裝失敗", f"拖曳套件安裝失敗，將以一般模式啟動：\n{exc}")
            else:
                messagebox.showinfo("安裝完成", "套件已安裝完成，請重新啟動程式以啟用拖曳。")
                root.destroy()
                return False
        root.destroy()
        return True

    names = "\n".join(f"- {name}" for name in missing)
    install = messagebox.askyesno(
        "缺少套件",
        f"程式缺少以下套件：\n\n{names}\n\n是否要自動安裝？",
    )
    if not install:
        messagebox.showwarning("無法啟動", "缺少必要套件，部分功能無法使用。")
        root.destroy()
        return False

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    except Exception as exc:
        messagebox.showerror("安裝失敗", f"自動安裝失敗：\n{exc}")
        root.destroy()
        return False

    messagebox.showinfo("安裝完成", "套件已安裝完成，請重新啟動程式。")
    root.destroy()
    return False


if not check_dependencies():
    sys.exit(0)


import fitz
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None


def file_size_text(path):
    if not path or not os.path.exists(path):
        return "-"
    size = os.path.getsize(path)
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024


def parse_drop_files(data):
    files = []
    current = []
    in_brace = False
    for char in data:
        if char == "{":
            in_brace = True
            current = []
        elif char == "}":
            in_brace = False
            files.append("".join(current))
            current = []
        elif char == " " and not in_brace:
            if current:
                files.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        files.append("".join(current))
    return [path for path in files if path.lower().endswith(".pdf")]


def default_save_path(source_path, suffix):
    path = Path(source_path)
    return str(path.with_name(f"{path.stem}{suffix}.pdf"))


def make_thumbnail(pdf_path, page_index=0, width=150, rotation=0, mark=None):
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        zoom = max(width / page.rect.width, 0.1)
        matrix = fitz.Matrix(zoom, zoom).prerotate(rotation)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        image.thumbnail((width, int(width * 1.45)), Image.Resampling.LANCZOS)
        if mark:
            image = image.convert("RGBA")
            overlay = Image.new("RGBA", image.size, mark)
            image = Image.alpha_composite(image, overlay)
        return ImageTk.PhotoImage(image)
    finally:
        doc.close()


class ScrollArea(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, bg="#f6f7f8", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", self._sync_scroll_region)
        self.canvas.bind("<Configure>", self._sync_width)

    def _sync_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)


class BaseTab(ttk.Frame):
    def __init__(self, app, notebook):
        super().__init__(notebook, padding=12)
        self.app = app
        self.thumb_size = tk.IntVar(value=150)
        self.thumbs = []
        self.drag_from = None
        self.drag_cards = []

    def enable_drop(self, widget, callback):
        if DND_FILES is None:
            return
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda event: callback(parse_drop_files(event.data)))

    def clear_frame(self, frame):
        for child in frame.winfo_children():
            child.destroy()
        self.thumbs.clear()
        self.drag_cards = []

    def choose_pdf(self):
        initialdir = self.app.last_dir if self.app.last_dir else os.getcwd()
        path = filedialog.askopenfilename(
            title="選取 PDF",
            initialdir=initialdir,
            filetypes=[("PDF files", "*.pdf")],
        )
        if path:
            self.app.last_dir = os.path.dirname(path)
        return path

    def choose_pdfs(self):
        initialdir = self.app.last_dir if self.app.last_dir else os.getcwd()
        paths = filedialog.askopenfilenames(
            title="選取 PDF",
            initialdir=initialdir,
            filetypes=[("PDF files", "*.pdf")],
        )
        if paths:
            self.app.last_dir = os.path.dirname(paths[0])
        return list(paths)

    def bind_drag_sort(self, widget, pos):
        widget.bind("<ButtonPress-1>", lambda event, p=pos: self.start_drag(event, p))
        widget.bind("<ButtonRelease-1>", self.end_drag)

    def start_drag(self, _event, pos):
        self.drag_from = pos

    def find_drop_position(self, event):
        if not self.drag_cards:
            return None
        x_root = event.x_root
        y_root = event.y_root
        nearest = None
        nearest_distance = None
        for pos, card in enumerate(self.drag_cards):
            left = card.winfo_rootx()
            top = card.winfo_rooty()
            right = left + card.winfo_width()
            bottom = top + card.winfo_height()
            if left <= x_root <= right and top <= y_root <= bottom:
                return pos
            center_x = left + card.winfo_width() / 2
            center_y = top + card.winfo_height() / 2
            distance = (center_x - x_root) ** 2 + (center_y - y_root) ** 2
            if nearest_distance is None or distance < nearest_distance:
                nearest = pos
                nearest_distance = distance
        return nearest

    def move_item(self, items, from_pos, to_pos):
        if from_pos is None or to_pos is None or from_pos == to_pos:
            return False
        item = items.pop(from_pos)
        items.insert(to_pos, item)
        return True


class RotateTab(BaseTab):
    def __init__(self, app, notebook):
        super().__init__(app, notebook)
        self.pdf_path = None
        self.pages = []
        self._build()

    def _build(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="開啟 PDF", command=self.open_pdf).pack(side="left")
        ttk.Button(toolbar, text="全部左轉", command=lambda: self.rotate_all(-90)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="全部右轉", command=lambda: self.rotate_all(90)).pack(side="left")
        ttk.Button(toolbar, text="全部重設", command=self.reset_all).pack(side="left", padx=4)
        ttk.Label(toolbar, text="縮圖").pack(side="left", padx=(16, 4))
        ttk.Scale(toolbar, from_=90, to=230, variable=self.thumb_size, command=lambda _v: self.render()).pack(side="left")
        ttk.Button(toolbar, text="輸出修改後 PDF", command=self.export_pdf).pack(side="right")
        self.title = ttk.Label(self, text="請開啟或拖曳 PDF 到此分頁")
        self.title.pack(anchor="w", pady=(0, 8))
        self.area = ScrollArea(self)
        self.area.pack(fill="both", expand=True)
        self.enable_drop(self, self.load_drop)
        self.bind_all("<Control-MouseWheel>", self.zoom)

    def zoom(self, event):
        value = self.thumb_size.get() + (10 if event.delta > 0 else -10)
        self.thumb_size.set(max(90, min(230, value)))
        self.render()

    def open_pdf(self):
        path = self.choose_pdf()
        if path:
            self.load_pdf(path)

    def load_drop(self, paths):
        if paths:
            self.load_pdf(paths[0])

    def load_pdf(self, path):
        try:
            doc = fitz.open(path)
            count = doc.page_count
            doc.close()
        except Exception as exc:
            messagebox.showerror("開啟失敗", f"無法開啟 PDF：\n{exc}")
            return
        self.pdf_path = path
        self.pages = [{"index": i, "rotation": 0} for i in range(count)]
        self.title.configure(text=f"{os.path.basename(path)} / {count} 頁")
        self.render()

    def render(self):
        self.clear_frame(self.area.content)
        if not self.pdf_path:
            return
        columns = max(1, self.winfo_width() // (self.thumb_size.get() + 48))
        for pos, item in enumerate(self.pages):
            card = ttk.Frame(self.area.content, padding=8)
            card.grid(row=pos // columns, column=pos % columns, padx=6, pady=6, sticky="n")
            self.drag_cards.append(card)
            thumb = make_thumbnail(self.pdf_path, item["index"], self.thumb_size.get(), item["rotation"])
            self.thumbs.append(thumb)
            label = ttk.Label(card, image=thumb)
            label.pack()
            self.bind_drag_sort(label, pos)
            ttk.Label(card, text=f"第 {pos + 1} 頁 / {item['rotation'] % 360}°").pack(pady=(6, 4))
            buttons = ttk.Frame(card)
            buttons.pack()
            ttk.Button(buttons, text="左轉", width=6, command=lambda p=pos: self.rotate_one(p, -90)).pack(side="left")
            ttk.Button(buttons, text="右轉", width=6, command=lambda p=pos: self.rotate_one(p, 90)).pack(side="left", padx=2)
            ttk.Button(buttons, text="重設", width=6, command=lambda p=pos: self.reset_one(p)).pack(side="left")

    def end_drag(self, event):
        to_pos = self.find_drop_position(event)
        moved = self.move_item(self.pages, self.drag_from, to_pos)
        self.drag_from = None
        if moved:
            self.render()

    def rotate_one(self, pos, degrees):
        self.pages[pos]["rotation"] = (self.pages[pos]["rotation"] + degrees) % 360
        self.render()

    def reset_one(self, pos):
        self.pages[pos]["rotation"] = 0
        self.render()

    def rotate_all(self, degrees):
        for item in self.pages:
            item["rotation"] = (item["rotation"] + degrees) % 360
        self.render()

    def reset_all(self):
        for item in self.pages:
            item["rotation"] = 0
        self.render()

    def export_pdf(self):
        if not self.pdf_path:
            messagebox.showwarning("尚未開啟", "請先開啟 PDF。")
            return
        output = filedialog.asksaveasfilename(
            title="另存新檔",
            defaultextension=".pdf",
            initialfile=os.path.basename(default_save_path(self.pdf_path, "_r")),
            initialdir=os.path.dirname(self.pdf_path),
            filetypes=[("PDF files", "*.pdf")],
        )
        if not output:
            return
        source = fitz.open(self.pdf_path)
        result = fitz.open()
        try:
            for item in self.pages:
                result.insert_pdf(source, from_page=item["index"], to_page=item["index"])
                page = result[-1]
                page.set_rotation((page.rotation + item["rotation"]) % 360)
            result.save(output, garbage=4, deflate=True)
            messagebox.showinfo("完成", f"已輸出：\n{output}")
        except Exception as exc:
            messagebox.showerror("輸出失敗", str(exc))
        finally:
            result.close()
            source.close()


class CompressTab(BaseTab):
    def __init__(self, app, notebook):
        super().__init__(app, notebook)
        self.pdf_path = None
        self.quality = tk.IntVar(value=70)
        self.original_size = tk.StringVar(value="原有檔案大小\n-")
        self.estimated_size = tk.StringVar(value="預計壓縮後大小\n-")
        self.actual_size = tk.StringVar(value="壓縮後實際大小\n-")
        self._build()

    def _build(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="開啟 PDF", command=self.open_pdf).pack(side="left")
        ttk.Label(toolbar, text="壓縮比例").pack(side="left", padx=(16, 6))
        ttk.Scale(toolbar, from_=35, to=95, variable=self.quality, command=lambda _v: self.update_estimate()).pack(side="left", fill="x", expand=True)
        ttk.Button(toolbar, text="輸出壓縮PDF", command=self.export_pdf).pack(side="right", padx=(10, 0))
        self.info = ttk.Label(self, text="請開啟或拖曳 PDF 到此分頁")
        self.info.pack(anchor="w", pady=(0, 12))
        stats = ttk.Frame(self)
        stats.pack(fill="x", pady=(0, 12))
        for variable in (self.original_size, self.estimated_size, self.actual_size):
            ttk.Label(
                stats,
                textvariable=variable,
                style="Stat.TLabel",
                anchor="center",
                justify="center",
                relief="raised",
                borderwidth=2,
            ).pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.enable_drop(self, self.load_drop)

    def open_pdf(self):
        path = self.choose_pdf()
        if path:
            self.load_pdf(path)

    def load_drop(self, paths):
        if paths:
            self.load_pdf(paths[0])

    def load_pdf(self, path):
        self.pdf_path = path
        self.actual_size.set("壓縮後實際大小\n-")
        self.update_estimate()

    def update_estimate(self):
        if not self.pdf_path:
            return
        original = os.path.getsize(self.pdf_path)
        quality = self.quality.get()
        factor = max(0.20, quality / 115)
        estimate = original * factor
        self.info.configure(text=f"{os.path.basename(self.pdf_path)} / 品質 {quality}")
        self.original_size.set(f"原有檔案大小\n{file_size_text(self.pdf_path)}")
        self.estimated_size.set(f"預計壓縮後大小\n{estimate / 1024 / 1024:.1f} MB")

    def export_pdf(self):
        if not self.pdf_path:
            messagebox.showwarning("尚未開啟", "請先開啟 PDF。")
            return
        output = filedialog.asksaveasfilename(
            title="另存新檔",
            defaultextension=".pdf",
            initialfile=os.path.basename(default_save_path(self.pdf_path, "_comp")),
            initialdir=os.path.dirname(self.pdf_path),
            filetypes=[("PDF files", "*.pdf")],
        )
        if not output:
            return
        quality = self.quality.get()
        zoom = 0.9 + (quality / 100)
        source = fitz.open(self.pdf_path)
        result = fitz.open()
        try:
            for page in source:
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                temp = Path(output).with_suffix(".jpg")
                img.save(temp, "JPEG", quality=quality, optimize=True)
                rect = fitz.Rect(0, 0, page.rect.width, page.rect.height)
                new_page = result.new_page(width=page.rect.width, height=page.rect.height)
                new_page.insert_image(rect, filename=str(temp))
                temp.unlink(missing_ok=True)
            result.save(output, garbage=4, deflate=True)
            self.actual_size.set(f"壓縮後實際大小\n{file_size_text(output)}")
            messagebox.showinfo("完成", f"已輸出：\n{output}\n\n實際大小：{file_size_text(output)}")
        except Exception as exc:
            messagebox.showerror("輸出失敗", str(exc))
        finally:
            result.close()
            source.close()


class MergeTab(BaseTab):
    def __init__(self, app, notebook):
        super().__init__(app, notebook)
        self.files = []
        self._build()

    def _build(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="加入 PDF", command=self.add_files).pack(side="left")
        ttk.Button(toolbar, text="清空", command=self.clear).pack(side="left", padx=4)
        ttk.Button(toolbar, text="輸出合併 PDF", command=self.export_pdf).pack(side="right")
        self.title = ttk.Label(self, text="請加入或拖曳 PDF 到此分頁")
        self.title.pack(anchor="w", pady=(0, 8))
        self.area = ScrollArea(self)
        self.area.pack(fill="both", expand=True)
        self.enable_drop(self, self.load_drop)

    def add_files(self):
        self.load_drop(self.choose_pdfs())

    def load_drop(self, paths):
        self.files.extend(paths)
        self.render()

    def clear(self):
        self.files = []
        self.render()

    def render(self):
        self.clear_frame(self.area.content)
        self.title.configure(text=f"合併清單 / {len(self.files)} 個檔案")
        for pos, path in enumerate(self.files):
            card = ttk.Frame(self.area.content, padding=8)
            card.grid(row=pos // 4, column=pos % 4, padx=6, pady=6, sticky="n")
            self.drag_cards.append(card)
            thumb = make_thumbnail(path, 0, 150)
            self.thumbs.append(thumb)
            label = ttk.Label(card, image=thumb)
            label.pack()
            self.bind_drag_sort(label, pos)
            ttk.Label(card, text=f"{pos + 1}. {os.path.basename(path)}", wraplength=160).pack(pady=(6, 4))
            ttk.Button(card, text="移除", command=lambda p=pos: self.remove(p)).pack()

    def end_drag(self, event):
        to_pos = self.find_drop_position(event)
        moved = self.move_item(self.files, self.drag_from, to_pos)
        self.drag_from = None
        if moved:
            self.render()

    def remove(self, pos):
        self.files.pop(pos)
        self.render()

    def export_pdf(self):
        if not self.files:
            messagebox.showwarning("沒有檔案", "請先加入 PDF。")
            return
        name = f"PDF_mer_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        output = filedialog.asksaveasfilename(
            title="另存新檔",
            defaultextension=".pdf",
            initialfile=name,
            initialdir=os.path.dirname(self.files[0]),
            filetypes=[("PDF files", "*.pdf")],
        )
        if not output:
            return
        result = fitz.open()
        try:
            for path in self.files:
                doc = fitz.open(path)
                result.insert_pdf(doc)
                doc.close()
            result.save(output, garbage=4, deflate=True)
            messagebox.showinfo("完成", f"已輸出：\n{output}")
        except Exception as exc:
            messagebox.showerror("輸出失敗", str(exc))
        finally:
            result.close()


class EditTab(BaseTab):
    def __init__(self, app, notebook):
        super().__init__(app, notebook)
        self.pages = []
        self.base_path = None
        self._build()

    def _build(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="開啟 PDF", command=self.open_pdf).pack(side="left")
        ttk.Button(toolbar, text="插入 PDF", command=self.insert_pdf).pack(side="left", padx=4)
        ttk.Button(toolbar, text="輸出編輯 PDF", command=self.export_pdf).pack(side="right")
        self.title = ttk.Label(self, text="請開啟 PDF；拖曳其他 PDF 可插入頁面")
        self.title.pack(anchor="w", pady=(0, 8))
        self.area = ScrollArea(self)
        self.area.pack(fill="both", expand=True)
        self.enable_drop(self, self.load_drop)

    def open_pdf(self):
        path = self.choose_pdf()
        if path:
            self.load_base(path)

    def insert_pdf(self):
        self.load_drop(self.choose_pdfs())

    def load_drop(self, paths):
        if not paths:
            return
        if not self.base_path:
            self.load_base(paths[0])
            for path in paths[1:]:
                self.add_insert(path)
        else:
            for path in paths:
                self.add_insert(path)
        self.render()

    def load_base(self, path):
        try:
            doc = fitz.open(path)
            count = doc.page_count
            doc.close()
        except Exception as exc:
            messagebox.showerror("開啟失敗", str(exc))
            return
        self.base_path = path
        self.pages = [{"path": path, "index": i, "inserted": False, "delete": tk.BooleanVar(value=False)} for i in range(count)]
        self.render()

    def add_insert(self, path):
        try:
            doc = fitz.open(path)
            count = doc.page_count
            doc.close()
        except Exception as exc:
            messagebox.showerror("插入失敗", f"{path}\n{exc}")
            return
        for i in range(count):
            self.pages.append({"path": path, "index": i, "inserted": True, "delete": tk.BooleanVar(value=False)})

    def render(self):
        self.clear_frame(self.area.content)
        if not self.base_path:
            return
        self.title.configure(text=f"{os.path.basename(self.base_path)} / 目前 {len(self.pages)} 頁")
        for pos, item in enumerate(self.pages):
            color = (80, 160, 255, 70) if item["inserted"] else None
            if item["delete"].get():
                color = (255, 80, 80, 90)
            card = ttk.Frame(self.area.content, padding=8)
            card.grid(row=pos // 4, column=pos % 4, padx=6, pady=6, sticky="n")
            self.drag_cards.append(card)
            thumb = make_thumbnail(item["path"], item["index"], 150, mark=color)
            self.thumbs.append(thumb)
            label = ttk.Label(card, image=thumb)
            label.pack()
            self.bind_drag_sort(label, pos)
            ttk.Label(card, text=f"第 {pos + 1} 頁", wraplength=150).pack(pady=(6, 2))
            ttk.Checkbutton(card, text="刪除", variable=item["delete"], command=self.render).pack()

    def end_drag(self, event):
        to_pos = self.find_drop_position(event)
        moved = self.move_item(self.pages, self.drag_from, to_pos)
        self.drag_from = None
        if moved:
            self.render()

    def export_pdf(self):
        if not self.pages:
            messagebox.showwarning("尚未開啟", "請先開啟 PDF。")
            return
        output = filedialog.asksaveasfilename(
            title="另存新檔",
            defaultextension=".pdf",
            initialfile=os.path.basename(default_save_path(self.base_path, "_edit")),
            initialdir=os.path.dirname(self.base_path),
            filetypes=[("PDF files", "*.pdf")],
        )
        if not output:
            return
        result = fitz.open()
        open_docs = {}
        try:
            for item in self.pages:
                if item["delete"].get():
                    continue
                path = item["path"]
                if path not in open_docs:
                    open_docs[path] = fitz.open(path)
                result.insert_pdf(open_docs[path], from_page=item["index"], to_page=item["index"])
            if result.page_count == 0:
                messagebox.showwarning("沒有頁面", "全部頁面都被刪除，無法輸出。")
                return
            result.save(output, garbage=4, deflate=True)
            messagebox.showinfo("完成", f"已輸出：\n{output}")
        except Exception as exc:
            messagebox.showerror("輸出失敗", str(exc))
        finally:
            result.close()
            for doc in open_docs.values():
                doc.close()


class PDFTturnApp:
    def __init__(self):
        root_class = TkinterDnD.Tk if TkinterDnD else tk.Tk
        self.root = root_class()
        self.root.title(f"{APP_CODE} {APP_VERSION} - {APP_NAME}")
        self.root.geometry("1180x760")
        self.root.minsize(900, 620)
        self.last_dir = None
        self._style()
        self._build()

    def _style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Microsoft JhengHei UI", 10), background="#f6f7f8")
        style.configure("TFrame", background="#f6f7f8")
        style.configure("TLabel", background="#f6f7f8", foreground="#202124")
        style.configure("TButton", padding=(10, 5))
        style.configure("TNotebook", background="#f6f7f8", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 8))
        style.configure(
            "Stat.TLabel",
            background="#ffffff",
            foreground="#202124",
            font=("Microsoft JhengHei UI", 16, "bold"),
            padding=(18, 18),
        )

    def _build(self):
        header = ttk.Frame(self.root, padding=(16, 12))
        header.pack(fill="x")
        ttk.Label(header, text=f"{APP_NAME} {APP_VERSION}", font=("Microsoft JhengHei UI", 18, "bold")).pack(side="left")
        if DND_FILES is None:
            ttk.Label(header, text="拖曳套件尚未安裝，可使用按鈕選取 PDF").pack(side="right")
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        notebook.add(RotateTab(self, notebook), text="頁面移轉")
        notebook.add(CompressTab(self, notebook), text="壓縮檔案")
        notebook.add(MergeTab(self, notebook), text="頁面合併")
        notebook.add(EditTab(self, notebook), text="頁面編輯")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    PDFTturnApp().run()
