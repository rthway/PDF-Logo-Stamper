

# 📄 PDF Logo Stamper - Documentation

**Author**: Roshan Kumar Thapa  
**Description**: A user-friendly desktop GUI application to add a centered logo/image stamp to each page of a selected PDF.  
**Technologies Used**:

-   **Python 3**
    
-   **Tkinter** (GUI)
    
-   **PyMuPDF** (`fitz`) - for PDF manipulation
    
-   **Pillow** (`PIL`) - for image processing
    

----------

## 📦 Features

-   Select a PDF file to modify.
    
-   Select a logo/image to stamp on each page.
    
-   Customize the logo’s size (width & height).
    
-   Customize vertical position (Y-axis) from the bottom.
    
-   Save the modified PDF to a desired location.
    
-   Simple, intuitive GUI built using Tkinter.
    

----------


## 📁 Project Structure

```text
pdf_logo_stamper/
├── main.py                # Main application file
├── processed_logo.png     # Temporary file (created during runtime)

```

----------

## 🧠 How It Works

1.  **Image Loading**: Opens the selected image using Pillow and converts it to RGBA.
    
2.  **PDF Loading**: Opens the selected PDF using `fitz`.
    
3.  **Insertion Logic**:
    
    -   Calculates horizontal center of each page.
        
    -   Calculates Y-position using the user-defined bottom margin.
        
    -   Inserts the image using PyMuPDF's `insert_image` with overlay mode.
        
4.  **Saving**: The updated PDF is saved to the user-defined path.
    
5.  **Feedback**: Shows success or error message dialogs based on the result.
    

----------

## ⚙️ Function Breakdown

### `add_logo_stamp(...)`

Adds a logo/image to each page of the given PDF file.

**Parameters:**

-   `input_pdf_path (str)`: Path to the input PDF.
    
-   `output_pdf_path (str)`: Path where the output PDF will be saved.
    
-   `logo_path (str)`: Path to the logo image.
    
-   `logo_size (tuple)`: Dimensions (width, height) of the logo.
    
-   `bottom_margin (int)`: Y-coordinate position from bottom.
    

----------

### `select_file(entry)`

Handles file selection for PDFs and images, and updates the corresponding entry field.

----------

### `save_file(entry)`

Prompts user to choose a save location for the output PDF.

----------

### `run_process()`

Validates inputs, parses dimensions, and calls `add_logo_stamp()` to perform the stamping.

----------

## 🧰 Requirements

Install dependencies using pip:

```bash
pip install PyMuPDF Pillow

```

----------

## 🚀 How to Run

1.  Save the code to a file, e.g., `pdf_logo_stamper.py`
    
2.  Run the script:
    

```bash
python pdf_logo_stamper.py

```

3.  Use the GUI to select files and parameters.
    
4.  Click "Add Logo to PDF" to apply the stamp and generate the new PDF.
    

----------

## 🛠️ Customization Tips

-   **Change default logo size**:  
    Modify the default values set by `entry_width.insert(0, "200")` and `entry_height.insert(0, "100")`.
    
-   **Default margin**:  
    Adjust `entry_margin.insert(0, "750")` to your preferred position.
    

----------

## 🧹 Notes

-   A temporary file `processed_logo.png` is created each time for internal processing.
    
-   Make sure the logo image has a reasonable resolution for clear output.
    
-   The bottom margin assumes typical A4 vertical height (~842 points). Adjust as needed.
    

----------

## ✅ Example Use Case

You're a company wanting to watermark your reports. Use this app to:

-   Stamp your logo at the bottom of each page.
    
-   Maintain centralized branding without manually editing every page.
    

----------



## 🧱 Step-by-Step: Convert to `.exe` using PyInstaller
To compile your **PDF Logo Stamper** Python application into a `.exe` (executable file) for Windows, follow these steps using **PyInstaller**:

### ✅ 1. **Install PyInstaller**

If not already installed:

```bash
pip install pyinstaller

```

----------

### 📁 2. **Prepare Your Project Folder**

Ensure your folder contains:

```plaintext
pdf_logo_stamper/
├── pdf_logo_stamper.py       # Your main application script

```

> Optionally rename your main script to something simpler like `main.py`.

----------

### ⚙️ 3. **Create the Executable**

Open terminal (CMD or PowerShell) in the project folder and run:

```bash
pyinstaller --noconfirm --onefile --windowed pdf_logo_stamper.py

```

### Explanation of Flags:

-   `--noconfirm`: Overwrites any previous build without asking.
    
-   `--onefile`: Bundles everything into a single `.exe` file.
    
-   `--windowed`: Prevents a command prompt window from appearing when you run the `.exe` (used for GUI apps).
    

----------

### 📦 4. **Find Your `.exe`**

After compilation, you’ll get this folder structure:

```plaintext
pdf_logo_stamper/
├── dist/
│   └── pdf_logo_stamper.exe   ✅ Your executable file
├── build/
├── pdf_logo_stamper.spec

```

Your `.exe` is located in the `dist/` folder.

----------

## 🖼️ Optional: Add a Custom Icon

To add an icon to your app:

1.  Prepare a `.ico` file (e.g., `app_icon.ico`)
    
2.  Add `--icon` parameter:
    

```bash
pyinstaller --noconfirm --onefile --windowed --icon=app_icon.ico pdf_logo_stamper.py

```

----------

## ✅ Final Notes

-   Distribute the `.exe` in the `dist/` folder.
    
-   You don’t need Python installed on the target machine.
    
-   Test it on another PC to ensure it runs without missing dependencies.
    
