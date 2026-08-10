# CHAPTER 3
# SYSTEM CONFIGURATION

This chapter describes the minimum and recommended hardware and software configurations required to run and maintain the **AI-Enabled Insurance Claim Management System (ClaimIQ)** in both development and production environments.

## 3.1. HARDWARE CONFIGURATION

To ensure smooth operation of the Django application, database transactions, Machine Learning model training, and heavy Optical Character Recognition (OCR) processing, the following hardware specifications are defined:

### 3.1.1. Development/Client En
vironment (Minimum)
* **Processor**     : Intel(R) Core(TM) i5/i7 (4th Gen or above) / AMD Ryzen 5 (or equivalent) @ 2.0 GHz
* **RAM**           : 8 GB DDR4
* **Hard Disk**     : 256 GB SSD (Solid State Drive recommended for fast Model loading)
* **Input Devices** : Standard Keyboard, Optical Mouse
* **Output Devices**: Monitor (Resolution: 1920 x 1080 recommended for administrative dashboards)

### 3.1.2. Production Server Environment (Recommended)
* **Processor**     : Quad-Core Intel Xeon or AMD EPYC Processor (or 2+ vCPUs on AWS/Azure cloud)
* **RAM**           : 16 GB DDR4 (To support concurrent execution of PaddleOCR and ML pipelines)
* **Hard Disk**     : 100 GB NVMe SSD or higher (for fast read/write of logs, database entries, and media files)

---

## 3.2. SOFTWARE CONFIGURATION

The system configuration relies on a robust open-source ecosystem consisting of Python, the Django framework, Scikit-learn, and state-of-the-art OCR tools. The specific software stack details are:

* **Operating System**        : Windows 10/11 (64-bit) / Linux (Ubuntu 20.04/22.04 LTS) / macOS (12.0+)
* **Web Browser**               : Google Chrome (Version 110+), Mozilla Firefox (Version 110+), or Microsoft Edge
* **IDE / Editor**              : Visual Studio Code (VS Code) / PyCharm (Community or Professional Edition)
* **User Interface Design**     : HTML5, CSS3, JavaScript (ES6+), Bootstrap 5 framework (for glassmorphic dark-theme responsiveness)
* **Backend Web Framework**     : Django Web Framework (Version 4.2 LTS / 5.0)
* **Development Server**         : Django WSGI Development Server
* **Production Web Server**      : Gunicorn / Uvicorn with Nginx (Reverse Proxy)
* **Server-Side Language**      : Python 3.11.x
* **Database (Development)**    : SQLite 3 (Built-in Django relational database)
* **Database (Production)**     : PostgreSQL 14+ / MySQL 8.0+
* **Machine Learning Stack**    : 
  * **Scikit-Learn (v1.3+)**     : For Logistic Regression, Random Forest, and Linear Regression models
  * **Pandas (v2.x)**            : For data parsing, manipulation, and CSV handling
  * **NumPy (v1.24+)**           : For numerical computations and array features
  * **Joblib (v1.3+)**           : For serializing and loading trained models
* **Document Extraction Engine** : 
  * **PaddleOCR (v2.7+)**        : Primary deep-learning-based text extraction engine
  * **PyTesseract (v0.3.10+)**    : Fallback engine (powered by Google Tesseract OCR v5.x)
  * **Pillow (PIL v10.x)**        : For basic image loading and manipulation
  * **OpenCV-Python (v4.8+)**     : For advanced image preprocessing, sharpening, and binarization
