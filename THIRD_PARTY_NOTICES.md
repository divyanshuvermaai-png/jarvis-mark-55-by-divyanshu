# Third-Party Notices & Open Source Disclosures

**Project:** JARVIS Mark 55 (Mark-LV)  
**Project Owner & Creator:** Divyanshu Verma ([Divyanshu Industries](https://github.com/divyanshuvermaai-png))  

---

## 1. Overview & Licensing Distinction

JARVIS Mark 55 incorporates, links against, and interfaces with third-party open-source libraries, frameworks, SDKs, and assets. 

> **Important Distinction:**  
> The proprietary terms of the [LICENSE](./LICENSE) apply exclusively to the original architecture, source code, user interface designs, custom mathematical algorithms, and original materials authored by Divyanshu Verma. Nothing in the proprietary license is intended to supersede, alter, or restrict the rights granted by upstream open-source licenses governing third-party components listed below.

---

## 2. Core Python Runtime Dependencies

The following open-source packages are defined in [requirements.txt](./requirements.txt) or imported by the application runtime:

| Component | Project / Upstream URL | Declared Scope | Verified License | Copyright / Attribution Notice |
| :--- | :--- | :--- | :--- | :--- |
| **PyQt6** | [riverbankcomputing.com](https://riverbankcomputing.com/software/pyqt/) | Required Core GUI | GNU GPL v3 / Commercial | © Riverbank Computing Limited; Qt © The Qt Company |
| **sounddevice** | [spatialaudio/python-sounddevice](https://github.com/spatialaudio/python-sounddevice) | Required Audio I/O | MIT License | © 2015 Matthias Geier |
| **NumPy** | [numpy.org](https://numpy.org/) | Required Mesh / Audio Math | BSD 3-Clause | © 2005-2024 NumPy Developers |
| **google-genai** | [googleapis/python-genai](https://github.com/googleapis/python-genai) | Required Gemini Live SDK | Apache License 2.0 | © Google LLC |
| **requests** | [requests.readthedocs.io](https://requests.readthedocs.io/) | Required HTTP Client | Apache License 2.0 | © Kenneth Reitz and contributors |
| **beautifulsoup4** | [crummy.com/software/BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) | Required Web Extraction | MIT License | © Leonard Richardson |
| **playwright** | [playwright.dev/python](https://playwright.dev/python/) | Required Web Automation | Apache License 2.0 | © Microsoft Corporation |
| **yt-dlp** | [github.com/yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | Required Media Extractor | The Unlicense (Public Domain) | © yt-dlp contributors |
| **pyautogui** | [github.com/asweigart/pyautogui](https://github.com/asweigart/pyautogui) | Required Desktop Input | BSD 3-Clause | © Al Sweigart |
| **pyperclip** | [github.com/asweigart/pyperclip](https://github.com/asweigart/pyperclip) | Required Clipboard Access | BSD 3-Clause | © Al Sweigart |
| **Pillow (PIL)** | [python-pillow.org](https://python-pillow.org/) | Required Image Processing | HPND License | © 2010-2024 Alex Clark and contributors; © 1995-2011 Secret Labs AB / Fredrik Lundh |
| **opencv-python**| [github.com/opencv/opencv-python](https://github.com/opencv/opencv-python) | Required Camera Vision | Apache License 2.0 | © OpenCV Foundation |
| **mss** | [github.com/BoboTiG/python-mss](https://github.com/BoboTiG/python-mss) | Required Screen Capture | MIT License | © Mickaël Schoentgen |
| **psutil** | [github.com/giampaolo/psutil](https://github.com/giampaolo/psutil) | Required System Monitor | BSD 3-Clause | © Giampaolo Rodola |
| **send2trash** | [github.com/arsenetar/send2trash](https://github.com/arsenetar/send2trash) | Required Safe File Deletion | BSD 3-Clause | © Arsen Mamikonyan |
| **python-pptx** | [github.com/scanny/python-pptx](https://github.com/scanny/python-pptx) | Document Processor | MIT License | © Steve Canny |
| **fastapi** | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) | Remote Dashboard Backend | MIT License | © Sebastián Ramírez |
| **uvicorn** | [uvicorn.org](https://www.uvicorn.org/) | Remote Dashboard ASGI Server | BSD 3-Clause | © Encode OSS Ltd |
| **cryptography**| [github.com/pyca/cryptography](https://github.com/pyca/cryptography) | Dashboard TLS & Security | Apache 2.0 / BSD 3-Clause | © The Python Cryptographic Authority |
| **python-multipart**| [github.com/Kludex/python-multipart](https://github.com/Kludex/python-multipart) | Dashboard Form Parser | Apache License 2.0 | © Andrew Dunham |
| **qrcode** | [github.com/lincolnloop/python-qrcode](https://github.com/lincolnloop/python-qrcode) | Dashboard QR Auth Code | BSD 3-Clause | © Lincoln Loop |
| **ddgs** | [github.com/deedy5/duckduckgo_search](https://github.com/deedy5/duckduckgo_search) | Web Search Fallback | MIT License | © deedy5 |
| **pdfplumber** | [github.com/jsvine/pdfplumber](https://github.com/jsvine/pdfplumber) | Document PDF Processor | MIT License | © Jeremy Singer-Vine |
| **PyPDF2** | [github.com/py-pdf/pypdf](https://github.com/py-pdf/pypdf) | Fallback PDF Reader | BSD 3-Clause | © Mathieu Fenniak |
| **python-docx** | [github.com/python-openxml/python-docx](https://github.com/python-openxml/python-docx) | Document Word Processor | MIT License | © Steve Canny |
| **pynvml** | [github.com/gpuopenanalytics/pynvml](https://github.com/gpuopenanalytics/pynvml) | NVIDIA GPU Telemetry | BSD 3-Clause | © NVIDIA Corporation |

---

## 3. Optional & Plugin Dependencies

These packages are imported conditionally within plugins or optional modules:

| Component | Project / Upstream URL | Declared Scope | Verified License |
| :--- | :--- | :--- | :--- |
| **google-api-python-client** | [github.com/googleapis/google-api-python-client](https://github.com/googleapis/google-api-python-client) | Gmail / Calendar Plugins | Apache License 2.0 |
| **google-auth-oauthlib** | [github.com/googleapis/google-auth-library-python-oauthlib](https://github.com/googleapis/google-auth-library-python-oauthlib) | Google OAuth Flow | Apache License 2.0 |
| **tinytuya** | [github.com/jasonacox/tinytuya](https://github.com/jasonacox/tinytuya) | Home Assistant Plugin | MIT License |
| **paho-mqtt** | [github.com/eclipse/paho.mqtt.python](https://github.com/eclipse/paho.mqtt.python) | Smart Printer Plugin | EPL-2.0 / EDL-1.0 |
| **openpyxl** | [openpyxl.readthedocs.io](https://openpyxl.readthedocs.io/) | Spreadsheet Automation | MIT License |
| **youtube-transcript-api** | [github.com/jdepoix/youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) | Video Summaries | MIT License |
| **pygetwindow** | [github.com/asweigart/pygetwindow](https://github.com/asweigart/pygetwindow) | Window Management | BSD 3-Clause |
| **groq** | [github.com/groq/groq-python](https://github.com/groq/groq-python) | Groq LPU Code Reasoning | Apache License 2.0 |
| **openwakeword** | [github.com/dscripka/openWakeWord](https://github.com/dscripka/openWakeWord) | Opt-in Wake Word Detection | Apache License 2.0 |

---

## 4. Platform-Specific Windows Dependencies

Installed exclusively when `sys_platform == "win32"`:

| Component | Purpose | Verified License |
| :--- | :--- | :--- |
| **pywin32** | Windows API & shortcut creation | Python Software Foundation License (PSFL) |
| **comtypes** | Windows COM interface bridging | MIT License |
| **pycaw** | Windows Core Audio API controller | MIT License |
| **win10toast** | Windows 10/11 toast notifications | MIT License |
| **wmi** | Windows Management Instrumentation queries | MIT License |
| **pywinauto** | Windows accessibility tree automation | BSD 3-Clause License |

---

## 5. Bundled Static Assets & Scripts

| Asset / File Path | Upstream Origin | Verified License | Attribution / Notice |
| :--- | :--- | :--- | :--- |
| **`dashboard/static/crypto-js.min.js`** | [CryptoJS](https://github.com/brix/crypto-js) | MIT License | Copyright (c) 2009-2013 Jeff Mott; Copyright (c) 2013-2016 Evan Vosberg |

---

## 6. Unresolved Provenance & Asset Disclosures

In accordance with our strict verification standards, the provenance of the following assets is explicitly documented:

1. **`core/face_model.obj` & `core/face_model.mtl`**:  
   - Header indicates export via Blender LTS (`# Blender 5.2.2 LTS MTL File: 'None'`, `www.blender.org`).
   - The mesh data represents 3D facial vertices and wireframe indices used for software rendering in the PyQt6 HUD. Specific original baseline model authorship is historically indeterminate; provided as-is for the application's mathematical wireframe projection.
2. **`assets/gantry_turntable/` (frame_000.png - frame_035.png)**:  
   - 36 rendered turntable viewport frames of a gantry model used for HUD demonstration. Excluded from git distribution via `.gitignore`.

---

## 7. Contact for Third-Party Inquiries

If you are a copyright holder or representative of an upstream project and believe that an attribution, link, or license statement requires modification or clarification, please contact:

**Divyanshu Verma**  
Founder & Lead Developer, Divyanshu Industries  
Email: [divyanshuverma.ai@gmail.com](mailto:divyanshuverma.ai@gmail.com)  
Project Repository: [jarvis-mark-55-by-divyanshu](https://github.com/divyanshuvermaai-png/jarvis-mark-55-by-divyanshu)
