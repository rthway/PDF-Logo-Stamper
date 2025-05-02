"""
PDF Logo Stamper
Author: Roshan Kumar Thapa
Description: A simple desktop GUI app to add a centered logo stamp on each page of a PDF.
Technologies: Tkinter, PyMuPDF, Pillow
"""

import fitz  # PyMuPDF
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox


def add_logo_stamp(input_pdf_path, output_pdf_path, logo_path, logo_size=(200, 100), bottom_margin=750):
    try:
        pdf_doc = fitz.open(input_pdf_path)
        logo = Image.open(logo_path).convert("RGBA")
        logo_stream = "processed_logo.png"
        logo.save(logo_stream)

        for page in pdf_doc:
            page_width = page.rect.width
            logo_width, logo_height = logo_size
            x = (page_width - logo_width) / 2
            y = bottom_margin
            rect = fitz.Rect(x, y, x + logo_width, y + logo_height)
            page.insert_image(rect, filename=logo_stream, overlay=True)

        pdf_doc.save(output_pdf_path)
        pdf_doc.close()
        messagebox.showinfo("Success", f"Logo added and saved to:\n{output_pdf_path}")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred:\n{str(e)}")


def select_file(entry):
    path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf"), ("Image Files", "*.png;*.jpg;*.jpeg")])
    if path:
        entry.delete(0, tk.END)
        entry.insert(0, path)


def save_file(entry):
    path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Files", "*.pdf")])
    if path:
        entry.delete(0, tk.END)
        entry.insert(0, path)


def run_process():
    input_pdf = entry_pdf.get()
    output_pdf = entry_output.get()
    logo_path = entry_logo.get()

    try:
        width = int(entry_width.get())
        height = int(entry_height.get())
        bottom_margin = int(entry_margin.get())
    except ValueError:
        messagebox.showerror("Input Error", "Please enter valid numbers for width, height, and margin.")
        return

    if not input_pdf or not output_pdf or not logo_path:
        messagebox.showerror("Missing Input", "Please select all files.")
        return

    add_logo_stamp(input_pdf, output_pdf, logo_path, (width, height), bottom_margin)


# === GUI SETUP ===
root = tk.Tk()
root.title("PDF Logo Stamper -  Roshan Kumar Thapa")
root.geometry("500x400")

tk.Label(root, text="Input PDF:").pack()
entry_pdf = tk.Entry(root, width=50)
entry_pdf.pack()
tk.Button(root, text="Browse", command=lambda: select_file(entry_pdf)).pack()

tk.Label(root, text="Logo Image:").pack()
entry_logo = tk.Entry(root, width=50)
entry_logo.pack()
tk.Button(root, text="Browse", command=lambda: select_file(entry_logo)).pack()

tk.Label(root, text="Output PDF Path:").pack()
entry_output = tk.Entry(root, width=50)
entry_output.pack()
tk.Button(root, text="Save As", command=lambda: save_file(entry_output)).pack()

tk.Label(root, text="Logo Width:").pack()
entry_width = tk.Entry(root, width=10)
entry_width.insert(0, "200")
entry_width.pack()

tk.Label(root, text="Logo Height:").pack()
entry_height = tk.Entry(root, width=10)
entry_height.insert(0, "100")
entry_height.pack()

tk.Label(root, text="Bottom Margin (Y pos):").pack()
entry_margin = tk.Entry(root, width=10)
entry_margin.insert(0, "750")
entry_margin.pack()

tk.Button(root, text="Add Logo to PDF", command=run_process, bg="green", fg="white", padx=10, pady=5).pack(pady=10)

root.mainloop()
